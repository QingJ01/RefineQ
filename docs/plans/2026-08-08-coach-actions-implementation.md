# Coach Actions Implementation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Turn explicit coach-chat requests into safe, server-authorized action proposals that the existing web UI executes through current learning APIs.

**Architecture:** `AgentService` runs the grounded reply and a context-isolated structured intent extraction concurrently. A pure action resolver validates the extracted intent against fresh owner/workspace learning state and returns a discriminated proposal with a stable action ID. The client renders proposal state, protects non-empty drafts, and executes accepted proposals through the existing question, plan, and saved-question APIs.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, SQL-backed repositories, React 19, Next.js 16 client components, TypeScript, pytest, Vitest.

---

### Task 1: Parameterize the structured transport

**Files:**
- Modify: `src/refineq/agent/structured.py`
- Test: `tests/unit/agent/test_structured.py`

**Step 1: Write the failing tests**

Add tests that monkeypatch `OpenAI` and assert the default transport still creates a client with `timeout=30.0, max_retries=2`, while `OpenAICompatibleStructuredTransport(timeout=8.0, max_retries=0)` forwards the override.

**Step 2: Run tests to verify RED**

Run: `python -m pytest tests/unit/agent/test_structured.py -q`

Expected: the custom-constructor test fails because the transport currently accepts no constructor parameters.

**Step 3: Implement the minimum change**

Add an initializer storing validated positive `timeout` and non-negative `max_retries`, then use those values when constructing `OpenAI`. Keep current defaults unchanged.

**Step 4: Run tests to verify GREEN**

Run: `python -m pytest tests/unit/agent/test_structured.py -q`

Expected: all structured transport tests pass.

### Task 2: Define and resolve coach actions

**Files:**
- Create: `src/refineq/agent/actions.py`
- Create: `tests/unit/agent/test_actions.py`

**Step 1: Write failing model and resolver tests**

Cover:

- strict discriminated intent parsing and invalid plan mutations;
- stable `blake2b(session_id:turn_id:type)` action IDs;
- current-question topic/mode/difficulty inheritance;
- difficulty boundary rejection;
- exact topic-name matching and unknown-topic candidates;
- save/unsave of the current pending question;
- `most_recent`, `next`, local `today/tomorrow`, and absolute-date session selection;
- ambiguous or missing sessions;
- preservation of local wall-clock time when moving sessions;
- rejection before today or after the exam date.

Use a wished-for pure API:

```python
proposal = resolve_action_proposal(
    intent,
    progress=progress,
    session_id="coach-session",
    turn_id="turn-1",
    timezone="Asia/Shanghai",
    now=datetime(2026, 8, 8, 12, tzinfo=UTC),
)
```

**Step 2: Run tests to verify RED**

Run: `python -m pytest tests/unit/agent/test_actions.py -q`

Expected: collection fails because `refineq.agent.actions` does not exist.

**Step 3: Implement minimal pure action models and resolver**

Create strict Pydantic models for the three intents and four proposal variants. Use `ZoneInfo`, fresh progress data, and stable reason codes. Keep matching deterministic and owner/workspace agnostic because the caller already supplies owner-scoped progress.

**Step 4: Run tests to verify GREEN**

Run: `python -m pytest tests/unit/agent/test_actions.py -q`

Expected: all action resolver tests pass.

### Task 3: Add bounded intent execution

**Files:**
- Modify: `src/refineq/agent/actions.py`
- Test: `tests/unit/agent/test_actions.py`

**Step 1: Write failing executor tests**

Exercise a `BoundedIntentExecutor(max_workers=1)` with one blocked task. Assert a second submission returns `None` immediately and the permit is released when the first task exits.

**Step 2: Run the focused test to verify RED**

Run: `python -m pytest tests/unit/agent/test_actions.py -q -k bounded`

Expected: failure because the bounded executor is missing.

**Step 3: Implement the executor**

Wrap a module-lived `ThreadPoolExecutor` with `BoundedSemaphore`. Acquire non-blocking before `submit`, release in a `finally`, and release immediately if submission itself raises.

**Step 4: Run tests to verify GREEN**

Run: `python -m pytest tests/unit/agent/test_actions.py -q`

Expected: all action tests pass.

### Task 4: Integrate intent extraction into AgentService

**Files:**
- Modify: `src/refineq/agent/service.py`
- Modify: `src/refineq/api/app.py`
- Modify: `tests/integration/test_agent_chat.py`

**Step 1: Write failing integration tests**

Add fake structured intent transports and assert:

- extraction sees only the system instruction and the exact current user message;
- valid intents become normalized proposals;
- null, invalid, timed-out, and capacity-rejected extraction degrade to no proposal;
- the grounded reply still receives the full untrusted learning context;
- a repeated `turn_id` returns the stored proposal/action ID without re-calling either model;
- plan and topic isolation reject IDs/names outside the current workspace;
- coach-system instructions forbid claiming actions have completed.

**Step 2: Run focused integration tests to verify RED**

Run: `python -m pytest tests/integration/test_agent_chat.py -q -k 'action or intent'`

Expected: failures because `AgentChatResponse` has no proposal and `AgentService` has no intent transport.

**Step 3: Implement minimal orchestration**

Inject an optional `StructuredModelTransport` and bounded executor. After the existing replay check, submit extraction, run the grounded reply, collect extraction for at most the eight-second extraction budget, re-read learning progress, resolve a proposal, and persist it in `turns[turn_id]`. Do not offer actions when `turn_id` is absent. Preserve existing tests by disabling implicit intent calls when tests inject only the legacy text transport.

**Step 4: Run integration and agent unit tests**

Run: `python -m pytest tests/integration/test_agent_chat.py tests/unit/agent -q`

Expected: all selected tests pass.

### Task 5: Extend the frontend contract and retry identity

**Files:**
- Modify: `apps/web/lib/types.ts`
- Modify: `apps/web/lib/api.ts`
- Modify: `apps/web/components/study-workspace.tsx`
- Modify: `apps/web/tests/contracts.test.ts`
- Modify: `apps/web/tests/components.test.tsx`

**Step 1: Write failing contract/retry tests**

Add TypeScript fixtures for each proposal variant. Add a component-level test in which the first coach request rejects and the second submission uses the same `turn_id`. Add a test that explicit question `requestId` overrides random ref generation.

**Step 2: Run tests to verify RED**

Run: `npm test -- --run tests/contracts.test.ts tests/components.test.tsx`

Expected: type/behavior failures because proposals and stable retry IDs are absent.

**Step 3: Implement types and stable request plumbing**

Add the discriminated `CoachActionProposal` union and optional `action_proposal`. Add `timezone` to `AgentSessionContext`. Keep a pending coach turn ID until a response is successfully processed. Allow `getQuestion` to accept an explicit request ID and return/throw so callers can determine success.

**Step 4: Run tests to verify GREEN**

Run: `npm test -- --run tests/contracts.test.ts tests/components.test.tsx`

Expected: selected tests pass.

### Task 6: Render and execute proposal states

**Files:**
- Modify: `apps/web/components/session-coach.tsx`
- Modify: `apps/web/components/study-workspace.tsx`
- Modify: `apps/web/app/styles.css`
- Modify: `apps/web/tests/components.test.tsx`

**Step 1: Write failing UI tests**

Cover rejected, executing, applied, failed, and confirmation-required cards; draft protection; successful retry with the same action ID; duplicate applied proposals producing no second write; and action failure retaining the coach reply while showing the error state.

**Step 2: Run tests to verify RED**

Run: `npm test -- --run tests/components.test.tsx`

Expected: failures because SessionCoach renders only text today.

**Step 3: Implement the smallest client state machine**

Keep action-card state inside `SessionCoach`; delegate workspace mutations through a typed callback. In `StudyWorkspace`, apply valid proposals through existing handlers, protect non-empty drafts, record successfully applied action IDs for the current page, and fetch a snapshot rather than replaying a stale write. Localize card labels in the existing zh/en copy structure.

**Step 4: Run frontend tests**

Run: `npm test`

Expected: all frontend tests pass.

### Task 7: Update demonstration documentation and verify the repository

**Files:**
- Modify: `docs/product/06-demo-script.md`

**Step 1: Add the coach-action demo beat**

Document the no-draft direct path and the draft-confirmation branch, including the split coach/action loading states.

**Step 2: Run formatting and focused checks**

Run:

```powershell
python -m ruff check src tests
python -m pytest
cd apps/web
npm test
npm run lint
npm run build
```

Expected: every command exits 0; pytest may retain the three environment-dependent PostgreSQL skips.

**Step 3: Review the diff against the design**

Confirm every v4 acceptance item is implemented, no runtime state is tracked, and user/workspace scoping remains server-enforced.

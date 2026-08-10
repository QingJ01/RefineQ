# 对抗性审查 P1 整改实现计划

> **For Claude:** REQUIRED SUB-SKILL: 用 `superpowers:test-driven-development` 逐任务实现；每个任务先写失败测试、看它失败、再实现、跑通、提交。

**Goal:** 落地 [2026-08-10 对抗性产品审查](../../../refineq-adversarial-audit-20260810/refineq-adversarial-product-audit-2026-08-10.md) 的 5 个 P1（学习证据竞态、Home 语用副作用、慢任务双重现实、截止日时区漂移、计划容量不变量），并按阶段处理 P2 体验/无障碍项。

**Architecture:** 全部基于 `main`（`4f2e07b`）。核心原则是**复用 main 已有的模式而非新建基础设施**：P1#2 移植 MCP 的 `expected_state_version` fail-closed 契约到 web；P1#1 在确定性策略层加守卫；P1#3 复用 `HomeReceiptRepository` 式客户端幂等键 + 现有条件提交；P1#4/#5 复用 `next_action._local_date` 的本地日期语义。所有迟到响应 fail closed，所有反馈只陈述可证明事实。

**Tech Stack:** Python 3.12 · FastAPI · pydantic（`extra="forbid"`）· Next.js 16 / React 19 · pytest · vitest。

**常用命令（Windows PowerShell，仓库根目录）：**
```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pytest tests/unit/learning tests/integration -q
.\.venv\Scripts\python.exe -m ruff check src tests ; .\.venv\Scripts\python.exe -m ruff format src tests
.\.venv\Scripts\python.exe scripts\scan_secrets.py
cd apps/web ; npm test ; npm run lint ; npm run build ; cd ../..
```
**基线：** 后端全绿；**每个任务结束提交**，`fix:`/`feat:`/`test:` 前缀，署名 `QingJ01 <qingj1314@163.com>`。

---

## 0. 可复用基础设施（写代码前先读，避免重造）

| 需求 | main 已有 | 位置 |
| --- | --- | --- |
| 题目版本 fail-closed | `expected_state_version` + question-id 绑定（HMAC） | `src/refineq/mcp/tools.py:499-513`、`contracts.py:158` |
| 学习状态版本号 | `store.version`，web 路径已有但不回传浏览器 | `src/refineq/learning/service.py:1026`、`:1206` |
| 幂等回执（键→操作） | `HomeReceiptRepository.transaction/get/save` + replay 模式 | `src/refineq/home/events.py:136-175`、`home/service.py:1336-1408` |
| 尝试/出题幂等 | `record_attempt`（`attempt_id` 去重 + `replayed`）、`question_generation_lock` | `src/refineq/storage/learning.py:86-140` |
| 条件提交边界 | snapshot→network→conditional-commit（内容哈希键） | `src/refineq/learning/personalized.py:126-146,254-260,339` |
| 本地日期语义 | `_local_date(value, tz_offset)`、offset-aware 倒计时 | `src/refineq/learning/next_action.py:70-72,213-214` |
| 冲突→HTTP | `LearningConflictError` → 409（已接线） | `src/refineq/api/routers/learning.py:48-58` |
| Home proposal/confirm | `propose_workspace` + confirm/revise 安全网 | `src/refineq/home/service.py:922-968`、前端 `learning-home.tsx:208-264` |

**整改顺序（审查第 6 节）：** Phase 1 = P1#2（学习证据正确，最优先）→ Phase 2 = P1#1（Agent 无副作用）→ Phase 3 = P1#3（慢任务可对账）→ Phase 4 = P1#4 + P1#5（计划不变量）→ Phase 5 = P2。

---

# Phase 1 · P1#2 题目身份状态契约 + 判分原因码

**问题：** 同 workspace 内切换学习模式触发晚到的 B 题响应，无条件 `setQuestion(B)` 覆盖当前显示的 A（前端 generation guard 只防跨 workspace）；用户按 A 作答，提交携带的却是 B 的 id，服务端只校验 id==当前 pending 就判分，证据台账记 B。判分退化为 fallback 时又用单一 blended 文案"未找到可核对的学习资料…"，即使有 citations、模型在线也照报。

**契约：** 出题返回 `state_version`；作答携带 `expected_state_version`（+ `prompt_hash`）；服务端版本不符即 409 fail closed；判分返回互斥 `reason_code`，前端按码显示恢复文案。

## Task 1.1: 判分返回结构化 reason_code（后端，纯净、独立）

**Files:**
- Modify: `src/refineq/learning/intelligence.py`（`GradingResult` `:131-142`、`fallback_grade` `:394-442`，误导文案 `:428`）
- Modify: `src/refineq/learning/service.py`（`AnswerResponse` `:268-297` 透传 `reason_code`）
- Test: `tests/unit/learning/test_intelligence.py`

**Step 1（RED）：** 写测试断言——(a) 有 trusted answer key 的正确作答不产生 `retrieval_empty` 码；(b) 无 answer key（key 被剥离/未配置资料）时 `reason_code == "insufficient_answer_evidence"` 或 `retrieval_empty`，且**当存在 citations 时绝不产生"没有资料"文案**；(c) 模型不可用走 `grader_unavailable`。原因码枚举：`ok` / `insufficient_answer_evidence` / `grader_unavailable` / `retrieval_empty` / `question_state_conflict`。

**Step 2:** 确认失败（`GradingResult` 无 `reason_code` 字段）。

**Step 3（GREEN）：** `GradingResult` 加 `reason_code: Literal[...]`；`fallback_grade` 依据 `answer_key_trusted`、`sources`、调用来源设置码；把 `:428` 那句从"无脑塞 gaps"改为**仅当 `reason_code==retrieval_empty` 且无 citations 时**才出现；`grade_answer` 的 `ModelNotConfiguredError`/`OpenAIError` 分支置 `grader_unavailable`。`AnswerResponse` 增加 `reason_code` 透传。

**Step 4:** 跑 `pytest tests/unit/learning/test_intelligence.py -q` 通过；跑全量 learning 单测无回归。

**Step 5:** commit `fix: return structured grading reason codes instead of one blended fallback line`

## Task 1.2: 出题回传 state_version、作答校验版本（后端 fail-closed）

**Files:**
- Modify: `src/refineq/learning/service.py`（`QuestionResponse` `:206-221` 加 `state_version`、`prompt_hash`，在 `:1137-1150` 构建 pending 处填充；`AnswerRequest` `:259-264` 加可选 `expected_state_version`/`prompt_hash`；`submit_answer` `:1399-1401` / `grade_once` `:1452-1454` 版本校验，镜像 `mcp/tools.py:502-513`）
- Test: `tests/integration/test_learning_journey.py`（或新增 `tests/integration/test_question_state_contract.py`）

**Step 1（RED）：** 集成测试——出题得 `state_version=v`；不改状态用 `expected_state_version=v` 作答成功；在两次之间用另一次出题把版本推进到 `v+1`，再用旧 `expected_state_version=v` 作答 → 返回 **409**（code `learning_conflict` / `question_state_conflict`），**不判分、不写证据**；`prompt_hash` 不符也 409。

**Step 2:** 确认失败（当前 `AnswerRequest` 无 `expected_state_version`，作答对任意匹配 pending 的 id 直接判分）。

**Step 3（GREEN）：** `QuestionResponse` 增 `state_version`（取 `current.version`，见 `:1026`）与 `prompt_hash`（`stable_id` over prompt+topic）；`AnswerRequest` 增可选字段；`submit_answer` 在 id 校验旁增加 `if expected_state_version is not None and before.version != expected_state_version: raise LearningConflictError("question_state_conflict")`，并在 `prompt_hash` 不符时同样拒绝。保持向后兼容（字段可选，MCP 路径不受影响）。

**Step 4:** 跑集成测试通过；全量 pytest 无回归。

**Step 5:** commit `feat: bind answers to the question state version and fail closed on conflict`

## Task 1.3: 前端 per-request staleness + 携带版本 + 按码显示（前端）

**Files:**
- Modify: `apps/web/hooks/use-practice-state.ts`（`:20-22` 增 per-question-request token）
- Modify: `apps/web/components/study-workspace.tsx`（`getQuestion` `:802-840` 捕获 token、在 apply 回调校验最新、并给 `createWorkspaceQuestion` 传 `AbortSignal`；`submitAnswer` `:863-900` 发送显示题的 `state_version`/`prompt_hash`，409 时停手并对账）
- Modify: `apps/web/lib/api.ts`（`createWorkspaceQuestion` `:519-543`、`submitWorkspaceAnswer` `:569-591` 携带/返回新字段）
- Modify: `apps/web/lib/types.ts`（`PracticeQuestion` `:294-306` 加 `state_version`/`prompt_hash`；`AnswerResult` `:323-349` 加 `reason_code`）
- Modify: `apps/web/components/learning-session-canvas.tsx`（`:422`、`:496-510` 按 `reason_code` 分支恢复文案）
- Test: `apps/web/tests/practice-navigation.test.ts` 或新增 `apps/web/tests/practice-state-contract.test.ts`

**Step 1（RED）：** 前端单测——模拟"生成 A（token t1）→ 切换学习模式生成 B（token t2）→ A 的晚到响应到达"，断言 A 的 apply 回调**不覆盖**当前 B（staleness token 拒绝）；断言 `submitAnswer` 携带当前显示题的 `state_version`；断言 `reason_code==question_state_conflict` 时显示"题目已更新，请重做当前题"，`grader_unavailable` 显示"判分服务暂不可用"，`retrieval_empty` 才显示"上传资料"。

**Step 2:** 确认失败。

**Step 3（GREEN）：** 加 per-request token（每次 `getQuestion` 递增并捕获，apply 前比对）；`createWorkspaceQuestion` 传 `AbortController.signal`，新请求/提交时 abort 旧的；`submitAnswer` 从 `question` 读 `state_version`/`prompt_hash` 一并 POST；`learning-session-canvas` 用 `reason_code` 映射文案表。

**Step 4:** `cd apps/web ; npm test` 通过。

**Step 5:** commit `fix: reject stale question responses and branch recovery copy on reason code`

## Task 1.4: 端到端真实验证（DeepSeek + bge-m3）

起后端（已配好模型的 data_root）+ 前端，用浏览器：出题 A → 切学习模式触发 B → 确认 A 不被覆盖 / 或提交旧题得 409 且不写证据；正确作答走 AI 判分且证据台账题目一致。截图留证。**不进 CI**，作为人工验收。

---

# Phase 2 · P1#1 Home 否定/引文/一次性语用守卫

**问题：** `HomeRoutingPolicy.decide()` 的 `STRONG_LONG_TERM` 分支绕过 proposal 安全网直接建空间；引号**内**的日期/分钟被 `infer_intent_constraints` 当真实约束抽走；否定从句 "do not create a **learning** workspace" 里的 "learning" 反而触发学习动词。

## Task 2.1: 约束抽取忽略引文 span（后端，单点覆盖 3 调用点）

**Files:**
- Modify: `src/refineq/workspaces/constraints.py`（`infer_intent_constraints` `:250-258`）
- Test: `tests/unit/workspaces/test_constraints.py`

**Step 1（RED）：** 测试——`infer_intent_constraints('What does "I have an exam on October 25 and study 90 minutes daily" mean?')` 的 `exam_at is None` 且 `daily_minutes is None`（引号内容不成为约束）；非引号文本仍正常抽取。

**Step 2-3:** 在抽取前用正则剥离 `"…"`/`“…”`/`「…」` span（`_strip_quoted_spans`），对剩余文本抽约束。覆盖 `policy.py:255`、`workspaces/service.py:317`、`home/service.py:930` 三个调用点。

**Step 4-5:** 测试通过；commit `fix: ignore quoted spans when extracting learning constraints`

## Task 2.2: 策略层否定/一次性守卫 + 引文剥离（后端）

**Files:**
- Modify: `src/refineq/home/policy.py`（`decide()` `:179-189` 顶部加守卫；拓宽 `_EXPLICIT_QUOTED_EXPLANATION` `:84-90`；在 `has_learning_verb/object` 计算前剥离引文）
- Test: `tests/integration/test_home_dispatch.py` + `tests/fixtures/home_dispatch_eval.json`

**Step 1（RED）：** 两条真实输入进 dispatch：
- `What does this quoted sentence mean: "…exam on October 25…90 minutes daily"? Explain it only; do not create a workspace.` → 结果 kind = `direct_answer`（或 `clarify`），**不创建 workspace、不写日历**。
- `Explain least squares. Do not create a learning workspace.` → `direct_answer`。
- 回归：正向 `我要准备9月20日线性代数期中，每天90分钟` 仍走 `propose_workspace`/`open_workspace`。

**Step 2:** 确认失败（当前建空间）。

**Step 3（GREEN）：** `decide()` 顶部加 `_NEGATED_CREATION`（`do not create|不要创建|别建`）/ `_ONE_SHOT`（`explain it only|just answer|一次性|只回答|仅解释`）→ 短路 `DIRECT_ANSWER`；在算 `has_learning_verb/object`/constraints 前对 `normalized` 剥离引文 span（复用 2.1 的 helper）；拓宽 `_EXPLICIT_QUOTED_EXPLANATION`。守卫排在 long-term 门（`:249-268`）之前。

**Step 4:** `pytest tests/integration/test_home_dispatch.py -q` 通过；补 fixtures 行。

**Step 5:** commit `fix: honor one-shot and negated-creation intent before long-term routing`

---

# Phase 3 · P1#3 针对性计划幂等键 + 客户端对账

**问题：** `POST /plan/targeted`（调模型，120s）是同步 `def`，客户端 120s abort 后服务端事务仍提交（`personalized.py:346-375`）；短路键是**内容哈希**，用户改任一字段重试即成新键 → 覆盖已提交但未见的计划。（`PUT /plan` regenerate 是确定性 30s，非本问题。）

## Task 3.1: 客户端幂等键贯穿针对性计划（后端）

**Files:**
- Modify: `src/refineq/learning/personalized.py`（`TargetedPlanRequest` `:24-34` 加 `idempotency_key`；短路/持久键 `:126-146,254-260,339` 改用客户端键）
- Modify: `src/refineq/api/routers/learning.py`（`:112-127` 透传）
- Test: `tests/integration/test_workspace_journey.py`（已 import `PlanUpdateRequest`，加 targeted 用例）或新增 `test_targeted_plan.py`

**Step 1（RED）：** 同一 `idempotency_key` 两次调用（第二次**改动** `notes` 字段）→ 返回同一 `plan.id`、**不产生第二份覆盖计划**（replay）；不同 key 才产生新计划。

**Step 2-3:** `TargetedPlanRequest` 加 `idempotency_key: str`（pattern 同 `attempt_id`）；receipt/短路以客户端键为主键（内容哈希退为附加校验），可用 `HomeReceiptRepository` 式持久化；`plan_transaction` 条件提交不变。

**Step 4-5:** 集成测试通过；commit `feat: key targeted plan generation on a client idempotency key`

## Task 3.2: 前端稳定键 + 超时对账（前端）

**Files:**
- Modify: `apps/web/lib/types.ts`（`TargetedPlanInput` `:526-535` 加 `idempotency_key`）
- Modify: `apps/web/lib/api.ts`（`createTargetedPlan` `:769-780` 发送键）
- Modify: `apps/web/components/study-workspace.tsx`（`createTargetedPlan` `:1172-1211`：为一次用户操作生成**稳定** key，408/abort 时用**同 key 重试**或 `getWorkspaceSnapshot` 对账，而非当终态失败）
- Test: `apps/web/tests/*`（targeted plan flow）

**Step 1（RED）：** 断言重试复用同一 `idempotency_key`；408 分支触发 snapshot 对账而非直接 `reportError` 终止。

**Step 2-5:** 实现 + `npm test` 通过；commit `fix: reconcile targeted plan on timeout instead of risking an overwrite`

> **可选（不在本期强制）：** 完整 operation/job store（`202 + operation_id` + 轮询 + 前端状态机），见 `docs/audits/2026-08-09-full-product-adversarial-audit.md:351-357`。本期最小修复已消除双重现实；如需泛化到其它 120s 模型调用再单独立项。

---

# Phase 4 · P1#4 截止日本地语义 + P1#5 计划容量不变量

> P1#4 与 P1#5 共享"本地日期"概念。先做 P1#4 消除 `23:59:59Z` 漂移根源，再做 P1#5 用 `timezone_offset_minutes` 按本地日期聚合容量（复用 `_local_date`）。

## Task 4.1: Home 提取本地化 + 前端读写一致 + 倒计时本地日期（P1#4，最小修复）

**Files:**
- Modify: `src/refineq/home/service.py`（`:930` 提取前用 `payload.timezone_offset_minutes` 本地化 `now`，镜像 `workspaces/service.py:316`）
- Modify: `apps/web/components/targeted-plan-builder.tsx`（`:19-34` 默认值本地日期已一致，确认；根因在存储侧）
- Modify: `apps/web/components/plan-settings.tsx`（`:104,114,175-180` 读/显示用与写入(`:146` local)相同的 tz，改用本地 `new Date(exam_at)` 派生 `YYYY-MM-DD`，去掉 `timeZone:"UTC"`）
- Modify: `apps/web/components/learning-session-canvas.tsx`（`:242-244` 倒计时改本地日历日期或直接用后端 `next_action` 的 `remaining_days`，去掉 `Math.ceil`-over-instant）
- Test: `tests/integration/test_home_dispatch.py`（提取本地化）；`apps/web/tests/*`（日期读写一致、倒计时）

**Step 1（RED）：** 后端——UTC+8 offset 下 dispatch 含 "9月20日" 的意图，proposal 的 `exam_at` 本地日期为 9-20（不是 UTC 当日 23:59:59Z 反算出的 9-21）。前端——`exam_at='2026-09-20T15:59:59Z'` 在 plan-settings 显示 `2026-09-20`；倒计时对 42 天目标显示 42 不是 43。

**Step 2-3:** 后端 `home/service.py:930` 本地化 now；前端三处按本地日期读写。

**Step 4-5:** 测试通过；commit `fix: keep the exam deadline on one local date across home dispatch and the plan form`

> **可选加固（审查根治原则的彻底版）：** 把 `exam_at` 从 `datetime` instant 迁移为 `YYYY-MM-DD` date 端到端（`constraints._exam_date` 返日期、`StudyPlan.exam_at`/请求模型/校验器改 `date`、前端绑 `<input type="date">`）。回归面大（多模型多文件），最小修复已覆盖报告实测场景；**若要做，作为独立任务并全量回归**。

## Task 4.2: 计划每日容量服务端不变量（P1#5）

**Files:**
- Modify: `src/refineq/learning/service.py`（新增 `_assert_daily_capacity(...)`；`update_plan_session` `:735` 调用；`add_plan_session` `:796` 前调用；`update_plan` 降低 `daily_minutes` 分支 `:899` 前调用；`PlanSessionUpdate`/`PlanUpdateRequest` 若需带 `timezone_offset_minutes`）
- Modify: `src/refineq/api/routers/learning.py`（`:398-417` 传 tz；409 detail 结构化 `daily_capacity_exceeded`）
- Modify: `apps/web/components/study-workspace.tsx`（`:1447-1473` 捕获 `daily_capacity_exceeded`，给冲突提示/顺延到下一空档，而非通用横幅）
- Modify: `apps/web/components/plan-timeline.tsx` / `schedule-calendar.tsx`（顺延用 tz 本地日期而非 `setUTCDate`）
- Test: `tests/integration/test_workspace_journey.py`（`PlanUpdateRequest` 已 import）

**Step 1（RED）：** 把一节改 30 分钟并顺延到已有 45 分钟的次日 → 该本地日合计 75 > `daily_minutes=45` → **409 `daily_capacity_exceeded`**，detail 含 `{date, used, requested, daily_minutes, next_free_date}`；未超载的顺延正常。

**Step 2:** 确认失败（当前 `update_plan_session` 盲写无校验）。

**Step 3（GREEN）：** `_assert_daily_capacity`：以 `timezone_offset_minutes` 把每个 `status!="completed"` 的 session `planned_at` 归到本地日期（复用 `_local_date`），聚合分钟数，目标日 `> daily_minutes` 则 `raise LearningConflictError` 带结构化 detail。三个写入点复用。前端捕获该码，顺延改用本地日期。

**Step 4-5:** 集成测试通过；commit `feat: enforce per-day plan capacity as a server invariant`

---

# Phase 5 · P2 体验与可访问性（按主题分批，每批独立提交）

> 每项先写断言（组件快照/CSS 文本/computed style/axe 规则）再改。规模小、可并行，但不阻塞 P1 发布门槛。

1. **检索"相似度"改名**（P2#1）：前端把 `Math.round(score*100)%` 的"匹配"标签改为"融合排序信号"或不显示绝对百分比；若要真相似度，后端单独返回原始 cosine。Files: `apps/web/components/source-drawer.tsx`、检索结果渲染处。
2. **来源/证据摘要层**（P2#2）：默认摘录+页码+命中高亮，原始 chunk 放二级展开。Files: `source-drawer.tsx`、`progress-topic-detail.tsx`、`evidence-ledger.tsx`。
3. **指标语义**（P2#3）：初始诊断 15% 标"先验掌握度"而非"学习进度"；失败尝试不计"完成练习 N 次"。Files: 侧栏进度、`progress-insights.tsx`。
4. **诊断证据分组**（P2#4）：按事件分组，折叠原始资料。
5. **能力状态 vs 实际后端分层**（P2#5）：管理端区分"外部能力已配置"与"当前实际检索后端(Fallback/hybrid)"。Files: `admin-console.tsx`。
6. **恢复校验文案**（P2#6）：去掉"确认口令"误导文案或补齐口令输入。Files: 备份校验弹窗。
7. **中英混排 + LaTeX**（P2#7）：任务名/教练输出本地化；教练回复渲染 LaTeX 而非原样反斜杠。
8. **对比度 WCAG**（P2#8）：进步/资料库/账户/管理/运维五页 serious `color-contrast`，统一颜色 token。Files: `apps/web/app/styles.css`。
9. **触控 44px**（P2#9）：账户页 40-42px 按钮/图标提到 ≥44px。Files: `styles.css`、`account-center.tsx`。
10. **资料分析折叠**（P2#10）：默认折叠 + 摘要 + "只看需处理项"。Files: `material-dropzone.tsx` 分析卡片。

---

# 验收与发布门槛

**每个 P1 都要有自动化回归**（审查建议）：
- 否定/引文路由矩阵（Task 2.2 fixtures）
- 迟到题目响应 barrier + 版本 409（Task 1.2/1.3）
- 结构化判分原因码（Task 1.1）
- 跨时区截止日 + 倒计时（Task 4.1）
- 顺延/编辑容量 409（Task 4.2）
- 针对性计划幂等 replay（Task 3.1）
- 保留：提示注入、两用户隔离、MCP full smoke（main 已绿，勿回归）

**全量验收：** `pytest -q` / `ruff` / `scan_secrets` / `vitest` / `eslint` / `build` 全绿 + 上述新回归 + 每个 P1 一次真实端到端（DeepSeek + bge-m3）。

**分批推送：** 每个 Phase 完成即可提交；Phase 1–4（5 个 P1）构成发布门槛，Phase 5（P2）可后续增量。

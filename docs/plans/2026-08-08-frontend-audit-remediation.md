# 前端审查修复实施计划

> **For implementation agents:** Use `superpowers:executing-plans` to implement this plan task-by-task.

**Goal:** 消除 2026-08-08 前端对抗性审查发现的全部致命问题与功能缺口，让 RefineQ 在评委的 5 分钟体验中完整、诚实地呈现它已经具备的 Agent 能力。

**Architecture:** 不改变现有架构边界。后端修复集中在 `learning/intelligence.py` 与 `workspaces/routing.py` 的降级路径；前端修复以"把已存在但未挂载的能力接回界面"为主，而非新建模块。所有改动遵循既有的 owner/workspace 隔离与降级不冒充原则。

**Tech Stack:** Python 3.12 + FastAPI + pytest；Next.js 16 + React 19 + TypeScript + Vitest + Playwright。

**问题台账：** [2026-08-08-frontend-audit-findings.md](2026-08-08-frontend-audit-findings.md)（编号 F-01…F-40、G-01…G-07 与本文一一对应）

---

## 执行顺序与时间预算

| 阶段 | 范围 | 预算 | 门槛 |
| --- | --- | --- | --- |
| Phase 0 | F-07、F-01、F-02、F-03、F-05/G-01、G-02、F-04、F-06 | 1.5 天 | 提交前必须全部完成 |
| Phase 1 | G-03…G-07 + F-08…F-30 | 4 天 | 复赛前 |
| Phase 2 | F-31…F-40 | 不限 | 赛后 |

**每个任务结束必须提交。** 提交信息用 `fix:` / `feat:` 前缀，署名 `QingJ01 <qingj1314@163.com>`。

**常用命令**（Windows PowerShell，仓库根目录）：

```powershell
# 后端
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check src tests scripts
.\.venv\Scripts\python.exe -m ruff format src tests scripts

# 前端
Set-Location apps/web
npm test
npm run lint
npm run build
Set-Location ../..

# 端到端（需要 .venv 里的 python）
Set-Location apps/web
$env:REFINEQ_PYTHON = "d:/project/personal agent/.venv/Scripts/python.exe"
npx playwright test
Set-Location ../..
```

---

# Phase 0 · 提交前必修

## Task 1: 修复 E2E 选择器，让 CI 转绿（F-07）

先做这个，因为后续每个任务都要靠 E2E 验证。

**Files:**
- Modify: `apps/web/tests/e2e/learning-journey.spec.ts:263`

**Step 1: 确认当前失败**

```powershell
Set-Location apps/web
$env:REFINEQ_PYTHON = "d:/project/personal agent/.venv/Scripts/python.exe"
npx playwright test
```

Expected: `1 failed / 4 passed`，失败信息 `Expected: 2 / Received: 3`。

**Step 2: 理解根因（不要改产品代码）**

`apps/web/components/evidence-ledger.tsx:219-221` 在每条证据的 `<li>` 内部渲染了来源 `<ul><li>`。后代选择器 `.evidence-timeline li` 把嵌套的来源项一起数入。产品行为正确。

**Step 3: 改为直接子代选择器**

```typescript
await expect(page.locator(".evidence-timeline > li")).toHaveCount(2);
```

同时检查同文件其它 `.evidence-timeline` 断言（如 `:264` 的 `not.toContainText("topic_")`）是否需要同样收窄——`toContainText` 作用于整个容器，无需改。

**Step 4: 重跑验证**

Run: `npx playwright test`
Expected: `5 passed`

**Step 5: 提交**

```bash
git add apps/web/tests/e2e/learning-journey.spec.ts
git commit -m "fix: scope evidence timeline assertion to direct children"
```

---

## Task 2: 补齐计算机与工程类科目路由（F-02）

**Files:**
- Modify: `src/refineq/workspaces/routing.py`（`_SUBJECT_HINTS`、`_capability_topics`、`_suggested_title`）
- Test: `tests/unit/workspaces/test_routing.py`

**Step 1: 写失败测试**

```python
def test_chinese_computer_science_intent_gets_readable_title_and_topics():
    decision = route_workspace(
        "10月25日考计算机组成原理期中，每天能学90分钟，先补流水线和缓存",
        [],
    )
    assert decision.subject == "computing"
    assert "10月25日" not in decision.title
    assert len(decision.title) <= 20
    for topic in decision.topics:
        assert "每天能学" not in topic
        assert len(topic) <= 20


def test_database_intent_is_not_general():
    decision = route_workspace("下周考数据库系统，重点是事务和索引", [])
    assert decision.subject == "computing"
```

**Step 2: 运行确认失败**

Run: `.\.venv\Scripts\python.exe -m pytest tests/unit/workspaces/test_routing.py -q`
Expected: FAIL，`subject == "general"`，title 为原句截断。

**Step 3: 在 `_SUBJECT_HINTS` 增加 `computing` 条目**

放在 `"science"` 之前（先匹配更具体的学科）：

```python
    "computing": (
        "计算机组成原理",
        "操作系统",
        "数据结构",
        "计算机网络",
        "数据库",
        "编译原理",
        "算法",
        "编程",
        "软件工程",
        "机器学习",
        "深度学习",
        "人工智能",
        "前端",
        "后端",
        "computer organization",
        "operating system",
        "data structure",
        "computer network",
        "database",
        "compiler",
        "algorithm",
        "programming",
        "software engineering",
        "machine learning",
        "python",
        "javascript",
    ),
```

**Step 4: 在 `_capability_topics` 增加 `computing` 映射**

```python
        "computing": (
            (("流水线", "pipeline"), "流水线与冒险"),
            (("缓存", "cache"), "缓存与存储层次"),
            (("事务", "transaction"), "事务与并发控制"),
            (("索引", "index"), "索引与查询优化"),
            (("进程", "线程", "process", "thread"), "进程与线程"),
            (("算法", "复杂度", "algorithm"), "算法与复杂度"),
        ),
```

**Step 5: 修 `_suggested_title` 的 general 兜底**

当前对 general 直接取原句前 24 字。改为：先剥离日期、时长等噪声片段，再截断；剥离后为空时回落到"个人学习"。

```python
_TITLE_NOISE = re.compile(
    r"(\d+月\d+日|\d+号|下周|明天|后天|每天\S{0,4}\d+\s*分钟|考试|准备|我想|想学)"
)


def _suggested_title(intent: str, subject: str) -> str:
    # ... 既有的分学科分支保持不变 ...
    if subject == "computing":
        return _COMPUTING_TITLES.get(...)  # 命中 hints 时取该 hint 作标题
    compact = _TITLE_NOISE.sub("", intent.strip().splitlines()[0])
    compact = compact.strip("，。！？,.!? ")[:20]
    return compact or "个人学习"
```

`computing` 分支的实现：取 `_SUBJECT_HINTS["computing"]` 中在 `normalized` 里出现且最长的那个 hint 作为标题（例如"计算机组成原理"）。

**Step 6: 运行验证**

Run: `.\.venv\Scripts\python.exe -m pytest tests/unit/workspaces/ -q`
Expected: PASS。再跑全量 `-m pytest -q` 确认没有回归（已有路由测试可能断言了 general 行为）。

**Step 7: 手工复核**

```powershell
$env:PYTHONPATH="src"; $env:PYTHONIOENCODING="utf-8"
.\.venv\Scripts\python.exe -c "from refineq.workspaces.routing import route_workspace; d=route_workspace('10月25日考计算机组成原理期中，每天能学90分钟，先补流水线和缓存',[]); print(d.title, d.subject, d.topics)"
```

Expected: 标题为「计算机组成原理」类可读短语，topics 为「流水线与冒险」「缓存与存储层次」。

**Step 8: 提交**

```bash
git add src/refineq/workspaces/routing.py tests/unit/workspaces/test_routing.py
git commit -m "fix: route computing subjects to readable titles and topics"
```

---

## Task 3: 无资料时也能出真题（F-01）

分两步：先让界面把用户推向上传（低风险），再放开无资料时的 AI 出题（有价值但需谨慎）。

### 3a. 今日页主列加上传引导

**Files:**
- Modify: `apps/web/components/learning-session-canvas.tsx:265-291`
- Modify: `apps/web/lib/i18n.ts`
- Test: `apps/web/tests/components.test.tsx`

**Step 1: 写失败测试**

```typescript
it("prompts for materials in the main column when the workspace has none", () => {
  const html = renderToStaticMarkup(
    <LearningSessionCanvas {...baseProps} materials={[]} />,
  );
  expect(html).toContain("data-testid=\"session-upload-prompt\"");
});

it("hides the upload prompt once materials exist", () => {
  const html = renderToStaticMarkup(
    <LearningSessionCanvas {...baseProps} materials={[sampleMaterial]} />,
  );
  expect(html).not.toContain("data-testid=\"session-upload-prompt\"");
});
```

**Step 2: 确认失败**

Run: `npm test -- --run tests/components.test.tsx`

**Step 3: 实现**

在 `learn` 阶段的主 CTA **之前**插入（仅当 `materials.length === 0`）：

```tsx
{materials.length === 0 && (
  <div className="session-upload-prompt" data-testid="session-upload-prompt">
    <p>{t("uploadFirstSourceTitle")}</p>
    <p className="muted">{t("uploadFirstSourceHint")}</p>
    <button type="button" className="primary-action" onClick={onOpenLibrary}>
      {t("uploadFirstSourceAction")}
    </button>
  </div>
)}
```

i18n 文案（中英各三条）：

- `uploadFirstSourceTitle`：先上传你的讲义或笔记 / Upload your own notes first
- `uploadFirstSourceHint`：题目会引用你的资料原文；没有资料时只能出通用题。 / Questions cite your own sources. Without them you only get generic tasks.
- `uploadFirstSourceAction`：去上传资料 / Add sources

**Step 4-5: 验证并提交**

```bash
git add apps/web/components/learning-session-canvas.tsx apps/web/lib/i18n.ts apps/web/tests/components.test.tsx
git commit -m "feat: guide new learners to upload sources before practising"
```

### 3b. 有模型时无资料也调 AI 出题

**Files:**
- Modify: `src/refineq/learning/intelligence.py:271-278`
- Test: `tests/unit/learning/test_intelligence.py`

**Step 1: 写失败测试**

```python
def test_generates_ai_question_without_sources_when_model_configured():
    service = LearningIntelligenceService(
        knowledge=_EmptyKnowledge(),
        settings=_ConfiguredSettings(),
        transport=_RecordingTransport(),
    )
    question = service.generate_question(
        owner_id="u1", workspace_id="w1",
        topic_id="t1", topic_name="缓存一致性",
        mastery=0.3, difficulty_level=2,
    )
    assert question.mode == "ai"
    assert question.citations == []          # 无资料时不得编造引用
    assert question.grounding == Grounding.GENERAL


def test_falls_back_when_model_missing_and_no_sources():
    service = LearningIntelligenceService(
        knowledge=_EmptyKnowledge(),
        settings=_UnconfiguredSettings(),
        transport=_RecordingTransport(),
    )
    question = service.generate_question(...)
    assert question.mode == "fallback"
```

**Step 2: 确认失败**（当前无论有无模型都返回 fallback）

**Step 3: 实现**

删除 `if not sources: return fallback_question(...)` 这个早退，改为：加载模型设置失败时才 fallback；调用模型时，无资料的提示词分支明确声明"没有可引用的资料，禁止输出任何 citation"，并在返回后强制 `citations = []`、`grounding = Grounding.GENERAL`。

**Step 4: 验证**

Run: `.\.venv\Scripts\python.exe -m pytest tests/unit/learning/ -q`，再跑全量。

**Step 5: 提交**

```bash
git add src/refineq/learning/intelligence.py tests/unit/learning/test_intelligence.py
git commit -m "feat: generate grounded-free AI questions when no sources exist"
```

---

## Task 4: 降级判分不伪造掌握度（F-03）

**Files:**
- Modify: `src/refineq/learning/intelligence.py:196-210`（`fallback_grade`）
- Test: `tests/unit/learning/test_intelligence.py`

**Step 1: 写失败测试**

```python
def test_fallback_grade_does_not_treat_fluent_structure_as_mastery_evidence():
    question = fallback_question(
        topic_id="t1", topic_name="缓存一致性",
        difficulty_level=2, sources=[],
    )
    answer = (
        "缓存一致性指多个处理器缓存中同一数据副本保持一致的性质，"
        "常用 MESI 协议维护，通过总线嗅探让写操作使其他副本失效，"
        "例如两个核心同时缓存同一变量时写入需先获得独占权。"
    )
    grade = fallback_grade(question, answer)
    assert grade.passed is False
    assert grade.mastery_evidence is False
    assert "资料" in grade.feedback


def test_fallback_grade_still_rejects_an_empty_answer():
    question = fallback_question(topic_id="t1", topic_name="缓存一致性",
                                 difficulty_level=2, sources=[])
    grade = fallback_grade(question, "不知道")
    assert grade.passed is False
    assert grade.mastery_evidence is False
```

**Step 2: 确认失败**

Expected: 第一条因当前反馈没有解释无资料降级而 FAIL；它不得因为答案够长或包含主题词就计入掌握度。

**Step 3: 实现**

根因不是“分数不够”，而是无资料且无模型时没有可验证的标准答案：

- 当 `expected_terms` 非空（有资料）：保持现有基于内容证据的逻辑。
- 当 `expected_terms` 为空（无资料）：允许给形成性反馈，但始终 `mastery_evidence=False`，反馈明确说明需要上传资料或配置模型后才能计入掌握度。
- 不得用长度、连接词或主题词堆叠代替正确性判断。Task 3b 已保证模型可用时会走 AI 语义判分；无模型路径保持诚实降级。

**Step 4: 验证**

Run: `.\.venv\Scripts\python.exe -m pytest tests/unit/learning/ -q`，再跑全量确认未影响有资料路径的既有断言。

**Step 5: 手工复核**

```powershell
$env:PYTHONPATH="src"; $env:PYTHONIOENCODING="utf-8"
.\.venv\Scripts\python.exe -c "from refineq.learning.intelligence import fallback_question, fallback_grade; q=fallback_question(topic_id='t1',topic_name='缓存一致性',difficulty_level=2,sources=[]); g=fallback_grade(q,'缓存一致性指多个处理器缓存中同一数据副本保持一致的性质，常用MESI协议维护，通过总线嗅探让写操作使其他副本失效，例如两个核心同时缓存同一变量时写入需先获得独占权。'); print(g.score, g.passed, g.mastery_evidence)"
```

Expected: `passed=False`、`mastery_evidence=False`，且反馈明确说明无资料降级不更新掌握度。

**Step 6: 提交**

```bash
git add src/refineq/learning/intelligence.py tests/unit/learning/test_intelligence.py
git commit -m "fix: explain source-free fallback grading honestly"
```

---

## Task 5: 收藏题接回界面（F-05 / G-01）

**Files:**
- Modify: `apps/web/components/learning-session-canvas.tsx`（新增收藏抽屉或在今日页尾部列出）
- Modify: `apps/web/components/study-workspace.tsx`（把 `savedQuestions` 与 `onPracticeSaved` 传下去）
- Reference: `apps/web/components/practice-card.tsx:215-236`（现成的列表渲染，可直接搬用）
- Test: `apps/web/tests/components.test.tsx`

**Step 1: 写失败测试**

```typescript
it("lists saved questions with a way to practise them again", () => {
  const html = renderToStaticMarkup(
    <LearningSessionCanvas {...baseProps} savedQuestions={[savedSample]} />,
  );
  expect(html).toContain("data-testid=\"saved-question-list\"");
  expect(html).toContain(savedSample.prompt);
});

it("shows an empty state when nothing is saved", () => {
  const html = renderToStaticMarkup(
    <LearningSessionCanvas {...baseProps} savedQuestions={[]} />,
  );
  expect(html).toContain("data-testid=\"saved-question-empty\"");
});
```

**Step 2: 确认失败**

**Step 3: 实现**

把 `practice-card.tsx:215-236` 的列表结构搬进今日页（建议放在会话区下方的可折叠区块），每条提供"再练这道题"按钮。`study-workspace.tsx` 新增 `practiceSavedQuestion(question)`，按 `question.id` 调用既有的 `api.retryWorkspaceQuestion(...)`，恢复原题而不是按 topic 生成新题；成功后清空旧结果和草稿并滚动到练习区。同时补一条空状态文案。

**Step 4: E2E 补一步**

在 `learning-journey.spec.ts` 已有的 `save-question` 断言之后，加：

```typescript
await expect(page.getByTestId("saved-question-list")).toContainText(savedPromptFragment);
await page.getByTestId("practice-saved-question").first().click();
await expect(page.getByTestId("practice-prompt")).toContainText(savedPromptFragment);
```

**Step 5: 验证**

Run: `npm test`、`npx playwright test`

**Step 6: 提交**

```bash
git add apps/web/components/learning-session-canvas.tsx apps/web/components/study-workspace.tsx apps/web/tests/
git commit -m "feat: surface saved practice questions in the learning session"
```

---

## Task 6: 判分后显示掌握度变化（G-02）

**Files:**
- Modify: `apps/web/components/study-workspace.tsx`（提交前记录该主题旧掌握度）
- Modify: `apps/web/components/learning-session-canvas.tsx:355-403`（reflect 卡渲染）
- Modify: `apps/web/lib/i18n.ts`
- Test: `apps/web/tests/components.test.tsx`

**Step 1: 写失败测试**

```typescript
it("shows mastery before and after grading", () => {
  const html = renderToStaticMarkup(
    <LearningSessionCanvas
      {...baseProps}
      result={{ ...sampleResult, mastery: 0.57, mastery_updated: true }}
      masteryBefore={0.42}
    />,
  );
  expect(html).toContain("42%");
  expect(html).toContain("57%");
});

it("explains when mastery did not change", () => {
  const html = renderToStaticMarkup(
    <LearningSessionCanvas
      {...baseProps}
      result={{ ...sampleResult, mastery_updated: false }}
      masteryBefore={0.42}
    />,
  );
  expect(html).toContain("data-testid=\"mastery-unchanged\"");
});
```

**Step 2: 确认失败**

**Step 3: 实现**

- `study-workspace.tsx` 的 `submitAnswer` 在发请求前记录 `progress?.mastery?.[question.topic_id]` 到一个 ref，判分后作为 `masteryBefore` 传给画布。
- reflect 卡渲染 `42% → 57%`（含涨跌方向），`mastery_updated === false` 时改渲染说明文案（可直接复用 `practice-card.tsx:168` 的 `masteryNotUpdated`）。

**Step 4-5: 验证并提交**

```bash
git add apps/web/components/ apps/web/lib/i18n.ts apps/web/tests/components.test.tsx
git commit -m "feat: show mastery change on the grading card"
```

---

## Task 7: 模型探测失败不再锁死教练（F-04）

**Files:**
- Modify: `apps/web/lib/model-capability.ts`
- Modify: `apps/web/components/session-coach.tsx:333,349,354`
- Modify: `apps/web/components/agent-panel.tsx:75-76,98,269`
- Modify: `apps/web/components/study-workspace.tsx:1102`
- Test: `apps/web/tests/model-capability.test.ts`、`apps/web/tests/components.test.tsx`

**Step 1: 写失败测试**

```typescript
it("keeps the coach usable when capability detection failed", () => {
  const html = renderToStaticMarkup(
    <SessionCoach {...baseProps} modelConfigured={null} />,
  );
  expect(html).not.toContain("disabled=\"\"");
  expect(html).toContain("data-testid=\"coach-recheck\"");
});

it("disables input only when the model is known to be unconfigured", () => {
  const html = renderToStaticMarkup(
    <SessionCoach {...baseProps} modelConfigured={false} />,
  );
  expect(html).toContain("disabled");
});
```

**Step 2: 确认失败**

**Step 3: 实现**

三条语义分开：

| 状态 | 含义 | 行为 |
| --- | --- | --- |
| `true` | 已配置 | 正常 |
| `false` | 确认未配置 | 禁用输入 + 管理员显示配置按钮 + 普通用户显示"请联系管理员配置模型"（解决 F-22） |
| `null` | 探测失败 | **允许发送**，失败后再降级；显示"重新检测"按钮 |

把 `disabled={... || modelConfigured !== true}` 改为 `disabled={... || modelConfigured === false}`。在 `study-workspace.tsx` 实现唯一的 `recheckModelCapability()`：调用 `loadModelCapability` 后更新父级 `modelConfigured`，并作为 `onRecheck` 同时传给 `SessionCoach` 和 `AgentPanel`。

`agent-panel.tsx` 不再用父级 `null` 覆盖本地重检结果；合并语义固定为：已知任一处为 `false` 时禁用，父级为 `true` 时启用，父级为 `null/undefined` 时采用最近一次本地探测结果。测试必须实际调用 `onRecheck`，覆盖 `null → true`、`null → false` 与再次失败仍为 `null`，而非只检查静态 HTML。

**Step 4-5: 验证并提交**

```bash
git add apps/web/lib/model-capability.ts apps/web/components/ apps/web/tests/
git commit -m "fix: distinguish unknown model capability from unconfigured"
```

---

## Task 8: 统一前后端上传限制（F-06）

**Files:**
- Modify: `apps/web/lib/upload-flow.ts:5-6`
- Modify: `apps/web/components/material-dropzone.tsx:341`
- Modify: `apps/web/lib/i18n.ts`（"不能超过 25 MB" → 20 MB）
- Modify: `apps/web/lib/error-messages.ts`（补 `material_limit`、`unsupported_material`、`material_extraction_failed` 等，见 F-20）
- Test: `apps/web/tests/contracts.test.ts`

**Step 1: 写失败测试**

```typescript
it("rejects files above the server limit locally", () => {
  expect(validateUploadFile({ name: "a.pdf", size: 21 * 1024 * 1024 }))
    .toBe("file_too_large");
});

it("rejects extensions the server does not accept", () => {
  expect(validateUploadFile({ name: "notes.markdown", size: 1024 }))
    .toBe("unsupported_type");
});
```

**Step 2: 确认失败**（当前两条都返回 `null`）

**Step 3: 实现**

- `MAX_UPLOAD_BYTES` 改为 `20 * 1024 * 1024`，与 `src/refineq/knowledge/policy.py:34` 对齐。
- `SUPPORTED_EXTENSIONS` 去掉 `markdown`；`accept` 属性同步改为 `.pdf,.docx,.txt,.md`。
- i18n 文案改 20 MB（中英）。
- 在 `error-messages.ts` 补齐服务端会抛但前端未映射的 code（至少 `material_limit`、`unsupported_material`、`material_extraction_failed`、`material_not_found`、`workspace_not_found`、`request_body_too_large`）。

**Step 4-5: 验证并提交**

```bash
git add apps/web/lib/ apps/web/components/material-dropzone.tsx apps/web/tests/contracts.test.ts
git commit -m "fix: align client upload limits with server policy"
```

---

## Phase 0 收尾：全量验收

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check src tests scripts
.\.venv\Scripts\python.exe -m ruff format --check src tests scripts
.\.venv\Scripts\python.exe scripts\scan_secrets.py
Set-Location apps/web
npm test; npm run lint; npm run build
$env:REFINEQ_PYTHON = "d:/project/personal agent/.venv/Scripts/python.exe"
npx playwright test
Set-Location ../..
```

**全部绿灯才算 Phase 0 完成。** 然后按 [06-demo-script.md](../product/06-demo-script.md) 用全新账号在非开发机器上完整走一遍。

---

# Phase 1 · 复赛前

以下按任务分组，每组仍遵循"写测试 → 确认失败 → 实现 → 验证 → 提交"。

## Task 9: 功能缺口补齐（G-03…G-07）

| 子项 | 文件 | 做法 |
| --- | --- | --- |
| G-03 考试倒计时 | `learning-session-canvas.tsx` 顶部、`workspace-switcher.tsx` | 用现成的 `daysLeft` i18n 键（`i18n.ts:67,255`）+ `plan.exam_at` 计算 |
| G-04 复习队列上今日页 | `study-workspace.tsx:1086-1125` | 把 `ReviewQueue` 也挂到 `today` section，仅在有到期项时显示 |
| G-05 日历区分活动类型 | `schedule-calendar.tsx:111,131` | 渲染 `session.activity`，复习用不同色标；参考 `plan-timeline.tsx:60-62` 的既有标签 |
| G-06 学习报告卡 | 新增 `components/learning-report.tsx`，挂在 progress 页顶部 | 使用现有 `LearningInsights.attempts` 与 `mastery_history` 的时间戳计算最近 7 天；当前值来自 `progress.mastery`，窗口基线取窗口开始前每个 topic 的最后一个 history 点，没有基线时标记为“暂无对比”，不得从累计计数伪造周数据 |
| G-07 reflect 阶段三个出口 | `learning-session-canvas.tsx:355-403` | 加"看进步"链接、"重做这题"（复用 `retryAttempt`）、把收藏按钮也放进 reflect 分支 |

## Task 10: 会场翻车风险（F-08…F-19）

按台账逐条修，建议顺序：F-08（insights loading 态）→ F-09（假失败闪屏）→ F-10（取消上传误报）→ F-12（出题并发 disabled）→ F-14（恢复失败提示）→ F-15（409 重新同步按钮）→ F-16（account 区分 401）→ F-11（管理端错误文案）→ F-13（上传串行化）→ F-17（上传 cleanup + beforeunload）→ F-18（reflect 死屏兜底）→ F-19（超时语义）。每项至少先补一条能复现台账行为的失败测试，再实现，不作为一个不可验证的大提交处理。

| 编号 | 最低回归验收 |
| --- | --- |
| F-08/F-09/F-14 | loading 与 error 状态互斥，恢复失败信息在登录界面可见 |
| F-10/F-17 | 用户取消不报错；卸载会 abort 在途上传并在离开前提示 |
| F-11/F-15/F-16 | 不渲染 Python 异常；409 可重新同步；仅 401/403 清会话 |
| F-12 | `use-practice-state.ts` 暴露 `practiceBusy`，三个出题入口均在 busy 时 disabled |
| F-13 | 同一用户多文件按队列串行上传，不再触发并发租约冲突 |
| F-18 | `result` 有值而 `question` 缺失时仍显示恢复/开始下一题出口；后端 snapshot 优先用 attempt 的 `question_snapshot` 恢复题面 |
| F-19 | 区分连接/响应超时和调用方取消；mutation 超时后的重试继续沿用幂等 request/attempt ID，不宣称未知结果“成功”或“失败” |

## Task 11: 错误与国际化（F-20…F-23、F-25）

- 补齐 `error-messages.ts` 映射（若 Task 8 未做完）。
- 加 `navigator.onLine` 检测，断网时给专门文案。
- `app/error.tsx`、`loading.tsx`、`not-found.tsx` 读 locale；新增 `app/global-error.tsx`。
- `admin-route.tsx:54` 改用错误码映射而非后端英文原文；`integrations/service.py:106` 的 `Connection succeeded` 改为返回结构化状态由前端本地化。
- `submitAnswer` 开头补 `setError("")`。
- `topic_id` 兜底改为"未命名主题"而非裸 ID。

## Task 11b: 草稿保护（F-24）

- `changeLearningMode`、`retryAttempt`、收藏题重练和其他替换当前题目的入口统一复用 `hasUnsavedPracticeDraft`。
- 有非空草稿时先显示确认对话框；取消不得清草稿、换题或发请求，确认后才执行。
- 在 `coach-actions.test.ts` 或新增 `practice-navigation.test.ts` 覆盖取消与确认两条路径，并补一条 Playwright 手机点击回归。

## Task 12: 移动端（F-26…F-30）

- F-26 日历：640px 断点改为按周列表或纵向议程，不再强塞 7 列网格。
- F-27 文案："拖入文件" → "选择文件或拖入"（中英同改）。
- F-28 触控：`.recent-card-actions button`、`.material-actions button` 最小 44×44，并移出全卡点击区。
- F-29 可供性：为 hover 态补 `:focus-visible` 与 `@media (hover: none)` 分支。
- F-30 会话接力：继续以 `sessionStorage` 保存短期 bearer token，不写入 `localStorage`。新增同源 `BroadcastChannel` 请求/响应握手，让新标签页能向已登录标签页请求一次会话副本；响应只在用户仍登录且消息来源同源时发出，设置短超时并在关闭 channel 时清理监听。长期“记住我”另立后端 HttpOnly refresh/session cookie 设计，不在前端持久化 bearer token。

---

# Phase 2 · 赛后清理

| 任务 | 内容 |
| --- | --- |
| Task 13 | `review.py` 二选一：接上（前端加 again/hard/good/easy 评分入口，主流程改用 `schedule_review`）或删除（含其测试）。**不要继续留着**（F-31） |
| Task 14 | 复习会话按 topic 去重 + `limit`，防止队列无限膨胀（F-32） |
| Task 15 | 路由理由持久呈现：渲染 `routing_summary`，取消 7 秒自毁（F-33） |
| Task 16 | 题目 `explanation` 下发前端，作为"为什么考这道题"（F-34） |
| Task 17 | `agent-panel` 支持动作提案，或在其请求中关闭意图抽取以省一次模型调用（F-35） |
| Task 18 | 删除 `coach-actions.ts` 的 `historical` 死分支及对应测试（F-36） |
| Task 19 | 首页↔空间共享 snapshot，消除双倍请求与整体重挂载（F-37） |
| Task 20 | 空计划时 path/calendar 页给完整引导；`progress-insights` 空状态套卡片外壳（F-38、F-39） |
| Task 21 | `loading.tsx` 文案按路由区分（F-40） |
| Task 22 | 清理 `practice-card.tsx`：Task 5/6 迁移完成后，删除剩余死代码与对应 CSS |

---

## 完成定义

全部阶段完成时，以下必须同时成立：

1. 七道验收关卡全绿（含 Playwright）。
2. 全新账号在非开发机器上，5 分钟内完成"说目标 → 上传 → 出题 → 作答 → 判分 → 看进步"，且：
   - 学习空间标题是可读短语，不是原句截断；
   - 未上传资料时主列有明确上传引导；
   - 判分卡显示掌握度前→后；
   - 收藏的题能在界面上找到；
   - 教练在网络抖动后仍可用（或有重新检测按钮）。
3. 移动端（390×844）完成同一条链路，无横向溢出、无 console 错误。
4. F-01…F-40、G-01…G-07 均有对应提交或明确的“验证后无需改动”证据；不得以赛后、时间紧张或仅文档说明作为未完成项。

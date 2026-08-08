# 前端对抗性审查 · 问题台账

> 审查日期：2026-08-08 · 基线提交：`ed5eb70` · 审查方式：只读代码审查 + 真实浏览器运行 + 后端函数实跑
> 配套修复计划：[2026-08-08-frontend-audit-remediation.md](2026-08-08-frontend-audit-remediation.md)

本文件是问题台账，只记录"发现了什么、证据在哪、为什么要紧"。修复步骤在配套的实施计划里。

## 验证基线

审查时实测的工程状态，修复后应保持或改善：

| 关卡 | 命令 | 当前结果 |
| --- | --- | --- |
| 后端测试 | `python -m pytest -q` | 330 passed, 3 skipped ✅ |
| 前端测试 | `npm test` | 119 passed ✅ |
| Python 静态检查 | `ruff check` / `ruff format --check` / `scan_secrets.py` | 全过 ✅ |
| 前端 Lint | `npm run lint` | 通过 ✅ |
| 生产构建 | `npm run build` | 通过，7 条路由 ✅ |
| 浏览器端到端 | `npx playwright test` | **1 failed / 4 passed ❌** |
| 移动端（iPhone 13，390×844） | 自建脚本 | 无横向溢出、零 console 错误 ✅ |

## 已排除的误报

以下三项在移动端 fullPage 截图里看似缺陷，静态核对后确认正常，**不要修**：

- "跳到主要内容" skip link 悬浮遮挡 —— [styles.css:1777-1792](../../apps/web/app/styles.css#L1777) 用 `translateY(-160%)` 隐藏、仅 `:focus-visible` 显示，符合无障碍规范。
- 黑色圆形 "N" 徽标遮挡文字 —— Next.js 开发工具徽标，生产构建不存在。
- 移动端提交按钮盖住次要按钮 —— [styles.css:6817-6831](../../apps/web/app/styles.css#L6817) `mobile-sticky-task-action` 是刻意设计（整宽 CTA + 44px 触控 + `env(safe-area-inset-bottom)`）。

三者均为 Playwright fullPage 截图对 `position: fixed/sticky` 元素的拼接假象。

---

## P0 · 提交前必修

### F-01 无资料时不调用 AI，出硬编码模板题

**证据：** [intelligence.py:271-278](../../src/refineq/learning/intelligence.py#L271-L278) 在 `self._settings.load()` **之前**提前返回：

```python
if not sources:
    return fallback_question(...)   # 早于模型配置加载
```

实跑验证：

```
无资料时的题目: 请用自己的话解释"缓存一致性"，并给出一个关键例子或应用。
```

**为什么要紧：** 即使模型完全配置好，用户未上传资料时第一道题就是这句模板。而新用户的自然动作正是先点今日页的主 CTA"进入实战任务"——[learning-session-canvas.tsx:265-291](../../apps/web/components/learning-session-canvas.tsx#L265-L291) 的主列没有任何上传入口，唯一资料提示是右侧窄栏一句灰字。评委看到模板题会直接判定"AI 没在工作"，这是整个产品叙事的穿帮点。

**修复方向：** 二选一或都做——(a) 今日页主列加显著上传引导，把用户推向有资料的路径；(b) 有模型配置时，无资料也调 AI 出题（提示词声明无引用可用，禁止编造引用）。

---

### F-02 中文理工科意图路由退化，标题与知识点变成整句原话

**证据：** 实跑 `route_workspace`：

```
输入: 10月25日考计算机组成原理期中，每天能学90分钟，先补流水线和缓存
  标题: 10月25日考计算机组成原理期中，每天能学90分   ← 原句前 24 字
  学科: general
  主题: ['10月25日考计算机组成原理期中每天能学90分钟先补流水线和']   ← 整句去标点

输入: 下周考数据库系统，重点是事务和索引
  主题: ['下周考数据库系统重点是事务和索引']
```

根因在 [routing.py](../../src/refineq/workspaces/routing.py) 的 `_subject()` 关键词表：覆盖数学、语言、理科、人文、产品，**计算机与编程类科目全部落到 `general`**，于是 `_suggested_title()` 取原句截断、`_topics()` 取整句。

**为什么要紧：** 后果连锁到出题——模板题把整句话当知识点填进去，实测题面为「请用自己的话解释"10月25日考计算机组成原理期中每天能学90分钟先补流水线和"」。配了模型时 AI 路由会给出合理标题，所以这是降级路径专属问题，但动态测评环境或模型抖动时必然暴露。

**修复方向：** 关键词表补计算机/编程/工程类科目及其常见考试名；`_suggested_title` 对 general 分支不再直接截断原句，改为抽取名词短语或给出中性标题。

---

### F-03 降级判分数学上不可能及格，掌握度永不更新

**证据：** [intelligence.py:196-210](../../src/refineq/learning/intelligence.py#L196-L210)。无资料时 `expected_answer` 就是主题名本身（[intelligence.py:107](../../src/refineq/learning/intelligence.py#L107)），于是：

```python
expected_terms = _concept_terms(question.expected_answer) - topic_terms   # 空集
required_matches = min(2, len(expected_terms))                            # 0
concept_present = bool(required_matches) and ...                          # 恒 False
score = (25 if substantive) + (45 if concept_present)                     # 45 分永远拿不到
mastery_evidence = substantive and concept_present                        # 恒 False
```

实跑一段专业准确的完整答案：

```
优秀答案得分: 55 | 通过: False | 计入掌握度: False
```

`mastery_evidence=False` → [service.py:943-956](../../src/refineq/learning/service.py#L943) 跳过 BKT 与难度更新 → 进度条永远 0%。

**为什么要紧：** 评委写出满分答案、拿 55 分、进度纹丝不动，且没有任何解释——唯一解释文案 `masteryNotUpdated` 在死代码里（见 F-05）。"看进步"这一环在无模型演示中恒为空。

**修复方向：** 不得仅凭长度、结构或主题词覆盖把答案计为掌握度证据。模型可用时走无资料 AI 出题与语义判分；模型不可用时应改成具有确定答案的客观模板题，或明确标注"本次为无资料降级判分，不计入掌握度"并在界面上说明。宁可不更新掌握度，也不能用流畅度冒充正确性。

---

### F-04 模型探测失败返回 `null`，教练永久禁用且无重查路径

**证据：** [model-capability.ts:6-8](../../apps/web/lib/model-capability.ts#L6) 任何异常返回 `null`，而消费端把 `null` 当禁用：

- [session-coach.tsx:333](../../apps/web/components/session-coach.tsx#L333)（建议按钮）、[:349](../../apps/web/components/session-coach.tsx#L349)（输入框）、[:354](../../apps/web/components/session-coach.tsx#L354)（发送）均为 `disabled={... || modelConfigured !== true}`
- [agent-panel.tsx:326,330](../../apps/web/components/agent-panel.tsx#L326) 同理

`modelConfigured` 只在 [study-workspace.tsx:213-216](../../apps/web/components/study-workspace.tsx#L213)（会话恢复）与 [:319-322](../../apps/web/components/study-workspace.tsx#L319)（登录）各设置一次，**没有任何重试路径**。

自愈探测也被短路：[agent-panel.tsx:75-76](../../apps/web/components/agent-panel.tsx#L75) 判断 `configuredFromWorkspace === undefined`，而传入的是 `null`（[study-workspace.tsx:1102](../../apps/web/components/study-workspace.tsx#L1102)），于是 [:98](../../apps/web/components/agent-panel.tsx#L98) 的 `settingsRequest` 变成 `Promise.resolve(null)`，永不自行重查。且 [:269](../../apps/web/components/agent-panel.tsx#L269) 的"配置模型"按钮要求 `modelConfigured === false`，`null` 时连管理员出口都消失。

**为什么要紧：** 会场 WiFi 抖一次，整场演示教练全灰，只能刷新整页。这是"产品叫 Agent，但 Agent 面板是死的"的展示风险。

**修复方向：** 区分"确认未配置（false）"与"探测失败（null）"两种状态；`null` 时允许发送并在失败后再降级，或提供显式"重新检测"按钮；修正 `agent-panel` 的 `undefined` 判断使其能自行重查。

---

### F-05 收藏功能是只进不出的黑洞（practice-card.tsx 整体死代码）

**证据：** [practice-card.tsx](../../apps/web/components/practice-card.tsx) 全仓引用只有 `tests/components.test.tsx:14`，`app/` 与 `components/` 无任何渲染点。随之埋没的功能：

| 功能 | 位置 |
| --- | --- |
| 收藏题列表与回放 | [practice-card.tsx:215-236](../../apps/web/components/practice-card.tsx#L215) |
| 判分后掌握度百分比 | [:163](../../apps/web/components/practice-card.tsx#L163) |
| `masteryNotUpdated` 说明 | [:168](../../apps/web/components/practice-card.tsx#L168) |
| AI/模板 出题与判分标识 | [:111](../../apps/web/components/practice-card.tsx#L111)、[:166](../../apps/web/components/practice-card.tsx#L166) |
| 难度手选 | [:79-95](../../apps/web/components/practice-card.tsx#L79) |
| 重做本主题 | [:192-202](../../apps/web/components/practice-card.tsx#L192) |
| 误区（misconceptions）渲染 | [:172](../../apps/web/components/practice-card.tsx#L172) |

`savedQuestions` 确实进了 state（[use-workspace-state.ts:27,40](../../apps/web/hooks/use-workspace-state.ts#L27)），但全应用只用于一个布尔判断（[learning-session-canvas.tsx:217](../../apps/web/components/learning-session-canvas.tsx#L217)）。`api.listWorkspaceSavedQuestions`（[api.ts:297](../../apps/web/lib/api.ts#L297)）除契约测试外从未调用。

**为什么要紧：** 用户点"收藏任务"→ 按钮变"取消收藏"→ 换题后这道题永久消失，没有入口、没有列表、没有空状态。评委问"我收藏的题在哪"无法回答。团队自己的文档仍在按这个文件规划改动（[04-experience.md:47,62](../product/04-experience.md)），说明是重构时漏掉的迁移，不是有意废弃。

---

### F-06 前后端上传限制不一致

**证据：**

| 项 | 前端 | 后端 |
| --- | --- | --- |
| 单文件上限 | 25 MB（[upload-flow.ts:6](../../apps/web/lib/upload-flow.ts#L6)） | 20 MB（[policy.py:34](../../src/refineq/knowledge/policy.py#L34)） |
| 扩展名 | 含 `.markdown`（[upload-flow.ts:5](../../apps/web/lib/upload-flow.ts#L5)、[material-dropzone.tsx:341](../../apps/web/components/material-dropzone.tsx#L341)） | 不含 `.markdown`（[policy.py:8-13](../../src/refineq/knowledge/policy.py#L8)） |

**为什么要紧：** 20–25 MB 的文件或 `.markdown` 文件通过本地校验 → 弱网上传数分钟 → 服务端拒绝（`material_limit` / `unsupported_material`，两者都不在前端错误映射表里）→ 队列显示写死的"上传失败，可以重试"（[material-dropzone.tsx:177,188,194](../../apps/web/components/material-dropzone.tsx#L177)），横幅显示兜底文案。用户按重试会永远失败，且没有任何一句话说明真实原因。

---

### F-07 E2E 选择器过松导致 CI 变红

**证据：** [learning-journey.spec.ts:263](../../apps/web/tests/e2e/learning-journey.spec.ts#L263) 断言 `.evidence-timeline li` 数量为 2，实际 3。根因是 [evidence-ledger.tsx:219-221](../../apps/web/components/evidence-ledger.tsx#L219) 在证据条目内部嵌套了来源 `<ul><li>`，被后代选择器一起数入。

**产品行为正确**（失败截图显示 EVIDENCE / 02，列表两条）。这是测试缺陷，不是回归。

**为什么要紧：** 提交清单要求 E2E 全绿，静态测评看工程质量的第一眼就是 CI 状态。

**修复方向：** 选择器改为直接子代 `.evidence-timeline > li`。

---

## P1 · 复赛前

### 会场翻车风险

| 编号 | 问题 | 证据 | 后果 |
| --- | --- | --- | --- |
| F-08 | insights 拉取无 loading 标志，消费方一律 `?? []` | [study-workspace.tsx:167-180](../../apps/web/components/study-workspace.tsx#L167)、[:1186](../../apps/web/components/study-workspace.tsx#L1186) | 弱网下先显示"当前没有到期复习"，几秒后才冒出数据，最易被误判为"产品没数据" |
| F-09 | "暂时无法打开这个学习空间"假失败闪屏 | [study-workspace.tsx:890](../../apps/web/components/study-workspace.tsx#L890) 先 `setWorkspace(null)` 再 `router.push`，命中 [:913](../../apps/web/components/study-workspace.tsx#L913) 分支；[:919](../../apps/web/components/study-workspace.tsx#L919) 标题说失败、[:920](../../apps/web/components/study-workspace.tsx#L920) 正文说加载中 | 每次点"所有空间"或撤销路由都闪一次，标题与正文自相矛盾 |
| F-10 | 取消上传弹出"操作失败"横幅 | [material-dropzone.tsx:220-223](../../apps/web/components/material-dropzone.tsx#L220) abort → [api.ts:126](../../apps/web/lib/api.ts#L126) 原样抛 AbortError → [study-workspace.tsx:599](../../apps/web/components/study-workspace.tsx#L599) `reportError` | 用户主动取消，被告知失败 |
| F-11 | 管理后台渲染 Python 异常原文 | [admin-console.tsx:780,803](../../apps/web/components/admin-console.tsx#L780) 直接 `setError(result.message)`，来源 [integrations/service.py:97-104](../../src/refineq/integrations/service.py#L97) 的 `str(error)` | 中文界面弹出 `Client error '401 Unauthorized' for url ...`；成功文案也是英文写死的 `Connection succeeded` |
| F-12 | 出题并发无保护 | [progress-insights.tsx:65-69](../../apps/web/components/progress-insights.tsx#L65)、[review-queue.tsx:49](../../apps/web/components/review-queue.tsx#L49) 无 `disabled`；[plan-timeline.tsx:68-74](../../apps/web/components/plan-timeline.tsx#L68) 的 disabled 是改计划的 busy。generation 只在 hydrate/clear 时递增（[use-practice-state.ts:25,47](../../apps/web/hooks/use-practice-state.ts#L25)），并发请求拿到同一 generation | 手机连点两个主题，先返回的解锁 UI、后返回的换掉题目，答案错位 |
| F-13 | 多文件并行上传抢全局租约锁 | [material-dropzone.tsx:211](../../apps/web/components/material-dropzone.tsx#L211) `forEach` 并行发起；后端 [materials.py:155-165](../../src/refineq/api/routers/materials.py#L155) 抢不到即 409 | 选 5 个文件大概率 4 个失败 |
| F-14 | 恢复会话非 401 失败时静默甩回登录页 | [study-workspace.tsx:276](../../apps/web/components/study-workspace.tsx#L276) 设了 error 但未设 auth → [:912](../../apps/web/components/study-workspace.tsx#L912) 渲染 `AuthPanel`，而它用自己的局部 error state（[auth-panel.tsx:33](../../apps/web/components/auth-panel.tsx#L33)） | 会话仍在，用户却看到干净的登录表单，无任何提示 |
| F-15 | 409 冲突无"重新同步"入口 | 错误文案字面"请刷新后重试"（[error-messages.ts:29](../../apps/web/lib/error-messages.ts#L29)）；`refreshWorkspaceSnapshot`（[study-workspace.tsx:688-697](../../apps/web/components/study-workspace.tsx#L688)）只能由 coach action 触发 | 用户停在练习阶段，手里的题服务端已没了，只能手动刷新 |
| F-16 | `/account` 任何失败即登出 | [account-center.tsx:319-322](../../apps/web/components/account-center.tsx#L319) 对任何 rejection（含 30s 超时、502）都 `clearLearningSession` + 跳转 | 弱网点一次"账户与安全"就被踢出登录 |
| F-17 | 上传中切页丢队列、不 abort、无 beforeunload | `MaterialDropzone` 仅在 `section === "materials"` 渲染（[study-workspace.tsx:1154-1167](../../apps/web/components/study-workspace.tsx#L1154)），组件内无 cleanup；全站仅管理端有 beforeunload（[admin-console.tsx:732,742](../../apps/web/components/admin-console.tsx#L732)） | 切页后队列清空、请求继续跑；刷新或关标签页静默丢失 |
| F-18 | `result` 存在但 `question` 为 null → 主区无任何按钮 | [learning-session.ts:79](../../apps/web/lib/learning-session.ts#L79) 只看 result 就返回 `reflect`，而 [learning-session-canvas.tsx:355](../../apps/web/components/learning-session-canvas.tsx#L355) 要求 `question` 非空；三个分支可同时 falsy | 题目被历史驱逐（[service.py:736-747](../../src/refineq/learning/service.py#L736)）后死屏 |
| F-19 | api.ts 超时竞态：成功却报超时 | [api.ts:97-100,122-126](../../apps/web/lib/api.ts#L97) 定时器 abort 与响应体流式读取存在竞态 | 弱网 + 大 snapshot 时出现"其实成功了却报超时" |
| F-20 | 错误码映射缺 14 个 + 无断网检测 | [error-messages.ts:5-56](../../apps/web/lib/error-messages.ts#L5) 只覆盖 21 个 code；缺 `unsupported_material`、`material_limit`、`material_not_found`、`workspace_not_found`、`request_body_too_large`、`integration_not_configured` 等。全仓无 `navigator.onLine` | 断网与服务器 500 对用户是同一句话 |
| F-21 | 管理端与全局错误页硬编码中文 | [admin-route.tsx:54,66](../../apps/web/components/admin-route.tsx#L54) 渲染后端英文 message；[error.tsx:14-22](../../apps/web/app/error.tsx#L14)、[loading.tsx:16-25](../../apps/web/app/loading.tsx#L16)、[not-found.tsx:12-19](../../apps/web/app/not-found.tsx#L12) 不读 locale；无 `app/global-error.tsx` | 英文评委撞 404 看到中文；root layout 抛错退化成白屏 |
| F-22 | `model_not_configured` 提示对普通用户不可操作 | 配置按钮均要求 `isAdmin`（[session-coach.tsx:299](../../apps/web/components/session-coach.tsx#L299)、[agent-panel.tsx:269](../../apps/web/components/agent-panel.tsx#L269)） | 普通账号只看到"没配置 / 仍可继续"，没有一句告诉他找谁配 |
| F-23 | 原始 `topic_id` 泄漏到界面 | [learning-session-canvas.tsx:199-201](../../apps/web/components/learning-session-canvas.tsx#L199)、[schedule-calendar.tsx:111,131](../../apps/web/components/schedule-calendar.tsx#L111) 的 `?? topic_id` 兜底 | 快照与 insights 不同步的瞬间显示 `topic_xxxx` |
| F-24 | 学习方式切换与重做直接销毁草稿，无确认 | [study-workspace.tsx:743-748](../../apps/web/components/study-workspace.tsx#L743)、[:530-553](../../apps/web/components/study-workspace.tsx#L530)；对比 coach 动作有保护（[coach-actions.ts:60-67](../../apps/web/lib/coach-actions.ts#L60)） | UI 自己的按钮绕过了已建好的草稿保护 |
| F-25 | `submitAnswer` 未清除上次错误 | [study-workspace.tsx:436-466](../../apps/web/components/study-workspace.tsx#L436) 开头缺 `setError("")`，对比 [:401,472,534,758](../../apps/web/components/study-workspace.tsx#L401) 都有 | 上次失败横幅在本次成功后仍挂着 |

### 移动端

| 编号 | 问题 | 证据 |
| --- | --- | --- |
| F-26 | 日历在手机上不可读 | [styles.css:6752](../../apps/web/app/styles.css#L6752) 固定 7 列；640px 断点无日历覆盖规则。360px 屏每格约 43px，减 padding 后 27px，事件字号 9px + `nowrap` + 省略号，只能显示一个字符 |
| F-27 | 资料页空状态文案假设桌面 | [i18n.ts:141](../../apps/web/lib/i18n.ts#L141) "还没有资料，**拖入文件**即可…"；英文版 [:329](../../apps/web/lib/i18n.ts#L329) 同样。手机无法拖拽，这是新用户在资料页看到的第一句话 |
| F-28 | 卡片操作按钮 30×30，低于 44px 触控标准且与全卡点击区重叠 | [styles.css:2758-2760](../../apps/web/app/styles.css#L2758) 绝对定位于卡片右下（[:2750-2756](../../apps/web/app/styles.css#L2750)）；`.material-actions` 无尺寸下限（[:4752-4755](../../apps/web/app/styles.css#L4752)） |
| F-29 | hover 是唯一可供性提示 | [styles.css:2770](../../apps/web/app/styles.css#L2770)、[:6757](../../apps/web/app/styles.css#L6757)、[:4256](../../apps/web/app/styles.css#L4256) 无 `:focus-visible` / `@media (hover: none)` 分支 |
| F-30 | `sessionStorage` 的会话无法在独立标签页间可靠接力 | [session.ts:6](../../apps/web/lib/session.ts#L6) 及 [study-workspace.tsx:203,230,247](../../apps/web/components/study-workspace.tsx#L203) | 新标签页可能回到登录页；但直接迁到 `localStorage` 会延长 bearer token 暴露时间，应优先做同源标签页安全接力，长期持久登录另行采用 HttpOnly refresh/session cookie |

---

## P1 · 功能缺口（该补）

| 编号 | 缺口 | 证据 / 依据 |
| --- | --- | --- |
| G-01 | 收藏题浏览入口（错题本） | 后端接口、UI 代码、i18n 全都有，只差挂载。见 F-05 |
| G-02 | 判分后显示掌握度 前→后 | [learning-session-canvas.tsx:355-403](../../apps/web/components/learning-session-canvas.tsx#L355) 只有分数；团队自己列为 P0（[05-roadmap.md](../product/05-roadmap.md)），称其为 Aha 时刻核心 |
| G-03 | 考试倒计时 | i18n 有 `daysLeft`（[i18n.ts:67,255](../../apps/web/lib/i18n.ts#L67)）但**全前端零引用**；`exam_at` 只出现在计划设置编辑框 |
| G-04 | 复习队列搬到今日页 | `ReviewQueue` 仅挂在 progress（[study-workspace.tsx:1184-1188](../../apps/web/components/study-workspace.tsx#L1184)）；今日页只在判分后显示一个只读日期 |
| G-05 | 日历区分复习/学习类型 | [schedule-calendar.tsx:111,131](../../apps/web/components/schedule-calendar.tsx#L111) 只渲染 topic，不显示 activity；判分自动插入的 review 场次混在里面无法辨认 |
| G-06 | 学习报告卡（时间窗口聚合） | 全前端无 `week` / `本周` / `streak`；`Progress.attempt_count`、`diagnostic_count`（[types.ts:86-87](../../apps/web/lib/types.ts#L86)）后端一直返回、前端从未渲染 |
| G-07 | reflect 阶段缺三个出口 | 无"看进步"入口、不能重做本题、无法收藏（[learning-session-canvas.tsx:326-336](../../apps/web/components/learning-session-canvas.tsx#L326) 的收藏按钮只在 practice 分支内） |

---

## P2 · 赛后清理

| 编号 | 问题 | 证据 |
| --- | --- | --- |
| F-31 | `review.py` 完整 SM-2 引擎从未被调用 | [review.py:52-89](../../src/refineq/learning/review.py#L52) 写了 AGAIN→10min / HARD×1.2 / GOOD×2 / EASY×3、streak、lapses、`limit=20`；全仓引用只有 `tests/unit/learning/test_review.py`。主流程用的是 [service.py:996](../../src/refineq/learning/service.py#L996) 一行 `timedelta(days=3 if is_correct else 1)`。前端无 rating 输入口——这是它接不上的直接原因。**要么接上要么删掉**，留着会被静态评审判为演示用假实现 |
| F-32 | 复习会话按 attempt_id 去重，队列会无限膨胀 | [service.py:1000](../../src/refineq/learning/service.py#L1000) 每次作答生成一条，非按 topic 去重；[service.py:1158-1180](../../src/refineq/learning/service.py#L1158) 无 limit。`review.py:84` 的 `limit=20` 正是为此写的 |
| F-33 | 路由理由 7 秒自毁且 `routing_summary` 永不渲染 | [study-workspace.tsx:300-308](../../apps/web/components/study-workspace.tsx#L300) 定时清除；持久化的 `routing_summary`（[workspaces/models.py:26](../../src/refineq/workspaces/models.py#L26)）只存在于 [types.ts:32](../../apps/web/lib/types.ts#L32) 的类型里，无组件渲染 |
| F-34 | 题目 `explanation` 从不下发前端 | AI 生成并存入 grading blob（[intelligence.py:33](../../src/refineq/learning/intelligence.py#L33)、[service.py:715](../../src/refineq/learning/service.py#L715)），但 `QuestionResponse` 不含此字段 |
| F-35 | `agent-panel` 丢弃动作提案却照付模型调用 | [agent-panel.tsx:153-161](../../apps/web/components/agent-panel.tsx#L153) 只取 message/citations/sources，[:128](../../apps/web/components/agent-panel.tsx#L128) 照样发 `turn_id` → 每轮白白付一次意图抽取 |
| F-36 | `coach-actions` 的 `historical` 分支是死路径 | [coach-actions.ts:51-58](../../apps/web/lib/coach-actions.ts#L51)；全仓 `historical: true` 只出现在 [tests/coach-actions.test.ts:102](../../apps/web/tests/coach-actions.test.ts#L102)，UI 从不传该参数 |
| F-37 | 首页↔空间切换整体重挂载 + 双倍 snapshot 请求 | [page.tsx:5](../../apps/web/app/page.tsx#L5) 与 [learning-route.tsx:13-18](../../apps/web/components/learning-route.tsx#L13) 是两棵树；`resolveIntent` 已拉到的 snapshot 被丢弃，新实例重新串行拉取 |
| F-38 | 空计划时 path / calendar 页近乎空白 | `PlanSettings` 被 `plan && progress` 门控（[study-workspace.tsx:1133](../../apps/web/components/study-workspace.tsx#L1133)）；[schedule-calendar.tsx:83](../../apps/web/components/schedule-calendar.tsx#L83) 早于 toolbar return |
| F-39 | `progress-insights` 空状态无卡片外壳 | [progress-insights.tsx:27-29](../../apps/web/components/progress-insights.tsx#L27) 裸 `empty-note`，与同页其他卡片视觉不一致 |
| F-40 | `loading.tsx` 文案与路由不匹配 | [loading.tsx:23-24](../../apps/web/app/loading.tsx#L23) "把你的学习进度接回来"在跳转 `/account`、`/admin` 时同样显示 |

---

## Agent 性评估（不构成缺陷，但影响评分叙事）

**已做扎实的部分：** 教练动作实现了三个（换题/改期/收藏），采用提案 + 客户端执行；`action_id` 用 blake2b 派生保证幂等（[actions.py:175-177](../../src/refineq/agent/actions.py#L175)）；破坏性操作在有草稿时要确认（[coach-actions.ts:60-67](../../apps/web/lib/coach-actions.ts#L60)）；13 种带候选清单的结构化拒绝；AI 路由结果做 ID 白名单校验（[intelligence.py:69-75](../../src/refineq/workspaces/intelligence.py#L69)）；系统提示词禁止模型宣称动作已完成。

**评委容易打的点：**

1. 三个动作都是已有按钮的自然语言别名。"去掉聊天框，这个产品少了什么功能"——答案是零。
2. 意图抽取只吃当轮消息（[agent/service.py:421-424](../../src/refineq/agent/service.py#L421)），不带历史、不带学习状态。用户说"那把它改简单点"，"它"指什么模型无从判断。
3. 一轮最多一个动作，无多步规划、无自主发起、无"我注意到你三天没练"这类主动行为。
4. 所有决策沉默：选哪个主题出题、难度为什么升降、复习为什么排这天、计划为什么这样排——代码里全有逻辑，界面上一句解释都没有。唯一会解释的路由理由 7 秒后消失（F-33）。
5. 动作执行在客户端，证据台账只记作答 attempt，不记录"Agent 替我改了计划"，拿不出服务端凭据。

**建议的叙事对策**（不改代码）：路演明确演示"同一句话在不同历史下路由到不同空间"，以及动作被拒时的结构化解释——这两处是最能证明 Agent 在做判断的现场素材。

# RefineQ 当前开发交接文档

## 1. 工作区信息

- 项目路径：`/Users/chengyuanwen/Desktop/refineQ/RefineQ`
- 当前开发分支：`codex/material-analysis`
- 当前代码保存在本地，尚未统一 commit 或 push。
- 工作区包含大量历史修改，不要执行 `git reset --hard` 或 `git checkout --`。
- 不要删除未跟踪目录 `output/` 和 `tmp/`。

## 2. 项目定位与架构

RefineQ 是面向考试和系统学习场景的个人学习 Agent。

主要目录：

- `src/refineq/`：Python 领域逻辑、FastAPI、Agent、RAG、计划、掌握度和存储。
- `apps/web/`：Next.js 前端。
- `tests/`：单元、集成、契约和部署测试。
- `infra/`：容器、Compose 和反向代理配置。
- `docs/`：架构、设计和运维文档。

当前目标学习闭环：

```text
用户目标
→ 上传资料
→ 分析章节和知识点
→ 生成学习计划和日历
→ 每日学习 Session
→ 出题与评分
→ 保存学习证据
→ 更新掌握度
→ 调整后续题目和计划
```

## 3. 已完成的主要功能

### 3.1 总资料库与学习空间资料

- 总资料库可以保存不同学习空间的资料。
- 学习空间可以上传新资料，也可以从总资料库选择已有资料。
- 同一资料库中禁止出现同名文件。
- 重名时返回明确提示。
- 资料列表布局和操作入口已经调整。
- 上传后可以分析资料类型、章节和知识点。
- 支持教材、讲义、试卷、作业和练习题等资料类型。

### 3.2 资料分析与学习计划

- 上传资料后可以分析知识点。
- 用户确认知识点后生成学习计划。
- 知识点可以分配到每天的日程。
- 日历和计划列表保持同步。
- 用户可以编辑日程日期、时间、时长和知识点。
- 日历中修改知识点后，“今日学习”同步更新。
- 今日更换知识点后，计划和日历同步。
- 新学习空间不再自动生成无意义的七天计划。
- 用户未明确提供时间约束时，计划和日程保持空白。
- 用户输入考试日期、每日时长和开始时间后才生成对应计划。
- 新学习空间默认掌握度已从 20% 改为 0%。

### 3.3 日历

- 独立日历页面。
- 月视图和当天 24 小时时间线。
- 用户可以添加和编辑日程。
- AI 生成的日程会直接进入日历。
- 支持一键清空计划。
- 支持从日历开始学习任务。
- 支持编辑日程知识点，并同步到 Today 页面。

### 3.4 学习空间管理

- 学习空间右侧三点菜单。
- 支持删除学习空间。
- 删除前显示确认弹窗。
- 侧边栏、最近学习空间和日程入口已经调整。

### 3.5 Session 页面简化

旧页面同时展示概念学习、案例拆解、项目实战和模拟考试，信息密度过高。现在前端统一为四步：

```text
1. 快速回顾
2. 今天学习
3. 练一练
4. 总结复盘
```

核心原则：

> Daily Plan 决定今天学什么，Agent 决定怎么教。

### 3.6 快速回顾

- 只读取昨天本地日期内产生的学习证据。
- 支持昨天的答题、复习和自我解释记录。
- 显示昨天真正学习过的知识点。
- 优先回顾昨天记录的薄弱点和错误。
- 如果昨天没有学习记录：
  - “快速回顾”显示“今天跳过”。
  - 自动进入“今天学习”。
  - 回顾时间重新分配给后续阶段。
- 上传资料本身不会被误认为学习记录。

主要代码：

```text
apps/web/lib/learning-session.ts
apps/web/components/learning-session-canvas.tsx
```

### 3.7 今天学习

- 从 Daily Plan 获取今日知识点。
- 从上传资料中检索相关内容。
- 将资料片段整理成更容易阅读的要点列表。
- 支持展开查看资料原文。
- 保留资料引用。
- 支持 Markdown 和 KaTeX 数学公式。

新增前端依赖：

```text
react-markdown
remark-gfm
remark-math
rehype-katex
katex
```

主要文件：

```text
apps/web/components/rich-text.tsx
apps/web/components/learning-session-canvas.tsx
```

### 3.8 练一练

后端支持：

- 根据当前知识点出题。
- 优先检索 Past Exam、Assignment 和 Practice Questions 等资料。
- 没有合适原题时由模型生成。
- 模型失败时使用确定性备用题。
- 评分并记录 strengths、gaps 和 misconceptions。
- 更新 BKT 掌握度。
- 更新难度状态。
- 保存学习证据。

难度规则：

```text
初始难度：2/5
两道独立题连续答对：升一级
两道独立题连续答错：降一级
```

页面现在显示：

- 当前题难度。
- 下一题预计难度。
- 下一题预计耗时。

### 3.9 Agent

- Session 右侧 Agent 默认展开。
- 不再要求用户先点击“完整对话历史”才能发现 Agent。
- 支持“给我一点提示”“换种方式解释”“回看相关内容”和“为什么问这道题”。
- Agent 输出数学公式支持 KaTeX。
- 保留完整对话、历史和资料引用。
- Agent 配置不可用时显示管理员入口或状态说明。

### 3.10 时间感知自适应 Session

实现参考文档：

```text
/Users/chengyuanwen/Downloads/RefineQ_Time_Aware_Adaptive_Session_Codex.md
```

已经完成第一版：

- 根据 Session 总时长动态分配四个阶段。
- 不再固定为 `5/10/20/10` 分钟。
- 页面显示剩余约多少分钟。
- 提交答案时向后端发送：
  - `remaining_minutes`
  - `summary_reserve_minutes`
- 后端结合当前掌握度、题目难度、知识点顺序和剩余时间返回下一步决策。

决策类型：

```text
continue_topic  继续当前知识点
next_topic      进入下一个知识点
summary         进入总结复盘
```

当前掌握度目标暂定为 75%。

时间不足条件：

```text
剩余时间 < 下一题预计时间 + 总结预留时间
→ 不开始新题
→ 进入总结复盘
```

主要文件：

```text
src/refineq/learning/session_adaptation.py
src/refineq/learning/service.py
apps/web/lib/learning-session.ts
apps/web/lib/types.ts
apps/web/lib/api.ts
apps/web/components/learning-session-canvas.tsx
apps/web/components/study-workspace.tsx
```

## 4. 当前最高优先级未解决问题

用户完成第一道题后点击“继续巩固”，下一题仍可能生成失败，而且可能出现重复题。

当前表现：

- 页面顶部显示“操作没有完成，请稍后重试”。
- 当前题评分和反馈正常。
- 点击“继续巩固”不能稳定进入下一题。
- 即使请求成功，题目文本也可能与上一题相同或高度相似。

### 4.1 已经尝试的修复

前端原来对“继续巩固”发送：

```ts
replace: true
```

现已改成：

```ts
replace: result ? false : true
```

设计意图：

- 已评分后的“继续巩固”创建一道新题，不替换 pending question。
- 用户明确点击“换一个任务”时才使用 `replace=true`。

用户实际测试后问题仍然存在，因此不能认为已经解决。

### 4.2 当前调查结论

后端本身支持连续出题：

```python
selected_difficulty = DifficultyState(...).level
generate_question(...)
```

模型请求失败时还会调用：

```python
fallback_question(...)
```

所以问题不是简单的“模型不能生成下一题”。

可能原因包括：

1. 下一题生成期间发生学习状态版本冲突。
2. `questionRequestIdRef` 在失败后没有清理，重试复用旧请求 ID。
3. API 请求成功，但恢复轮询读取到上一道题。
4. 题目成功返回后，被前端 practice generation 版本判断拒绝应用。
5. 模型没有收到最近题目列表，因此生成重复题。
6. `fallback_question()` 每种模式只有一个固定模板，模型降级时必然重复。
7. 未知 API 错误被前端统一隐藏成“操作没有完成”。

## 5. 下一步建议

### 5.1 显示真实错误

下一题失败时应展示或记录：

- HTTP status。
- API error code。
- 后端返回的安全错误信息。

当前文件：

```text
apps/web/lib/error-messages.ts
```

目前未知错误只返回：

```text
操作没有完成，请稍后重试。
```

### 5.2 修复 request ID 生命周期

重点检查：

```text
apps/web/components/study-workspace.tsx
questionRequestIdRef.current
```

当前主要在生成成功后清理。失败后可能保留旧 request ID，导致重试返回旧题或重复题。

建议：

- 为每次明确的“继续巩固”创建新 request ID。
- 非可恢复失败后清除旧 request ID。
- 只有网络超时恢复期间才保留同一个 request ID。

### 5.3 后端增加题目去重

当前模型 prompt 只收到：

```text
topic
mastery
difficulty
prior_feedback
materials
```

应该增加最近题面：

```text
recent_question_prompts
```

并明确要求：

```text
Do not repeat or paraphrase any previous question.
Test a different aspect, example, representation, or application.
```

生成后还应进行归一化相似度检查。过度相似时：

- 重试一次模型；或
- 改用不同的 fallback 模板。

相关文件：

```text
src/refineq/learning/intelligence.py
src/refineq/learning/service.py
```

### 5.4 扩展 fallback 题目模板

当前 `fallback_question()` 每种学习模式基本只有一个固定模板，模型失败时会重复。

建议增加：

```text
definition
principle
worked example
error diagnosis
application
transfer
comparison
```

可以使用：

```text
question_sequence % template_count
```

选择不同模板。

### 5.5 增加真实连续题测试

后端已有基础测试：

```text
生成第一题
→ 提交答案
→ 请求第二题
→ 第二题 ID 不同
→ 第二题仍有材料依据
```

该测试通过，但还未覆盖：

- 模型超时后的恢复。
- request ID 重用。
- 重复题面检测。
- 前端点击“继续巩固”的完整链路。

下一步应增加 Playwright 或组件集成测试。

## 6. 最近测试状态

最近稳定状态：

```text
前端测试：203 passed
ESLint：passed
Next.js production build：passed
```

后端针对性测试：

```text
Session adaptation：passed
Workspace journey：passed
连续生成第二题基础测试：passed
```

注意：自动测试虽然通过，但用户实际浏览器中的“继续巩固”仍然失败，应以真实浏览器结果为准。

## 7. 本地运行

### 7.1 后端

```bash
cd /Users/chengyuanwen/Desktop/refineQ/RefineQ
source .venv/bin/activate
uvicorn refineq.api.app:create_app --factory --reload --host 127.0.0.1 --port 8000
```

### 7.2 前端

```bash
cd /Users/chengyuanwen/Desktop/refineQ/RefineQ/apps/web
npm run dev
```

默认访问：

```text
http://127.0.0.1:3000
```

## 8. 测试命令

### 8.1 后端

```bash
cd /Users/chengyuanwen/Desktop/refineQ/RefineQ
source .venv/bin/activate
ruff check src tests
pytest -q
```

### 8.2 前端

```bash
cd /Users/chengyuanwen/Desktop/refineQ/RefineQ/apps/web
npm test
npm run lint
npm run build
```

运行 `npm run build` 后，Next.js 可能修改：

```text
apps/web/next-env.d.ts
```

本地期望内容为：

```ts
import "./.next/dev/types/routes.d.ts";
import "./.next/dev/types/root-params.d.ts";
```

## 9. Git 注意事项

- 当前存在大量未提交修改。
- 不要执行破坏性 reset。
- 不要覆盖队友或用户已有修改。
- 不要删除 `output/` 和 `tmp/`。
- 暂时不要直接合并或 push。
- 先解决“继续巩固生成下一题”和重复题问题，再进行真实浏览器验证。
- 稳定后再 commit、push，并发起 PR 合并到 main。

## 10. 新窗口建议提示词

```text
请继续处理 /Users/chengyuanwen/Desktop/refineQ/RefineQ 当前
codex/material-analysis 分支。先阅读仓库中的 AGENTS.md 和
docs/RefineQ_Current_Development_Handoff.md。

当前最高优先级 Bug 是：用户完成题目后点击“继续巩固”，下一题生成失败且可能重复。
不要 reset 或覆盖现有未提交修改，不要删除 output/ 和 tmp/。
请先查出真实 API 错误，再修复 request ID 恢复、模型/备用题去重，并使用真实连续题流程测试验证。
```

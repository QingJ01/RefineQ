# Calm Learning Shell Implementation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将 RefineQ 全部前端页面重构为豆包式的极简个人学习应用壳，同时保留现有业务行为和测试契约。

**Architecture:** 保持单页 `StudyWorkspace` 状态机和现有 API 不变，通过语义化调整组件结构、统一 Lucide 导航图标，并重写全局样式系统完成视觉重构。组件测试负责锁定新的页面语义，Playwright 负责验证完整学习旅程和响应式页面。

**Tech Stack:** Next.js 16 App Router、React 19、TypeScript、全局 CSS、Lucide React、Vitest、Playwright。

---

### Task 1: 锁定新应用壳语义

**Files:**
- Modify: `apps/web/tests/components.test.tsx`
- Modify: `apps/web/components/auth-panel.tsx`
- Modify: `apps/web/components/learning-home.tsx`

**Steps:**

1. 添加断言：登录页包含 `RefineQ` 应用标识和简洁欢迎区；学习首页包含 composer、最近空间列表语义和自动路由说明。
2. 运行 `npm test -- tests/components.test.tsx`，确认新断言因结构缺失而失败。
3. 调整登录页和学习首页 JSX，加入应用标识、清晰标题区、输入工具栏与语义类名，保留所有交互和 `data-testid`。
4. 再次运行组件测试并确认通过。

### Task 2: 重构学习工作区应用壳

**Files:**
- Modify: `apps/web/tests/components.test.tsx`
- Modify: `apps/web/components/study-workspace.tsx`

**Steps:**

1. 为工作区增加可静态测试的侧栏导航数据/标记断言，覆盖今日学习、资料、证据和 Agent。
2. 运行定向测试，确认失败原因是新壳结构尚不存在。
3. 将顶部栏、dossier rail 和编号横向导航重组为左侧侧栏、工作区头部、学习统计条和主内容区；状态逻辑不变。
4. 运行组件测试并确认通过。

### Task 3: 统一功能内容组件

**Files:**
- Modify: `apps/web/components/plan-timeline.tsx`
- Modify: `apps/web/components/practice-card.tsx`
- Modify: `apps/web/components/material-dropzone.tsx`
- Modify: `apps/web/components/evidence-ledger.tsx`
- Modify: `apps/web/components/agent-panel.tsx`

**Steps:**

1. 增加组件测试断言，锁定计划列表、练习状态、资料上传区、证据时间线和对话 composer 的语义标记。
2. 运行测试并确认断言失败。
3. 统一卡片标题、按钮、空状态、列表行和聊天消息结构；保留现有数据映射和业务事件。
4. 运行组件测试并确认通过。

### Task 4: 重写视觉系统与响应式布局

**Files:**
- Modify: `apps/web/app/styles.css`
- Modify: `apps/web/app/layout.tsx`

**Steps:**

1. 更新元数据字符并只保留 Manrope 字体导入。
2. 用新的颜色、排版、间距、圆角、侧栏、composer、卡片、状态与移动端规则替换旧编辑风格。
3. 运行 `npm run lint` 和 `npm run build`，修复所有样式关联的类型或构建问题。
4. 在 1440×1000 与 390×844 视口截图检查登录页和完整学习旅程，修正溢出、对比度和触控尺寸。

### Task 5: 项目级验证

**Files:**
- Verify: `apps/web/tests/components.test.tsx`
- Verify: `apps/web/tests/e2e/learning-journey.spec.ts`

**Steps:**

1. 运行 `npm test`，预期全部 Vitest 用例通过。
2. 运行 `npm run lint`，预期 0 error。
3. 运行 `npm run build`，预期 Next.js 生产构建成功。
4. 运行 `npm run test:e2e`，预期完整学习旅程通过。
5. 检查 `git diff --check`、`git status --short` 和最终桌面/移动截图。

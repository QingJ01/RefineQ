# Consumer Brand Polish Implementation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将确认的 A 方向 Logo 全局替换到 RefineQ，并完成字号、边框、圆角和长计划呈现的第二轮精修。

**Architecture:** 新增无依赖的 React SVG 品牌组件和 Next.js `app/icon.svg`，由现有页面组合使用；视觉细节继续集中在全局 CSS。学习计划组件仅增加本地展开状态，不改变计划数据和 API。

**Tech Stack:** Next.js 16、React 19、TypeScript、SVG、全局 CSS、Vitest、Playwright。

---

### Task 1: 品牌组件与全局替换

**Files:**
- Create: `apps/web/components/brand.tsx`
- Create: `apps/web/app/icon.svg`
- Modify: `apps/web/tests/components.test.tsx`
- Modify: `apps/web/components/auth-panel.tsx`
- Modify: `apps/web/components/learning-home.tsx`
- Modify: `apps/web/components/study-workspace.tsx`

**Steps:**

1. 添加失败测试，断言 `BrandMark` 包含折页、进步圆点和可访问标题，并断言登录页不再输出旧字母标。
2. 运行定向组件测试并确认失败。
3. 实现 SVG 品牌组件和 favicon，替换登录、首页、工作区与加载状态的旧标识。
4. 运行组件测试并确认通过。

### Task 2: 长学习计划折叠

**Files:**
- Modify: `apps/web/tests/components.test.tsx`
- Modify: `apps/web/components/plan-timeline.tsx`
- Modify: `apps/web/lib/i18n.ts`

**Steps:**

1. 添加一个包含 10 个节点的失败测试，断言初始只渲染 7 个并提供展开按钮。
2. 运行测试并确认失败。
3. 为 `PlanTimeline` 增加本地展开状态与中英文按钮文案。
4. 运行组件测试并确认通过。

### Task 3: 全局视觉精修

**Files:**
- Modify: `apps/web/app/styles.css`

**Steps:**

1. 调整品牌色、字号、圆角、边框和阴影变量。
2. 删除内容卡、进度条和模型设置区的重复描边，保留输入与交互边界。
3. 增加 Logo 尺寸规则、折叠按钮以及触控按下状态。
4. 检查 1440×1000 和 390×844 的登录、首页、工作区与 Agent 页面。

### Task 4: 项目级验证与提交

**Files:**
- Verify: `apps/web/tests/components.test.tsx`
- Verify: `apps/web/tests/e2e/learning-journey.spec.ts`

**Steps:**

1. 运行 `npm test`、`npm run lint` 和 `npm run build`。
2. 运行 `npm run test:e2e`。
3. 运行后端测试与 Ruff，确认全仓库未受影响。
4. 检查视觉截图、`git diff --check`、提交身份和工作区状态后提交。

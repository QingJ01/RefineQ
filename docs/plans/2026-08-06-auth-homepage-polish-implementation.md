# Auth Homepage Polish Implementation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 放大登录首页的核心说明，并通过一条轻量学习记忆轨迹提升首屏品牌层次。

**Architecture:** 保持现有 `AuthPanel` 结构和 API 行为，仅增加语义化展示节点、翻译键与局部 CSS。所有变化限定在登录首页，不改动认证数据流。

**Tech Stack:** Next.js 16、React 19、TypeScript、Lucide React、全局 CSS、Vitest、Playwright。

---

### Task 1: 定义首页层次契约

**Files:**
- Modify: `apps/web/tests/components.test.tsx`
- Modify: `apps/web/tests/contracts.test.ts`

1. 先添加失败测试，要求登录首页包含四个学习轨迹节点。
2. 添加 CSS 契约，要求主说明为 18px、卡内说明为 13px。
3. 运行定向测试，确认因结构与样式尚未实现而失败。

### Task 2: 实现学习记忆轨迹与字号调整

**Files:**
- Modify: `apps/web/components/auth-panel.tsx`
- Modify: `apps/web/lib/i18n.ts`
- Modify: `apps/web/app/styles.css`

1. 增加四个中英文轨迹标签并替换旧胶囊。
2. 放大两处说明文字，加入点阵背景和轨迹节点样式。
3. 运行定向测试并确认通过。

### Task 3: 项目验证与提交

**Files:**
- Verify: `apps/web/tests/components.test.tsx`
- Verify: `apps/web/tests/contracts.test.ts`
- Verify: `apps/web/tests/e2e/learning-journey.spec.ts`

1. 运行前端测试、Lint、Build 与端到端旅程。
2. 截图检查 1440px 与 390px 登录首页。
3. 运行 `git diff --check`，确认提交身份后创建本地提交。

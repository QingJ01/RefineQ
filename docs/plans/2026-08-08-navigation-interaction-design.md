# 导航与交互逻辑 · 对抗审查与整改方案

> 审查日期：2026-08-08 · 基线：`5a0991f`
> 审查方式：只读代码审查 + 真实浏览器往返实测（生产构建）+ 侧边栏链接全量 dump
> 已完成：`5a0991f`（管理/账户区域不再叠加学习者空间列表；当前空间退出「最近使用」；当前页只标记一次）

## 验证基线

| 关卡 | 结果 |
| --- | --- |
| 前端 vitest | 166 passed ✅ |
| ESLint | 通过 ✅ |
| 生产构建 | 通过 ✅ |

生产构建实测的跨区域往返（**dev 下看到的请求翻倍是 StrictMode 假象，生产没有**）：

| 动作 | 请求数 |
| --- | --- |
| 工作区 → 账户 | 2 |
| 账户 → 回工作区 | 6（`auth/me` → `settings/model` → `workspaces` → `snapshot` → `agent/sessions` → `insights`） |
| 工作区 → 总日历 | 3 |
| 总日历 → 进空间 | 6 |
| 今日 → 进步 | 1 |
| 进步 → 今日 | 2 |

草稿跨区域往返完整保留、回到同一空间、零 pageerror。

---

## 一、架构前提

[learning-app-shell.tsx:10-19](../../apps/web/components/learning-app-shell.tsx#L10) 在 root layout 做分流：`/` 与 `/learn/**` 渲染**同一个** `<StudyWorkspace>`（状态保留），其余渲染 `{children}`。

所以"五个区域"实际只有两类：**StudyWorkspace 域**与**其余**。跨越这条边界即整棵子树卸载重挂载。这是有意设计（[contracts.test.ts:322-337](../../apps/web/tests/contracts.test.ts#L322) 断言了它），但**代价没有被处理**——下面 B 组的问题几乎全部源于此。

---

## 二、发现

### A 组 · 信息架构：概念重叠

#### A-1 两个日历是同一份数据的两套皮肤

后端 [calendar/service.py:67-100](../../src/refineq/calendar/service.py#L67) 遍历所有空间读 `progress.plan.sessions`；空间日历直接把 snapshot 的 `plan` 交给 `ScheduleCalendar`，后者 group 的也是 `plan.sessions`。**同一批记录。**

42 格月视图、右侧当日 agenda、「今天」按钮、日期 key 函数、活动标签、空态文案、CSS 类名——全部重复实现。实质差异只有两条且都藏得很深：跨空间 vs 单空间、只读 vs 可编辑（要点进某天再点某条才显形）。

侧边栏里两个入口**同图标同尺寸相隔十行**，中文只差一个「总」字，英文是 `Global calendar` vs `Calendar`。

还有一处功能倒置：只读的总日历显示完成状态徽章，**可编辑的空间日历不显示完成状态**。

#### A-2 「学习路径」与空间「日历」是同一个数组的两种渲染，能力被随意切开

| 操作 | 只在 path | 只在 calendar |
| --- | --- | --- |
| 开始这次学习 | ✅ | ✗ |
| 标记完成 / 重新打开 | ✅ | ✗ |
| 顺延一天 | ✅ | — |
| 改到任意时间 | ✗ | ✅ |
| 改时长 | ✗ | ✅ |

两边最终调同一个 `updatePlanSession`。**要改时间必须去日历，要标完成必须去路径，无任何提示。**

命名同时有硬冲突：[i18n.ts:32,38](../../apps/web/lib/i18n.ts#L32) 的 `path` 与 `plan` 中文都是「学习路径」，英文却分裂成 `Learning path` / `Study path`；日历里同一对象还有第四个名字「RefineQ 学习时间表」。

路径页的副标题写着"围绕能力目标组织每次学习，而不是堆积重复日程"，而它每一行都在印日期。

#### A-3 「今日」名不副实

[learning-session-canvas.tsx](../../apps/web/components/learning-session-canvas.tsx) 全文**只有一处** `planned_at`（取下次复习日期）。`nextSession` 是 `plan.sessions.find(status !== "completed")`——**第一个未完成场次，与日期无关**。三周后的场次也会顶着「今日学习」标题出现。收藏题目列表也无条件渲染、不按日期过滤。

更糟的是**三处文案在把用户推向这个页面做它做不到的事**：`plan-timeline.tsx:38`、`schedule-calendar.tsx:102`、`i18n.ts:126` 都写"先回到今日学习确认目标"，而目标编辑在 path 页的 `PlanSettings` 里。

#### A-4 「到期复习」语义倒置

同一个组件在两处渲染：今日页是**条件渲染**（`insightsLoading || due_reviews.length > 0`），进步页是**无条件渲染**。

结果：**没有到期复习时，今日隐藏它、进步显示一张空卡片**——正好与语义相反。而它的空态文案"当前没有到期复习，继续按计划学习即可"出现在一个叫「进步」的页面上本身就是错位。

#### A-5 「进步」页塞了四种时间尺度、两种职能

| 卡片 | 时间窗 | 职能 |
| --- | --- | --- |
| LearningReport | 滚动近 7 天（硬编码，界面无控件） | 只读 |
| ReviewQueue | 现在/已逾期 | 待办队列 |
| ProgressInsights | 当前状态 | 只读 + 发起练习 |
| EvidenceLedger | 全部历史 | 重做/备注/申诉 |

`EvidenceLedger` 自己有三套名字：i18n 叫「学习记录」、kicker 叫 `EVIDENCE`、legacy 路由段叫「证据」。它在进步页纯属历史合并残留——`learning-routes.ts` 至今仍把 `evidence` 重定向到 `progress`。

#### A-6 关键任务的点击成本

| 任务 | 实际路径 |
| --- | --- |
| 今天该学什么 | 今日页主 CTA 是**临时生成一道题**，不是启动计划场次；启动场次的按钮只在 path。真实 3 击，且今日页不提示 |
| 改考试日期 | 5 次交互，控件在自称"不是日程"的页面里，字段叫「目标日期」而今日页显示为「N 天后**考试**」 |
| 看错题 | ~4 次交互 + 长滚动。三个都像"错题"的竞争入口（收藏题目 / 到期复习 / 证据台账），**唯一写着"错题"二字的地方是个不可点的装饰标签** |
| 全局找资料 | **不存在**。搜索硬绑定当前空间，N 个空间要逐个试 |
| 跨空间看最弱项 | **不存在**。mastery 只在单空间 snapshot 里 |

---

### B 组 · 导航状态与时序

#### B-1 点「学习首页」会闪出假报错页

[study-workspace.tsx:1138-1160](../../apps/web/components/study-workspace.tsx#L1138) 的 `prepareHomeNavigation` 在 onClick 里**同步** `setWorkspace(null)`，但**不设 `homeBusy`**。Next App Router 的导航是 transition（低优先级），普通更新先 flush。于是路由提交前的窗口里命中 `1195` 分支，整屏渲染 **「暂时无法打开这个学习空间」** + 重试按钮。网络一慢就是几秒钟的假报错。

对比 `redirectUnavailableWorkspace` 和 `authenticated` 都记得先 `setHomeBusy(true)`——这里漏了。`returnHome` 和 WorkspaceSwitcher 的 `onAllSpaces` 同病。

#### B-2 资料上传在客户端导航时被静默 abort

`material-dropzone.tsx` 的 cleanup 里 `controllers.forEach(c => c.abort())`；`beforeunload` 只挡整页卸载，**挡不住客户端路由**。传大文件时点「总日历」→ 整棵树卸载 → 上传全 abort → [study-workspace.tsx:816](../../apps/web/components/study-workspace.tsx#L816) `if (isAbortError(caught)) return []` **静默吞掉，连错误横幅都没有**。

管理台对脏表单实现了 document 捕获阶段的点击拦截，说明作者知道要拦；materials 这条路径完全没拦。另外 `runGuardedPracticeAction` 这个草稿保护**没接到任何导航链接上**——带未交草稿点侧边栏任何链接，零确认。

#### B-3 跨区域往返丢失的状态

只有「学习首页」走 `prepareHomeNavigation`（会存快照），其余四类链接走 `prepareRouteNavigation`——**它不存快照**。

| 状态 | 去 /calendar 或 /account 再回来 |
| --- | --- |
| 草稿 | 侥幸保住（每次按键写 sessionStorage） |
| 当前题目 / 判分结果 | 丢，从服务端重拉 |
| `masteryBefore` | **永久丢失**，快照里也没有 → 回来后掌握度增量不显示 |
| `learningMode` | 丢，重新推断，可能与用户手选不一致 |
| Coach 对话 | 丢，`coachSessionId` 归零，服务端会话线程断掉 |

#### B-4 后退/前进与点击不对称

三个 `prepare*` 都是 `<Link onClick>`，**后退不触发**。于是「点侧边栏学习首页再点回来」是本地快照秒开，「用后退/前进走同一条路」必然整屏白 + 一次网络往返。

#### B-5 快照无 TTL、无版本，且漏字段

`saveWorkspaceSnapshot` 写的快照没有时间戳或版本，`consumeWorkspaceSnapshot` 只校验 id。可达路径：工作区 → 学习首页（存快照）→ 总日历 → 从总日历点该空间的任务 → 冷挂载**命中旧快照直接 apply，一个请求都不发**，且之后不 revalidate。

同时保存时**漏了 `topic_suggestions`**（类型里有），恢复时 `?? []` → **从本地快照恢复会静默清空资料页的 AI 主题建议**。

#### B-6 `saveWorkspaceSnapshot` 无 try/catch，可把应用点崩

它在 `<Link onClick>` 同步执行，快照含完整 `plan + evidence + materials + saved_questions`。资料多的空间容易撑爆 sessionStorage 配额；`QuotaExceededError` 抛出 → 后续 `setWorkspace(null)` 与 `router.push` 都不执行 → 异常冒到 React 事件处理 → 触发 `app/error.tsx` 错误边界。**"点学习首页把整个应用点崩"是可达的。**

---

### C 组 · 数据残留与一致性

#### C-1 登出不清答题草稿与路由提示

`logout()` 调 `clearWorkspaceSnapshots`（只扫 `refineq.workspace-snapshot:` 前缀）+ 内存态清理，**不清** `refineq.practice-draft:*` 与 `refineq.workspace-route-notice`。

后果一（隐私）：同一浏览器 tab 换账号登录后，**前一个用户的答案原文仍在 sessionStorage**。
后果二（诡异行为）：`route-notice` 无 TTL、整个 tab session 有效，登出重登后仍会复活，弹出"已为你切换空间"，且它的撤销按钮会把用户推去一个早已不相关的空间。

#### C-2 页内 401 在五个区域有三种表现

`lib/api.ts` **没有全局 401 拦截层**。挂载阶段五个区域都正确清会话并跳登录；但挂载之后：

| 区域 | 页内请求 401 |
| --- | --- |
| StudyWorkspace（出题/交卷/上传/改计划…全部） | 仅红色横幅，**会话不清、不跳转**，用户拿死 token 继续点 |
| Account | 变成面板内一行文字，与同文件挂载期行为矛盾 |
| Admin | 变成 `loadError` + 「重新加载」按钮 → **永远加载失败**，每点一次再发 2~4 个必死请求 |

---

### D 组 · 效率

#### D-1 冷挂载是 4 层串行瀑布

`Promise.all([getProfile, getModelSettings])` → 串行 `listWorkspaces` → 串行 `getWorkspaceSnapshot` → `getWorkspaceInsights`。无缓存层（无 SWR/react-query），`getProfile` 在五个区域每次挂载都打一遍。一次「工作区 → 总日历 → 工作区」往返里 `getProfile` ×3、`listWorkspaces` ×3 是纯重复。

#### D-2 切换语言触发请求风暴

`locale` 混进数据 effect 的 deps，只因为 catch 里用它做错误文案本地化。点一次「EN」：`/admin/operations` 重发 **4 个**管理请求，工作区重发 `insights`。这些接口返回体与 locale 无关。

#### D-3 管理台脏表单确认后走整页硬刷新

`window.location.assign(pendingHref)` 而非 `router.push` —— 浏览器级导航，整个 React 应用冷启动。

#### D-4 死 CSS

`5a0991f` 删除了 `.app-spaces-all` 元素与 `.app-recent-spaces > small`，对应 CSS 规则残留。

---

## 三、整改方案

### 第一层：信息架构（决定后面所有改动）

**核心决策：把「同一个对象的不同视图」合并，把「不同职能」分开。**

**IA-1 合并「学习路径」与空间「日历」为一个 section「计划」。**
同一份 `plan.sessions`，页内提供列表/日历两种视图切换，**两种视图共享全部操作**（开始、标记完成、顺延、改时间、改时长）。`learningSections` 从 5 项减为 4 项：`today / plan / materials / progress`。
一并消灭：能力被切开、`path`/`plan` 同名冲突、"不是日程却全是日期"的自相矛盾、以及侧边栏里两个日历图标相邻。

**IA-2 全局 `/calendar` 定位为「跨空间日程」。**
保留（它回答的是空间日历回答不了的问题），但：改名以消除与空间视图的歧义；换图标；**深链改为指向 `today` 而非 `calendar`**（现在跳过去是死胡同，因为空间日历没有"开始"按钮）；补上完成状态徽章的对称性。

**IA-3 「今日」要么真按日期过滤，要么改名。**
推荐：保留「今日」之名，但让它**真正消费计划**——`nextSession` 改为优先取今天的未完成场次，主 CTA 改为"开始今天的场次"（调 `startPlanSession`）而非临时出题；今天无场次时才回退到自由练习。同时修掉三处把用户指向这里"确认目标"的错误文案。

**IA-4 「到期复习」只留在今日，且常驻。**
今日页无条件渲染（含空态"今天没有到期复习"），进步页移除。这同时修好 A-4 的语义倒置。

**IA-5 「进步」瘦身，「学习记录」独立命名。**
进步页保留 LearningReport + ProgressInsights + ProgressTopicDetail（都是"我进步了多少"）。EvidenceLedger 统一叫「学习记录」，作为进步页的独立分区并给它一个页内锚点，或后续拆为独立 section。同时把"错题"这个用户真正会搜的词，落到一个可点的入口上。

### 第二层：可靠性（可独立于 IA 先做）

| 编号 | 改动 | 位置 |
| --- | --- | --- |
| R-1 | `prepareHomeNavigation` / `returnHome` / `onAllSpaces` 先 `setHomeBusy(true)`，消除假报错闪屏 | `study-workspace.tsx:1138` |
| R-2 | `saveWorkspaceSnapshot` 包 try/catch，配额溢出时降级为不存快照而非崩溃；快照补 `topic_suggestions` | `study-workspace.tsx:1148`、`workspace-snapshot-handoff.ts` |
| R-3 | 快照加时间戳，超过阈值（建议 5 分钟）视为过期走网络；或 apply 后后台 revalidate | `workspace-snapshot-handoff.ts` |
| R-4 | `logout()` 增加清理 `refineq.practice-draft:*` 与 `refineq.workspace-route-notice`；`route-notice` 加时间戳与 TTL | `study-workspace.tsx:1162` |
| R-5 | 上传进行中拦截客户端导航：复用管理台的 `guardNavigation` 模式，或在 abort 时给出可见提示而非静默吞掉 | `material-dropzone.tsx`、`study-workspace.tsx:816` |
| R-6 | `lib/api.ts` 增加全局 401 处理：统一清会话并跳登录，五区域行为一致 | `lib/api.ts` |
| R-7 | 把 `masteryBefore` 与 `learningMode` 纳入快照，跨区域往返不丢 | `study-workspace.tsx` |

### 第三层：效率（收益明确、风险低）

| 编号 | 改动 |
| --- | --- |
| E-1 | 把 `locale` 移出数据 effect 的 deps（错误文案改为渲染时本地化），消除切语言请求风暴 |
| E-2 | `getProfile` / `listWorkspaces` 做进程内短缓存（或提升到 shell 层只取一次），消除跨区域重复 |
| E-3 | 冷挂载瀑布并行化：`listWorkspaces` 与 `getProfile` 可并行；`insights` 可与 `snapshot` 并行 |
| E-4 | 管理台脏表单确认后改用 `router.push` 而非 `window.location.assign` |
| E-5 | 清理 `.app-spaces-all` 与 `.app-recent-spaces > small` 死 CSS |

---

## 四、执行顺序

**已完成：** 管理/账户不再叠加学习者导航（`5a0991f`），对应原六条建议中的 ①（当前空间退出最近使用）、②（删除「全部学习空间」）、以及管理侧的重复高亮。

**建议顺序：**

1. **R-1、R-4、R-2**——三个都是小改动，分别消除"点首页闪报错"、"登出泄漏草稿"、"点首页崩应用"。风险最低、感知最强。
2. **IA-4**（复习队列归位）+ **IA-2 深链修正**——两处一行级改动，直接修好语义倒置和死胡同。
3. **E-1、E-5**——纯清理。
4. **IA-1**（合并计划与日历）——这是最大的一块，动 `learningSections`、两个组件、i18n、测试与 E2E。建议单独一个提交，做完跑全量。
5. **IA-3**（今日真正消费计划）——依赖 IA-1 完成后的计划语义。
6. **IA-5、R-3、R-5、R-6、R-7、E-2、E-3、E-4**——按余力推进。

原建议 ③（区分两个日历）被 IA-1 + IA-2 取代；④（工作区在全局导航有落点）在 IA-1 把 section 减到 4 项后重新评估，可能不再必要；⑤（账户锚点移出 contextNavigation）并入 IA-5 一并处理；⑥（switcher 与最近使用二选一）已由 `5a0991f` 解决——「最近使用」在工作区里现在只剩其他空间，语义已经是"切到别的空间"。

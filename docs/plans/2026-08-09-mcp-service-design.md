# RefineQ MCP 服务设计

> 日期：2026-08-09 · 状态：设计待确认
> 目的：为初赛动态测评（占 50%）提供平台可直接调用的 Agent 接口，同时让 RefineQ 的学习闭环可被外部 Agent 复用
> 依据：[HACKATHON.md §6.1](../../HACKATHON.md)、后端 77 个端点的能力盘点

---

## 0. 前提核实（都已查证，不是假设）

**赛制原文是"或"不是"必须"。** §6.1：「平台会解析源码 ZIP，**或**使用选手直接提供的 MCP 接口」。MCP 是两条路径之一。但它仍值得做：平台若走 ZIP，要自己把项目跑起来才能验证"Agent 是否能够连通"；走 MCP 则是发一个请求。**风险面差一个量级。**

以下五条约束直接决定设计形状：

| # | 事实 | 证据 | 对设计的约束 |
| --- | --- | --- | --- |
| 1 | **没有任何机器凭据** | 只有 JWT，`identity/service.py:76` TTL = 12 小时，无 refresh、无 API key、无 service account | 提交出去的 MCP 地址不能依赖 12 小时 token；必须先解决凭据 |
| 2 | Token 会被三种情况提前失效 | `identity/service.py:779-788`：改密码、退出所有会话、账号删除 | 演示账号一旦改密，提交的 MCP 接口当场失效 |
| 3 | **限流按 IP 不按用户** | `api/limits.py:317-318,363` 写操作 240/分钟，key 是 `request.client.host` | MCP 服务作为单一出口，与该 IP 全部流量共享配额 |
| 4 | `snapshot` **有写副作用且体积不可控** | `workspaces/service.py:552-560` 写 journey event；响应含全量 evidence / materials / 含 chunk 全文的 sources | MCP 读工具不能直接转发 snapshot |
| 5 | 只有 `agent/chat` 硬依赖模型 | `agent/service.py:321` 抛 `ModelNotConfiguredError` → 409；出题、判分、路由、检索**都有确定性降级** | MCP 可在零模型环境下演示完整闭环 |

**工程成本另计**：仓库无 `mcp` 依赖，锁文件由 `uv pip compile --generate-hashes` 生成（1168 条哈希），**本机没有 uv**。加依赖必须先解决 uv，这是排期上的硬前置。

---

## 1. 定位：MCP 暴露什么

**不是把 77 个端点映射成 77 个工具。** 那正是工具设计的头号反模式——工具描述互相重叠会让调用方无法选择，且吃光上下文预算。

MCP 暴露的是**学习闭环这条产品主线**，不是 REST 资源：

```
说明目标 → 进入空间 → 上传资料 → 取得任务 → 作答 → 判分与证据 → 下一步
```

一条判断准则：**如果一个能力只有 RefineQ 的 Web 界面需要，它就不该进 MCP。** 归档空间、改密码、管理后台、备份、集成配置全部不暴露。

### 明确不暴露

| 不暴露 | 理由 |
| --- | --- |
| 全部 `/admin/*` | 跨 owner 的运维面，与学习闭环无关，且是最大的越权风险面 |
| `/auth/*` 写操作（改密、删号、退出所有会话） | 会让 MCP 自己的凭据失效；且账号生命周期不该由外部 Agent 驱动 |
| `/auth/export`、`/settings/model` | 前者是全量导出，后者是平台级 admin 配置 |
| 材料下载原始二进制 | MCP 传输大二进制无收益，且 chunk 检索已能提供依据 |
| `/projects/*` 遗留路由 | 只有 `POST`，无列表无删除，是历史遗留 |
| `snapshot` 原样转发 | 有写副作用 + 体积不可控（见前提 4） |

---

## 2. 工具集（9 个，命名空间 `refineq`）

数量控制在 10 以内。每个工具给出**做什么 / 何时用 / 入参 / 返回 / 错误**四段描述——工具描述就是提示词，不是文档。

### 2.1 状态读取（2 个）

**`refineq:list_learning_spaces`**

- **做什么**：列出学习者当前全部活跃学习空间，每个附带"下一步该做什么"。
- **何时用**：会话开始时、或需要知道"我在学什么/该学哪个"时。这是大多数会话的第一个调用。
- **入参**：`include_archived: bool = false`
- **返回**（每空间约 8 字段，无 chunk 全文）：
  ```
  spaces[]: { id, title, goal, exam_at?, days_left?, mastery_avg,
              material_count, next_action: { type, reason, minutes } }
  ```
- **错误**：`unauthorized`（凭据失效，附重新获取方式）

**`refineq:get_space_state`**

- **做什么**：读取单个空间的当前状态：目标、截止、掌握度分布、今日计划、资料统计、待答题、上次判分。
- **何时用**：确定要在哪个空间行动之后；不要为了"看看有什么"而对每个空间都调一次。
- **入参**：`space_id: str`、`detail: "concise" | "full" = "concise"`
- **返回**：`concise` 省略 evidence 与 sources 全文；`full` 追加最近 10 条学习记录摘要。**任何模式都不返回 chunk 原文**（要原文用 `search_materials`）。
- **实现要点**：**不得调用 `GET /snapshot`**（它写 journey event 且体积不可控）。走 `next-action` + `insights` 的投影，或新增只读投影方法。
- **错误**：`space_not_found`

### 2.2 闭环主线（5 个）

**`refineq:start_learning`** ← 这是产品的招牌能力

- **做什么**：把一句自然语言学习目标变成一个准备好的学习空间——识别学科、考试日期、每日时间，复用已有空间或新建，并生成到考试日的计划。
- **何时用**：学习者表达一个新的学习目标时。若目标明显对应已有空间，本工具会复用而不是重复创建。
- **入参**：`intent: str (1..2000)`、`timezone_offset_minutes: int = 0`
- **返回**：`{ action: "created"|"reused"|"switched", confidence, reason, space: {...}, next_action: {...}, mode: "ai"|"fallback" }`
- **降级**：模型不可用时走关键词路由，`mode="fallback"`，**不隐瞒**。
- **错误**：`invalid_learning_constraints`（附可接受的表述示例）、`workspace_quota`

**`refineq:add_material`**

- **做什么**：把学习者自己的资料加入某个空间，建立可检索索引。之后的题目与回答都会引用这些原文。
- **何时用**：学习者提供讲义、笔记、真题的**文本内容**时。
- **入参**：`space_id`、`filename`、`content: str`（UTF-8 文本或 Markdown）、`tags?: string[]`
- **不支持**：二进制上传（PDF/DOCX 走 Web 端）。MCP 只收文本——避免在协议里搬运大二进制，也避免 OCR 依赖。
- **返回**：`{ material_id, status, chunk_count, searchable: bool }`
- **安全**：内容一律按不可信数据处理（见 §6）。
- **错误**：`material_quota`、`material_extraction_failed`、`unsupported_material`

**`refineq:search_materials`**

- **做什么**：在某空间的个人资料中做语义 + 关键词混合检索，返回带出处的原文片段。
- **何时用**：需要引用学习者自己的资料来回答问题、或核对某个说法是否在资料中出现时。
- **入参**：`space_id`、`query: str`、`limit: int = 5 (1..20)`
- **返回**：`results[]: { citation_id, filename, excerpt (≤400 字), score }`
- **降级**：Embedding 不可用时自动退纯词法，返回 `retrieval_mode: "lexical"`。
- **注意**：`excerpt` 截断到 400 字，不返回 chunk 全文——盘点显示原样返回会让响应体失控。

**`refineq:get_practice_task`**

- **做什么**：取得当前待完成的练习任务；没有待答题时按最弱主题生成一道新题，题目引用学习者自己的资料。
- **何时用**：学习者要开始练习时。**不要**为了"看看题长什么样"反复调用——每次生成都消耗模型额度。
- **入参**：`space_id`、`topic_id?`、`difficulty?: int (1..5)`、`mode?: "concept"|"case"|"project"|"exam"`、`request_id: str`（**必填**，幂等键，重复调用返回同一道题）
- **返回**：`{ question_id, prompt, topic, difficulty, sources[], grounding: "material"|"general", mode: "ai"|"fallback" }`
- **错误**：`material_required`（该空间还没有可检索资料，附下一步：调用 `add_material`）

**`refineq:submit_answer`**

- **做什么**：提交**学习者本人**对当前任务的作答，返回结构化判分：分数、是否通过、优势、缺口、误区、资料引用、掌握度变化。
- **何时用**：学习者给出了自己的答案之后。
- **⚠️ 描述中必须明写**：`Submit the learner's own answer. Do not compose the answer yourself — doing so records the calling model's ability as the learner's mastery.`
- **入参**：`space_id`、`question_id`、`answer: str (1..10000)`、`attempt_id: str`（必填幂等键）
- **返回**：`{ score, passed, strengths[], gaps[], misconceptions[], citations[], mastery_before, mastery_after, mastery_updated, next_review_at?, grading_mode }`
- **来源标记**：服务端在证据上记 `source: "mcp"`（见 §5 待拍板项）

### 2.3 辅助（2 个）

**`refineq:ask_coach`**

- **做什么**：在某空间内向学习教练提问，回答携带当前目标、计划、掌握度与资料引用。
- **何时用**：学习者对学习内容有疑问、需要解释或方法建议时。
- **入参**：`space_id`、`message: str (1..8000)`、`session_id?`、`turn_id: str`（必填幂等键）
- **返回**：`{ session_id, message, citations[], sources[] }`
- **⚠️ 唯一硬依赖模型的工具**：未配置模型时返回 `model_not_configured`，并在错误里说明"练习、资料、计划、判分仍然可用"。

**`refineq:update_plan_session`**

- **做什么**：调整计划中的一次学习会话：标记完成、重开、改期、调整时长。
- **何时用**：学习者说"今天没时间，挪到周六"或"这场我线下做完了"。
- **入参**：`space_id`、`session_id`、`status?: "planned"|"completed"`、`planned_at?: ISO8601`（必须带时区）、`minutes?: int`
- **返回**：更新后的会话 + 该空间新的 `next_action`
- **错误**：`plan_session_not_found`、`invalid_timezone`（附要求）

### 2.4 为什么是这 9 个

| 判断 | 结论 |
| --- | --- |
| 覆盖闭环全部八步？ | 是：`start_learning`(1,2) → `add_material`(3) → 计划随空间生成(4) → `get_practice_task`(5) → `submit_answer`(6,7) → `list/get_state` 与 `next_action`(8) |
| 有无两个工具指向同一场景？ | 无。`get_space_state` 读状态、`search_materials` 读资料、`get_practice_task` 取任务，边界互斥 |
| 调用方能否只用描述判断该调哪个？ | 每个工具的"何时用"都给了触发条件，且 `list_learning_spaces` 被明确标为会话起点 |

---

## 3. 认证与部署

### 3.1 凭据（必须先解决的缺口）

现状：只有 12 小时 JWT，且改密即失效。**提交出去的 MCP 地址不能建立在它之上。**

**Phase 1（赛前，推荐）——服务账号绑定，不新增凭据类型：**

- MCP 端点在服务端绑定一个**专用评测账号**，凭据来自环境变量 `REFINEQ_MCP_ACCOUNT_EMAIL` / `REFINEQ_MCP_ACCOUNT_PASSWORD`；
- MCP 服务进程内自行 `login` 取 JWT、缓存、**401 时自动刷新**，调用方完全不接触凭据；
- 调用方凭 `REFINEQ_MCP_SHARED_SECRET`（请求头）访问该端点，不需要 RefineQ 账号。

优点：零 schema 变更、零新凭据类型、12 小时 TTL 问题在内部消化。
限制：MCP 面向**一个固定学习者身份**——对评测正合适，对多用户不适用。

**Phase 2（赛后）——按用户的 MCP 访问令牌：**

新增可撤销、可限定范围（`read` / `loop` / `full`）的长期令牌，用户在账号中心自助签发。这才是给真实用户用的形态。

### 3.2 传输与部署

| 场景 | 传输 | 说明 |
| --- | --- | --- |
| 平台远程调用（主路径） | **Streamable HTTP**，挂在 `/mcp` | 与主应用同进程，走 Caddy 反代；这是"提供 MCP 接口"最直接的形态 |
| 平台解析 ZIP 后本地跑 | **stdio** | `refineq-mcp` console script，同一套工具实现 |

**关键实现决策：MCP 服务与 FastAPI 同进程，直接调用应用服务层**（`workspace_service` / `learning_service` / `agent_service`），**不经过 HTTP 自调用**。理由：

- 复用全部既有不变量（owner 强制、幂等、事务边界、降级），不需要重新实现一遍；
- 避免多一跳网络与序列化；
- 避免被自己的 IP 限流打中（见 §3.3）。

新增模块 `src/refineq/mcp/`：

```
tools.py       工具定义与 JSON Schema
service.py     工具执行：参数校验 → 调用应用服务 → 投影为紧凑返回
projections.py 只读投影（替代 snapshot，无写副作用、有界体积）
auth.py        服务账号 token 缓存与刷新
server.py      Streamable HTTP + stdio 两种入口
```

### 3.3 限流

盘点显示写操作按 **IP** 限流 240/分钟（`api/limits.py:363`）。MCP 与主应用同进程且直接调服务层 → **不经过该中间件**，天然不受影响。

但要补一道自己的闸：MCP 侧按**服务账号**限流（建议写操作 60/分钟），防止调用方失控刷额度或刷模型费用。

---

## 4. 降级行为

盘点确认只有 `agent/chat` 硬依赖模型。因此**零模型环境下 MCP 仍能演示完整闭环**——这是相对多数参赛项目的优势，要在工具返回里明确标出而不是藏起来。

| 工具 | 无模型时 |
| --- | --- |
| `list_learning_spaces` / `get_space_state` | 完全可用（纯规则） |
| `start_learning` | 可用，关键词路由，`mode="fallback"` |
| `add_material` / `search_materials` | 可用；检索退纯词法，`retrieval_mode="lexical"` |
| `get_practice_task` | 可用，`mode="fallback"`；**仍带资料引用**（`intelligence.py:230-232`） |
| `submit_answer` | 可用，`grading_mode="fallback"` |
| `update_plan_session` | 完全可用 |
| `ask_coach` | **唯一不可用**，返回 `model_not_configured` 并说明其余能力仍可用 |

---

## 5. 待你拍板的两个决策

### 决策一：MCP 提交的作答是否计入掌握度

外部 Agent 可以替用户答题，服务端无法区分"用户口述、Agent 转达"和"Agent 自己编"。若计入，掌握度就变成"调用方模型有多强"，直接冲撞产品头号主张。

| 方案 | 优点 | 代价 |
| --- | --- | --- |
| **A. 计入，但记 `source:"mcp"` 并在证据台账显示**（推荐） | 闭环在 MCP 上可完整演示；不隐藏、不伪造，判断权交给看台账的人 | 台账里会出现掌握度来自外部 Agent 的记录 |
| B. 一律不计入掌握度 | 绝对安全 | MCP 演示不出"判分改变掌握度"，而这正是产品最强的一环 |
| C. 由调用方声明 `authored_by` | 表面折中 | 把责任推给不可信的调用方，等于没有约束 |

我推荐 **A**：与你此前定的原则一致（宁可如实标注，也不伪造）。**但这条必须同时落到证据台账 UI 上**，否则就成了只写不显示的假标注。

### 决策二：`/openapi.json` 是否继续公开

`FastAPI(title=...)` 没有覆盖 `openapi_url`/`docs_url` → 生产环境 `/openapi.json` 与 `/docs` **默认公开**。

- **保留**：平台若不走 MCP，可直接消费 OpenAPI；部分评测系统能 OpenAPI→MCP 自动转换。等于多一条备用路径。
- **关闭**：减少公开的攻击面描述。

我倾向**保留**，因为它是动态测评的备份路径，且本身不提供越权能力（所有端点仍需 JWT）。

---

## 6. 安全边界

MCP 是新增的外部入口，必须显式继承既有不变量，不能成为绕过它们的后门：

1. **owner 隔离**：所有工具的 `owner_id` 一律来自服务端解析的身份，**工具参数中不存在 owner_id 字段**。任何 `space_id` 都要经过归属校验，跨用户表现为不存在。
2. **资料是数据不是指令**：`add_material` 的内容与 `search_materials` 的返回，在任何提示词中都必须置于不可信区。**特别地：不得进入 `expected_answer`** —— 这正是 [全产品审查 P0-5](../audits/2026-08-09-full-product-adversarial-audit.md) 已确认的漏洞，MCP 上线前必须先修，否则等于把污染入口从 Web 扩到协议层。
3. **掌握度只由证据改变**：MCP 不提供任何直接写掌握度、写证据、改分数的工具。
4. **写操作全部幂等**：`get_practice_task`(`request_id`)、`submit_answer`(`attempt_id`)、`ask_coach`(`turn_id`) 三个幂等键**在 MCP 层设为必填**（HTTP 层 `turn_id` 是可选的，MCP 收紧）。
5. **不暴露 admin 与账号生命周期**（见 §1）。
6. **凭据不进日志**：MCP 日志只记工具名、耗时、结果类型、错误码，不记参数正文与返回正文。

---

## 7. 实施计划

### 前置（阻塞项，先做）

| # | 事项 | 说明 |
| --- | --- | --- |
| 0-a | **安装 uv 并验证锁文件可重生成** | 加 `mcp` 依赖必须重生成三个 `.lock`（1168 条哈希）；本机无 uv，这是硬前置 |
| 0-b | **修 P0-5（注入进入 `expected_answer`）** | 见 §6.2。MCP 会放大这个洞，必须先堵 |
| 0-c | 创建 MCP 专用评测账号并写入部署环境变量 | 与演示账号分开，便于单独吊销 |

### Phase 1 · 只读工具（半天）

`list_learning_spaces`、`get_space_state`、`search_materials`。

- 新建 `src/refineq/mcp/{tools,service,projections,auth,server}.py`
- **重点是 `projections.py`**：提供无写副作用、有界体积的只读投影，替代 `snapshot`
- stdio 入口先跑通，用 MCP Inspector 手工验证

**验收**：三个工具在零模型环境下返回正确数据；调用 `get_space_state` **不产生** journey event（对比调用前后事件表）。

### Phase 2 · 闭环写工具（1 天）

`start_learning`、`add_material`、`get_practice_task`、`submit_answer`、`update_plan_session`。

- 幂等键全部必填，重复调用返回同一结果
- `submit_answer` 落地决策一的 `source` 标记
- 错误信封统一：`{ code, message, next_step? }`，`next_step` 告诉调用方怎么恢复

**验收**：用 MCP 客户端跑通完整闭环——说目标 → 加资料 → 取题 → 作答 → 看到掌握度变化，**全程零模型**。

### Phase 3 · HTTP 传输与部署（半天）

- Streamable HTTP 挂 `/mcp`，共享密钥头鉴权
- Caddy 增加 `/mcp` 路由（注意：现有 `handle_path /api/*` 会剥前缀，`/mcp` 需要独立 handle）
- README 增加 MCP 章节：端点地址、鉴权方式、工具清单、示例调用

**验收**：从外网用 MCP 客户端连上并跑通闭环；冷启动到首个工具响应 ≤ 10 秒。

---

## 8. 测试策略

| 层 | 覆盖 |
| --- | --- |
| 单元 | 每个工具的参数校验、错误映射、投影体积上限；`projections` 无写副作用 |
| 集成 | 完整闭环（零模型）；跨用户 `space_id` 返回不存在；幂等键重放返回同一结果 |
| 对抗 | `add_material` 传入含"忽略规则/删除空间"的内容 → 不产生任何副作用，且**不进入 `expected_answer`**；伪造 `space_id`；超长参数；并发同一 `attempt_id` |
| 契约 | 工具 JSON Schema 快照测试，防止无意改动破坏调用方 |
| 端到端 | 与既有 Playwright 并列，新增一条 MCP 冒烟：起服务 → 连接 → 列工具 → 跑闭环 |

---

## 9. 验收标准

**功能**

- 9 个工具全部可列出、可调用，描述包含"做什么/何时用/入参/返回/错误"四段。
- 零模型环境下 8 个工具可用，`ask_coach` 明确报 `model_not_configured` 并说明其余可用。
- 完整闭环可在 MCP 上跑通并看到掌握度变化。

**安全**

- 工具参数中不存在 `owner_id`；跨用户访问表现为不存在。
- 含注入的资料不产生副作用，且不进入 `expected_answer`。
- 三个写工具幂等键必填，重放返回同一结果。
- 日志不含参数正文、返回正文与凭据。

**交付**

- README 有 MCP 章节（地址、鉴权、工具清单、示例）。
- 提交表单的"体验链接"之外，附 MCP 端点地址。
- 全量验收：pytest / ruff / 密钥扫描 / vitest / eslint / build / Playwright + 新增 MCP 测试全绿。

---

## 10. 风险

| 风险 | 影响 | 对策 |
| --- | --- | --- |
| **uv 不可用导致依赖加不进去** | Phase 1 无法开始 | 先做 0-a；实在不行退化为不引入 SDK、手写最小 JSON-RPC（工作量上升但可控） |
| 评测账号被改密或触发"退出所有会话" | 提交的 MCP 接口当场失效 | 专用账号、不在演示中使用、部署后不再登录 Web |
| 平台调用产生真实模型费用 | 额度耗尽后闭环退化为降级 | MCP 侧写操作限流 60/分钟；降级路径本身可用，不会中断 |
| P0-5 未修先上 MCP | 把污染入口从 Web 扩到协议层 | 列为前置阻塞项 0-b |
| 时间不足 | 赶不上初赛 | Phase 1+2（stdio）即可交付一个可本地验证的 MCP；Phase 3 的公网 HTTP 是增量 |

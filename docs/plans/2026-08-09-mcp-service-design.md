# RefineQ MCP 服务设计

> 日期：2026-08-09
>
> 状态：设计定稿候选（v4，待兼容性 Spike 通过后实施）
>
> 适用范围：比赛动态评测 MVP；产品化 MCP 仅定义演进边界，不在本期承诺
>
> 关联计划：[MCP 服务实施计划](./2026-08-09-mcp-service-implementation.md)
>
> 依据：[HACKATHON.md](../../HACKATHON.md)、[架构说明](../architecture.md)、MCP 官方规范

## 0. 执行摘要

RefineQ 应该提供 MCP 接口，但本期只做一个**面向动态评测、可重复验证核心学习闭环的最小适配层**，不建设完整的外部 Agent 平台。

原因有三点：

1. RefineQ 的核心价值是“自己的资料 → 主动练习 → 可信判分 → 掌握证据 → 下一行动”，不是协议覆盖率。
2. 比赛允许解析源码包或调用 MCP。MCP 的直接价值是降低评测方启动和理解系统的成本，而不是替代 Web 产品。
3. 当前没有用户级机器凭据、持久任务系统或可复用的资料摄取应用服务。此时同时建设 10 个工具、Resources、Prompts、Tasks 和 Elicitation，会扩大风险而不会等比例增加评测价值。

本设计因此采用两阶段方案：

- **Phase A：评测 MVP。** 5 个工具、Streamable HTTP、可重置的隔离沙箱、同步有界执行、确定性降级。
- **Phase B：产品化扩展。** 用户级授权、资料写入、可信学习证据、持久任务、Resources 和 Prompts；每项都必须先满足对应前置条件。

本期明确不做：Tasks、Elicitation、资料上传、计划修改、教练会话、Resources、Prompts、stdio 交付和通用第三方账号接入。

按一名熟悉仓库的工程师估算，完整 Phase A 仍需约 4～6 个工程日，包括协议 Spike、沙箱恢复、公网验证和全量回归。若距离比赛提交不足 24 小时，应优先保证源码 ZIP、Web 主流程和公开部署；除非隔离沙箱和公网闭环已经通过，否则不发布半成品 MCP，更不能省略隔离和安全门后宣称闭环完成。

---

## 1. 产品判断

### 1.1 RefineQ 的不可替代价值

MCP 只是适配器。它必须暴露现有产品闭环，而不能另造一套简化业务：

```text
学习目标与资料
    ↓
识别当前学习状态
    ↓
从资料生成主动练习
    ↓
结构化判分与证据
    ↓
掌握度与下一行动
```

任何 MCP 能力只在满足以下至少一项时进入本期：

- 能让评测方直接观察核心闭环；
- 能显著降低运行和验证成本；
- 能复用既有领域不变量，而不是复制业务逻辑。

### 1.2 两类用户必须分开

| 使用者 | 当前价值 | 本期处理 |
| --- | --- | --- |
| 比赛评测方 | 快速连通并验证核心能力 | **本期主用户**，提供隔离评测沙箱 |
| 真实学习用户的外部 Agent | 在其他客户端调用个人学习状态 | 需求尚未验证，进入 Phase B |

不能用比赛共享密钥冒充产品级授权，也不能用合成评测作答冒充真实学习者证据。

### 1.3 为什么不是完整 API 映射

将 REST 端点逐一转换为 MCP 工具会造成：

- 工具描述重叠，调用方难以选择；
- 暴露账号、管理、归档、备份等非学习能力；
- 响应体积失控；
- 在 MCP 层复制权限、事务和错误语义；
- 为协议展示牺牲核心路径可靠性。

MCP 只暴露“评测所需的最短学习闭环”。Web 专属操作继续留在 Web。

---

## 2. 已知约束与决策门

### 2.1 仓库现状

| 约束 | 影响 |
| --- | --- |
| 当前没有 `mcp` 依赖和 `src/refineq/mcp/` | 这是新适配层，不是补齐已有实现 |
| 当前 JWT 面向浏览器会话，没有用户级 API token/OAuth | 本期只能使用独立评测凭据，不得宣称支持真实用户接入 |
| 资料上传编排仍主要位于 API router | 本期不提供 `add_material`；先抽取共享应用服务 |
| 没有持久任务表、worker、lease、恢复与清理机制 | 本期不声明 Tasks 能力 |
| workspace snapshot 有事件副作用且响应可能很大 | MCP 只读工具必须使用独立只读投影 |
| 外部模型调用已有确定性降级路径 | MVP 可保持同步，并在预算内降级 |

### 2.2 协议基线

实现以 MCP `2026-07-28` 为目标，同时验证官方 SDK 支持的上一稳定协议版本。协议和 SDK 事实以实现当天的官方资料为准：

- [MCP 2026-07-28 发布说明](https://blog.modelcontextprotocol.io/posts/2026-07-28/)
- [`server/discover` 规范](https://modelcontextprotocol.io/specification/draft/server/discover)
- [Python SDK](https://github.com/modelcontextprotocol/python-sdk)
- [ASGI 挂载说明](https://py.sdk.modelcontextprotocol.io/run/asgi/)

实施要求：

1. 使用支持目标协议的官方 Python SDK v2，并锁定一个经过测试的精确版本和哈希。
2. 不手写 JSON-RPC 作为依赖失败时的退路。
3. 每个请求独立解析协议版本和客户端能力，不依赖连接级隐式状态。
4. 实现并测试 `server/discover`；声明的能力必须和实际实现完全一致。
5. 目标评测客户端不支持某项能力时，删减能力，而不是要求评测方升级。

### 2.3 兼容性 Spike 是实施门槛

在编写领域工具之前，必须用实际评测客户端或官方 Inspector 验证：

- Streamable HTTP 是否可用；
- 远程 URL 的格式；
- `Authorization: Bearer` 是否能透传；
- 支持的协议版本；
- 是否能正确消费 `structuredContent`、`outputSchema` 和 `isError`；
- 网络代理的连接与响应超时。

若无法确认实际评测客户端，则最低交付以官方 Python SDK 客户端和 Inspector 为准，并在文档中明确“目标平台兼容性未确认”，不能把推测写成已支持。

---

## 3. 设计原则

### 3.1 适配，不复制

MCP handler 只负责：

```text
协议参数校验 → 身份/沙箱解析 → 调用应用服务或只读投影 → MCP 结果映射
```

它不得：

- 直接操作 repository 绕过应用服务；
- 重写计划、判分、检索或掌握度算法；
- 调用自身 HTTP API；
- 把 API router 当作可复用领域服务。

### 3.2 真实性优先于能力数量

- “configured” 不等于“healthy”。
- 确定性降级必须显式返回 `mode="fallback"`。
- 未验证作者身份的答案不能污染真实用户掌握度。
- 不支持的能力不出现在 `server/discover`。
- 业务错误通过稳定错误码表达，不能伪装成成功文本。

### 3.3 隔离和可重复优先于共享状态

所有比赛调用使用专用评测账号和**串行、可重置的评测沙箱**：

- `begin_demo` 创建或幂等恢复一个评测运行；
- 同一 `client_run_key` 重试返回同一个运行；
- 同一时刻只允许一个运行占用评测账号；
- 第二个运行收到可重试的 `demo_busy`，而不是共享学习状态；
- 运行有 5 分钟 TTL，成功提交答案后立即完成并释放；被遗弃的运行过期自动释放；
- 新运行开始前按固定模板重置专用账号；
- 真实用户数据永远不进入评测沙箱。

这是比赛适配方案，不是多租户产品架构。Phase B 必须改为用户级授权和 owner 隔离。

### 3.4 证据来源和学习效果分离

MCP 传入的答案只能证明“调用方提交了这段文本”，不能证明学习者本人完成了作答。

评测沙箱允许展示完整的模拟学习效果，但必须返回：

```json
{
  "evidence_source": "mcp_relayed",
  "simulation": true,
  "mastery_effect": {
    "applied_to_sandbox": true,
    "applied_to_real_learner": false
  }
}
```

真实用户 Phase B 的默认规则是：

- `mcp_relayed`：可以判分和保存为低信任记录，但不更新掌握度；
- `mcp_elicited`：仍是客户端提供的输入，不自动视为真人证明；
- 只有可验证的可信交互通道才能产生 mastery evidence。

### 3.5 所有写操作可安全重试

每个 mutation 都必须有：

- 调用方生成的幂等键；
- 服务端唯一约束；
- 稳定 replay 结果；
- 冲突时的 `expected_version` 或等价前置条件；
- 外部模型调用采用 snapshot → network → conditional commit；
- 超时后重试不会重复生成证据或重复更新状态。

---

## 4. Phase A：评测 MVP

### 4.1 工具总览

MVP 只提供 5 个工具。

| 工具 | 类型 | 目的 |
| --- | --- | --- |
| `refineq_begin_demo` | 写 | 创建/恢复一个隔离评测运行并返回已播种状态 |
| `refineq_get_learning_context` | 读 | 读取目标、计划摘要、主题、资料和下一行动 |
| `refineq_search_materials` | 读 | 从预置资料中检索带出处的有界片段 |
| `refineq_get_practice_task` | 写 | 幂等取得或生成一道资料约束题 |
| `refineq_submit_answer` | 写 | 幂等判分并展示沙箱中的证据和掌握变化 |

不提供 `owner_id` 参数。除 `begin_demo` 外，其余工具都要求不透明的 `run_id`；服务端将其解析为专用评测 principal 和 sandbox owner。

### 4.2 `refineq_begin_demo`

**用途**：开始一轮可重复评测，返回固定学习空间、资料状态和运行时能力。

输入：

```json
{
  "client_run_key": "caller-generated-idempotency-key"
}
```

输出摘要：

```json
{
  "run_id": "opaque-random-token",
  "expires_at": "2026-08-09T12:00:00Z",
  "simulation": true,
  "space": {
    "id": "...",
    "title": "极限与连续性",
    "material_count": 1
  },
  "runtime": {
    "question": {"configured": true, "mode": "ai"},
    "grading": {"configured": true, "mode": "ai"},
    "retrieval": {"configured": true, "mode": "hybrid"},
    "observed_at": null,
    "stale": true
  },
  "next_tool": "refineq_get_learning_context"
}
```

`runtime` 只报告配置状态和最近一次已观测结果。没有 canary 记录时必须返回 `observed_at=null, stale=true`，不得声称健康。

错误：

- `demo_busy`：另一个运行正在占用沙箱，带 `retry_after_ms`；
- `demo_seed_failed`：重置失败，运行不得进入 active；
- `unauthorized`：评测凭据错误。

### 4.3 `refineq_get_learning_context`

**用途**：一次返回评测所需的有界学习上下文，避免枚举大量细粒度资源。

输入：`run_id`。

输出最多包含：

- 一个预置空间；
- 目标、截止日期和每日时长；
- 最多 8 个主题的掌握摘要；
- 今日最多 8 个会话；
- 资料数量和索引状态；
- 当前 pending question 摘要；
- 下一行动及其理由；
- `state_version`。

禁止返回 chunk 全文、完整证据台账和无界计划。该工具使用新的只读投影，不得调用带 journey-event 写入副作用的 workspace snapshot。

### 4.4 `refineq_search_materials`

输入：

```json
{
  "run_id": "...",
  "query": "函数在一点连续需要满足什么条件？",
  "limit": 5
}
```

约束：

- `limit` 范围 1～8；
- 每个 excerpt 最多 400 个 Unicode 字符；
- 总响应不超过 8 KiB；
- 只返回沙箱空间已链接、已索引的资料；
- embedding 不可用时退化为 lexical，并返回 `retrieval_mode`；
- 每条结果必须含稳定 `citation_id`、文件名和相关度。

资料正文始终是不可信数据，不能改变工具选择、权限或 answer key。

### 4.5 `refineq_get_practice_task`

输入：

```json
{
  "run_id": "...",
  "request_id": "caller-generated-idempotency-key",
  "topic_id": null,
  "difficulty": 3
}
```

行为：

1. 在沙箱内复用现有 pending question；否则生成新题。
2. 最终题目必须满足资料 grounding 不变量，不能仅因为“存在已索引资料”就宣称 grounded。
3. `request_id` 重放返回同一个 `question_id` 和相同结果。
4. AI 超过预算或不可用时使用确定性资料约束题，并标记 `mode="fallback"`。
5. 不支持没有资料的通用模板题；种子异常时返回 `material_required`。

输出包括 `question_id`、题面、主题、难度、引用、grounding、生成模式和 `state_version`。

### 4.6 `refineq_submit_answer`

输入：

```json
{
  "run_id": "...",
  "question_id": "...",
  "answer": "...",
  "attempt_id": "caller-generated-idempotency-key",
  "expected_state_version": 12
}
```

行为：

- 只接受当前沙箱的 pending question；
- `attempt_id` 重放返回同一份判分和证据；
- 状态版本不符返回 `state_conflict`，不得覆盖新状态；
- 判分模型失败时可以走确定性降级，但只有满足现有可信证据规则时才算通过；
- prompt echo、资料指令注入和不可信 answer key 不得形成 mastery evidence；
- 掌握变化只写入评测沙箱，并明确 `simulation=true`。
- 结果持久化后将运行标为 completed 并释放沙箱；此后的重复 `attempt_id` 仍从幂等记录返回同一结果，其他工具不再接受该 run。

输出包括分数、是否通过、优势、缺口、误区、引用、判分模式、证据来源、沙箱掌握度前后值、最终状态摘要和下一行动。因此评测方不需要在提交后再次读取已经释放的运行。

---

## 5. MCP 响应契约

### 5.1 成功结果

每个工具都定义 `inputSchema` 和 `outputSchema`，并返回正式 `CallToolResult`：

- `structuredContent`：机器可消费的主结果；
- `content`：一段简短文本回退，供旧客户端显示；
- `isError=false`；
- `schema_version="1"`；
- `request_id`、`mode`、`warnings` 使用统一字段。

工具 annotations 必须如实设置：

- 读取工具：`readOnlyHint=true`；
- 沙箱写工具：`readOnlyHint=false`；
- 幂等写工具：`idempotentHint=true`；
- 所有 MVP 工具：`openWorldHint=false`；
- 不声明无依据的 destructive 或安全属性。

### 5.2 错误结果

参数 Schema 错误由协议层返回。业务错误返回 `isError=true`：

```json
{
  "schema_version": "1",
  "error": {
    "code": "state_conflict",
    "message": "学习状态已变化，请重新读取上下文后重试。",
    "retryable": true,
    "retry_after_ms": null,
    "next_action": "refineq_get_learning_context"
  }
}
```

稳定错误码至少包含：

| 错误码 | 重试 | 语义 |
| --- | --- | --- |
| `unauthorized` | 否 | 凭据无效 |
| `run_not_found` | 否 | 运行不存在或不属于当前 principal |
| `run_expired` | 是 | 重新调用 `begin_demo` |
| `demo_busy` | 是 | 沙箱被另一运行占用 |
| `state_conflict` | 是 | 状态版本变化 |
| `material_required` | 否 | 种子资料不可用，属于部署故障 |
| `model_timeout` | 视情况 | 且没有可用降级路径 |
| `rate_limited` | 是 | 带 `retry_after_ms` |
| `internal_error` | 是 | 不泄露内部异常、路径和 SQL |

---

## 6. 身份、沙箱与安全边界

### 6.1 评测认证

MVP 只接受：

```http
Authorization: Bearer <REFINEQ_MCP_EVALUATION_SECRET>
```

要求：

- 使用标准 Authorization 头，不发明专用密钥头；
- 服务端保存密钥哈希或通过恒定时间方式比较；
- 密钥只通过 `REFINEQ_*` 环境变量配置；
- 日志、错误、OpenAPI 和 MCP 响应不得出现密钥；
- 支持轮换，启动时拒绝默认值和弱密钥；
- 按凭据和来源 IP 双层限流；
- 评测 principal 只能访问专用沙箱。

### 6.2 运行生命周期

沙箱运行使用小型持久记录，而不是连接内存：

```text
idle → seeding → active → completed
         ↓           ↓
       failed   expired/released
```

运行记录至少包含：`run_id_hash`、`client_run_key_hash`、`principal_id`、`status`、`expires_at`、`seed_version`、`created_at`、`updated_at`。

另外保存有 TTL 的 MCP 幂等结果：`principal_id`、`run_id_hash`、`tool_name`、`idempotency_key_hash`、`input_hash`、`result_json`、`created_at`、`retain_until`。这样下一轮重置了底层学习状态后，上一轮的网络重试仍能返回原结果，而不会重新判分。

安全规则：

- 不存明文 run token；
- `client_run_key` 唯一且与 principal 绑定；
- 任何工具调用都重新验证 TTL 和 principal；
- 幂等重放先校验 principal、run、tool、key 和 input hash；同 key 不同输入返回 conflict；
- 重置必须在专用 owner 的学习状态事务和资料恢复协议内完成；
- 崩溃遗留的 `seeding`/`active` 运行由启动恢复或下一次 `begin_demo` 回收；
- 不跨请求持有数据库事务或进程锁。

### 6.3 继承现有产品不变量

MCP 不得弱化以下规则：

1. 所有 repository 操作 owner-scoped；跨 owner 表现为不存在。
2. 上传资料和检索片段都是数据，不是指令。
3. 掌握度只能由可信证据路径改变。
4. 外部网络调用不持有长数据库事务或资料 mutation lease。
5. object storage、SQL 和索引写入沿用恢复协议。
6. 所有写操作有幂等与并发前置条件。
7. 日志只记录工具名、耗时、结果类别、错误码、协议版本和匿名运行标识，不记录题面、答案、资料正文或凭据。

---

## 7. 传输与部署

### 7.1 ASGI 结构

使用官方 SDK 的 Streamable HTTP transport，挂载到 FastAPI：

```text
FastAPI parent app
└── /mcp  → MCP ASGI app（内部 path = /）
```

必须由父应用 lifespan 启动和停止 MCP session manager。不能只调用 `app.mount()` 后假设子应用 lifespan 自动执行。

部署还必须验证：

- 外部最终地址确实是 `/mcp`，不是 `/mcp/mcp`；
- transport security 的 `allowed_hosts` 包含正式域名；
- Caddy 保留 Authorization 头并正确转发流式响应；
- `/api/*` 的 `handle_path` 不影响 `/mcp`；
- 健康检查不创建 MCP 沙箱或写 journey event；
- 冷启动到 `server/discover` 成功在部署预算内。

### 7.2 配置

新增配置必须进入强类型 `Settings`、`.env.example` 和 Compose，不得只读取散落的 `os.environ`：

```text
REFINEQ_MCP_ENABLED
REFINEQ_MCP_EVALUATION_SECRET
REFINEQ_MCP_ALLOWED_HOSTS
REFINEQ_MCP_RUN_TTL_SECONDS        # 默认 300
REFINEQ_MCP_IDEMPOTENCY_TTL_SECONDS # 默认 86400
REFINEQ_MCP_READ_RATE_LIMIT
REFINEQ_MCP_WRITE_RATE_LIMIT
```

默认 `REFINEQ_MCP_ENABLED=false`。生产启动时若启用 MCP 但密钥缺失、过短或仍是示例值，应 fail closed。

---

## 8. 延迟、降级与容量

| 工具 | P95 目标 | 最大执行预算 | 超时行为 |
| --- | ---: | ---: | --- |
| `begin_demo` | 2 s | 5 s | 失败，不留下 active 运行 |
| `get_learning_context` | 500 ms | 2 s | 返回可恢复错误 |
| `search_materials` | 1.5 s | 4 s | hybrid → lexical |
| `get_practice_task` | AI 12 s / fallback 1 s | 20 s | 超时转确定性题 |
| `submit_answer` | AI 12 s / fallback 1 s | 20 s | 超时转规则判分 |

规则：

- MVP 不创建后台 Task；一次调用必须在预算内成功、降级或失败。
- 超时后的后台模型结果必须被取消或丢弃，不能迟到提交。
- `mode`、`grading_mode`、`retrieval_mode` 必须如实返回。
- 响应体默认不超过 16 KiB；检索结果不超过 8 KiB。
- 限流按 read/write 分开，`begin_demo` 有更严格的重置频率。

---

## 9. 明确不进入 MVP 的能力

| 能力 | 暂缓原因 | 进入 Phase B 的门槛 |
| --- | --- | --- |
| `add_material` | router 编排尚未抽成共享服务 | `MaterialIngestionService` 覆盖配额、对象、索引、lease、恢复和 workspace 重验 |
| `start_learning` | 真实空间创建会产生长期状态和重试歧义 | 用户级授权、幂等键、创建/撤销边界完成 |
| `update_plan_session` | 缺少统一幂等和乐观并发契约 | `request_id + expected_version` 落入领域服务 |
| `ask_coach` | 强依赖模型且不是评测闭环最短路径 | 真实客户端需求、费用和超时策略明确 |
| Resources | 用户私有缓存、分页和变更通知尚未设计 | `cacheScope=private`、TTL、cursor 和订阅策略完成 |
| Prompts | 不能保证宿主模型严格执行工具序列 | 在目标客户端实测有价值，或改为服务端 workflow 工具 |
| Elicitation | 不能证明真人作者身份 | 只作为 UX 输入机制；可信证据另有可验证通道 |
| Tasks | 无持久任务基础设施 | task repository、worker、lease、恢复、principal 绑定、取消和 TTL 全部完成 |
| stdio | 远程评测以 HTTP 为主，多一个传输面增加测试成本 | 出现明确本地集成需求 |

---

## 10. Phase B：产品化演进

Phase B 不是自动执行的待办清单，每项都必须有真实客户端需求或评测证据。

### 10.1 用户级授权

- OAuth 2.1 或用户级可撤销 token；
- token scope 至少分为 `learning:read`、`practice:write`、`materials:write`、`plan:write`；
- principal 与 task、resource、idempotency record 永久绑定；
- 账号停用、密码重置、全局登出和授权撤销语义明确；
- 不再使用评测共享账号。

### 10.2 资料摄取应用服务

先从 API router 抽取 `MaterialIngestionService`，Web 和 MCP 共同调用。服务必须拥有：

- 文件/文本标准化；
- 类型、大小和配额检查；
- canonical material 去重与 workspace link；
- 对象存储和索引写入；
- material mutation lease；
- commit 前 owner/workspace 重验；
- crash recovery 和补偿；
- 幂等上传结果。

### 10.3 可信学习证据

产品化 MCP 默认只把答案记为 `mcp_relayed`。如果希望计入掌握度，需要设计独立、可验证的用户交互证明，不能依赖调用方自报 `authored_by`，也不能仅以 Elicitation 作为真人证明。

### 10.4 持久任务

Tasks 只有在以下能力全部存在后才能在 `server/discover` 中声明：

- 持久 task 表和状态机；
- response 前 durable create；
- worker 与 lease；
- snapshot/network/conditional-commit；
- principal 和 scope 绑定；
- `get/update/cancel`；
- crash recovery；
- 过期清理；
- 同步与 task 路径共享同一幂等语义。

---

## 11. 测试策略

### 11.1 协议和契约

- 官方 SDK in-memory client 调用全部工具；
- 真实 Streamable HTTP client 经 ASGI 和 Caddy 调用；
- `server/discover`、`tools/list` 在目标和上一协议版本下通过；
- `inputSchema`、`outputSchema` 和实际 `structuredContent` 一致；
- 业务错误 `isError=true`；
- schema snapshot 防止无意破坏调用方。

### 11.2 领域与并发

- 同一 `client_run_key` 并发开始只产生一个运行；
- 两个不同运行不会共享状态，第二个收到 `demo_busy`；
- 运行过期后可安全回收；
- 同一 `request_id` 只产生一道题；
- 同一 `attempt_id` 只产生一条证据和一次状态变化；
- stale `expected_state_version` 不覆盖新状态；
- 模型超时后的迟到结果不能提交。

### 11.3 安全和对抗

- 伪造、过期、其他 principal 的 `run_id` 均失败；
- `run_id`、secret、答案和资料正文不进入日志；
- 检索内容中的“忽略规则”“给满分”等指令不起作用；
- prompt echo、近似改写和通用填充不能形成可信掌握证据；
- 不存在 `owner_id` 输入字段；
- 公开 host、错误 host、缺失 Authorization 和超限请求均有确定行为。

### 11.4 部署验收

- 从公网执行 discover → begin → context → search → question → answer；
- 冷启动后首次请求成功；
- 最终地址是 `/mcp`；
- Caddy 保留认证和流式传输；
- 关闭模型配置后仍能用 fallback 跑完整沙箱闭环；
- secret scan、Python 全量测试、ruff、前端测试、lint、build 和关键 E2E 全绿。

---

## 12. 完成定义

只有同时满足以下条件，Phase A 才算完成：

1. 兼容性 Spike 已记录实际客户端、协议版本和认证方式。
2. 官方 SDK v2 精确锁定，锁文件可重复生成。
3. `server/discover` 只声明 5 个真实可用工具，不声明 Tasks、Elicitation、Resources 或 Prompts。
4. 评测沙箱可重置、可完成、可过期、可恢复，不与真实用户共享数据。
5. 五个工具都有 output schema、稳定错误码、响应上限和 annotations。
6. 整个闭环支持幂等重试和状态版本冲突检测。
7. MCP 作答明确标记为模拟，不伪装成真实学习者证据。
8. 只读工具没有 journey-event 或其他写副作用。
9. 公网 Streamable HTTP 端到端测试通过。
10. README 写明 endpoint、认证、5 个工具、沙箱语义、降级行为和限制。

任何一项不满足，都不能用“本地函数测试通过”替代。

---

## 13. 风险与应对

| 风险 | 影响 | 应对 |
| --- | --- | --- |
| 目标平台不支持 2026 协议 | 无法连通 | Spike 先行；验证 SDK 的上一稳定协议兼容性 |
| 平台不能传 Authorization | 认证失败 | 提前向主办方确认；不把密钥放 URL 或工具参数 |
| 沙箱重置失败 | 评测看到脏状态 | fail closed；不创建 active run；提供部署告警 |
| 同一账号并发评测 | 状态互相污染 | 持久串行 lease、`demo_busy` 和 TTL 回收 |
| 外部模型超时 | 动态评测不稳定 | 严格预算和确定性降级；迟到结果不提交 |
| SDK 版本或规范变化 | 契约漂移 | 精确 pin、协议矩阵测试、schema snapshot |
| 为赶时间手写协议 | 产生隐蔽兼容和安全问题 | 禁止手写 JSON-RPC；Spike 失败就缩小交付，不降低协议正确性 |
| MCP 挤占主产品工作 | 影响更高权重的体验与真实使用 | Phase A 固定范围；Phase B 需要独立产品证据和排期 |

---

## 14. 设计决策记录

| 决策 | 结论 | 原因 |
| --- | --- | --- |
| 是否做 MCP | 做评测 MVP | 降低动态评测接入成本 |
| 是否做完整外部 Agent 平台 | 本期不做 | 用户需求、身份和任务基础设施未成立 |
| 是否提供 10 个工具 | 否，MVP 5 个 | 用最短闭环控制范围和风险 |
| 是否提供资料上传 | 否 | 尚无可复用的资料摄取应用服务 |
| 是否使用 Tasks | 否 | 无 durable task architecture，且客户端支持不确定 |
| 是否使用 Elicitation 证明本人作答 | 否 | 协议不能证明真实作者身份 |
| MCP 作答是否改变真实掌握度 | 否 | 只改变明确标记的评测沙箱状态 |
| 是否使用共享可变种子账号 | 仅作为串行可重置沙箱 | 通过运行 lease 和 TTL 阻止跨评测污染 |
| 是否提供 Resources/Prompts | MVP 不提供 | 不是闭环必需，且兼容性和价值未验证 |
| 是否手写 JSON-RPC 兜底 | 否 | 协议和安全风险不可接受 |

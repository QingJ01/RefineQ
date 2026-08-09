# MCP 服务实施计划

> 日期：2026-08-09
>
> 状态：待实施（v4；只有 Phase 0 兼容性门通过后才能进入编码）
>
> 设计依据：[RefineQ MCP 服务设计](./2026-08-09-mcp-service-design.md)
>
> 目标：交付一个可从公网重复运行、不会污染真实用户状态的 MCP 评测 MVP

## 0. 范围和完成标准

本计划只实现以下 5 个工具：

1. `refineq_begin_demo`
2. `refineq_get_learning_context`
3. `refineq_search_materials`
4. `refineq_get_practice_task`
5. `refineq_submit_answer`

本期不实现：

- Tasks；
- Elicitation；
- Resources；
- Prompts；
- `add_material`；
- `start_learning`；
- `update_plan_session`；
- `ask_coach`；
- stdio 交付；
- 真实用户 OAuth/API token。

任何人在实施中扩大上述范围，都需要先更新设计文档、说明新增用户价值和前置条件，并重新评估交付时间。

### 总体验收路径

从公网使用真实 MCP 客户端完成：

```text
server/discover
  → tools/list
  → begin_demo
  → get_learning_context
  → search_materials
  → get_practice_task
  → submit_answer
```

`submit_answer` 必须返回最终证据、沙箱掌握变化和下一行动，然后原子地将运行标为 completed 并释放沙箱。所有结果都明确 `simulation=true`，不改变真实用户数据。

### 工作量和截止线

| 阶段 | 单人估算 | 可交付结果 |
| --- | ---: | --- |
| Phase 0 | 0.5 天 | 已验证的协议、SDK 和真实 wire skeleton |
| Phase 1 | 0.75～1 天 | 配置、合同、认证、lifespan 和 HTTP transport |
| Phase 2 | 1～1.5 天 | 可恢复、可重复的评测沙箱 |
| Phase 3 | 0.5～0.75 天 | 无副作用 context 和有界资料检索 |
| Phase 4 | 1～1.5 天 | 幂等出题、判分和沙箱学习效果 |
| Phase 5～6 | 0.75～1 天 | 公网、可观测性、回归和独立验收 |

总计约 4～6 个工程日，不把代码审查后的修复时间压成零。

如果提交截止不足 24 小时：

1. 先保证源码 ZIP、Web 主流程和公开部署；
2. 可以完成 Phase 0 作为技术验证，但它不等于可提交的 MCP 产品端点；
3. 若 Phase 2 的隔离沙箱尚未完成，不发布会接触可变学习状态的 MCP；
4. 不得改用共享可变账号、手写协议或省略 owner/secret 测试来伪装完整闭环；
5. 比赛提交走赛制允许的源码 ZIP 路径，MCP 留到完整质量门通过后再开放。

---

## 1. 实施纪律

### 1.1 TDD 顺序

每个任务严格按以下顺序：

1. 写会失败的测试；
2. 运行目标测试并确认失败原因正确；
3. 写最小实现；
4. 运行目标测试；
5. 运行相邻模块回归；
6. 代码和文档同步更新。

不能先写实现再补“证明当前行为”的测试。

### 1.2 架构边界

- MCP handler 不直接写 repository，只有沙箱生命周期 repository 除外。
- 学习、检索、出题和判分必须复用现有应用/领域服务。
- MCP 不通过 HTTP 调用本项目自己的 REST API。
- 不调用有 journey-event 副作用的 workspace snapshot。
- 外部模型调用必须保持 snapshot → network → conditional commit。
- 不在外部模型调用期间持有数据库事务、owner lock 或 material mutation lease。
- 所有配置进入 `refineq.config.Settings`，禁止散落读取环境变量。

### 1.3 建议模块结构

```text
src/refineq/mcp/
├── __init__.py
├── auth.py                 # Bearer 验证和 MCP principal
├── contracts.py            # 输入/输出模型、schema_version
├── errors.py               # 稳定错误码和 CallToolResult 映射
├── projections.py          # 无副作用、有界只读投影
├── sandbox.py              # 评测运行、lease、重置和恢复
├── tools.py                # 5 个薄 handler
└── server.py               # SDK server、discover、ASGI transport
```

数据库和应用装配仍留在现有边界：

- schema/migration：`src/refineq/database/engine.py` 及现有迁移路径；
- 配置：`src/refineq/config.py`；
- FastAPI 装配：`src/refineq/api/app.py`；
- 公网路由：`infra/Caddyfile`；
- Compose 配置：`infra/compose.yml`。

---

## 2. Phase 0 · 兼容性和依赖门

在 Phase 0 完成前，不编写业务工具。

### Task 0.1：确认目标客户端能力

**产物**

新增：

- `docs/operations/mcp-compatibility.md`

记录：

- 实际客户端名称和版本；
- 可连接的 MCP 协议版本；
- Streamable HTTP 支持情况；
- `Authorization: Bearer` 是否透传；
- `server/discover`、`tools/list`、`tools/call` 的实际请求/响应；
- `structuredContent`、`outputSchema`、`isError` 的消费行为；
- 客户端和代理超时；
- 不支持的能力清单。

**验证方法**

先使用官方 Inspector；能获得比赛实际客户端时，再重复相同矩阵。使用最小官方 SDK echo server，不接入 RefineQ 领域逻辑。

**阻塞条件**

- 无法通过公网 Streamable HTTP 连通；
- 平台不能安全传递凭据；
- 只能使用与官方 SDK v2 不兼容的协议版本。

遇到阻塞时先调整交付方案，不能通过把密钥放 URL、工具参数或日志来绕过。

### Task 0.2：选择并锁定官方 SDK v2

**修改**

- `pyproject.toml`
- `requirements.lock`
- `requirements-dev.lock`
- 需要时更新 `THIRD_PARTY_NOTICES.md`

**步骤**

1. 从官方 Python SDK 发布记录中选择支持目标协议的当前稳定 v2。
2. 在兼容性文档记录精确版本、发布日期和对应协议。
3. `pyproject.toml` 使用精确版本或经过评审的窄兼容范围；锁文件必须固定哈希。
4. 在 Python 3.11、3.12、3.13 的项目支持范围内至少验证 CI 使用版本和生产版本。

禁止：

- 使用 `mcp<2` 实现 `2026-07-28`；
- 提交 `mcp==2.x.y` 之类占位版本；
- SDK 安装失败后手写 JSON-RPC；
- 只修改 `pyproject.toml` 而不重生成锁文件。

**验证**

```powershell
python -c "import mcp; print(mcp.__file__)"
python -m pip check
```

使用仓库既有锁文件生成流程重建三份 lock，并确认第二次生成没有 diff。

### Task 0.3：提交最小协议 Spike

**新增**

- `src/refineq/mcp/__init__.py`
- `src/refineq/mcp/server.py`
- `tests/contract/test_mcp_protocol.py`

**测试先行**

测试必须通过官方 SDK client，而不是直接调用 Python 函数：

- `server/discover` 返回目标和兼容协议版本；
- `tools/list` 当前为空；
- 未声明 Tasks、Elicitation、Resources、Prompts；
- 不支持的协议版本返回规范错误；
- 最小 Streamable HTTP ASGI 请求成功。

**退出标准**

- 兼容性矩阵已写入文档；
- SDK v2 和锁文件确定；
- 实际 wire test 通过；
- 团队确认继续 Phase 1。

---

## 3. Phase 1 · MCP 基础设施

### Task 1.1：强类型配置

**修改**

- `src/refineq/config.py`
- `.env.example`
- `infra/compose.yml`
- `tests/unit/test_config.py` 或现有配置测试

**新增配置**

```text
REFINEQ_MCP_ENABLED=false
REFINEQ_MCP_EVALUATION_SECRET=
REFINEQ_MCP_ALLOWED_HOSTS=
REFINEQ_MCP_RUN_TTL_SECONDS=300
REFINEQ_MCP_IDEMPOTENCY_TTL_SECONDS=86400
REFINEQ_MCP_READ_RATE_LIMIT=120
REFINEQ_MCP_WRITE_RATE_LIMIT=30
```

**测试**

- 默认关闭；
- 启用但密钥缺失时启动失败；
- 示例值、短密钥和空 allowed-hosts 在生产模式下失败；
- TTL 和限流上下界校验；
- `SecretStr` 不在 repr 和错误中泄露；
- 未识别的旧环境变量不能悄悄启用服务。

### Task 1.2：统一合同和错误映射

**新增**

- `src/refineq/mcp/contracts.py`
- `src/refineq/mcp/errors.py`
- `tests/unit/test_mcp_contracts.py`

**实现**

- Pydantic 输入/输出模型；
- `schema_version="1"`；
- 成功和错误 `CallToolResult` builder；
- `structuredContent` 与简短 text fallback；
- 稳定错误码、`retryable`、`retry_after_ms`、`next_action`；
- 全部输出经过 `outputSchema` 校验；
- 未知异常统一映射为 `internal_error`，服务端保留 correlation id，但不返回堆栈。

**测试**

- 每个错误都是 `isError=true`；
- 错误 text 和 structured 内容语义一致；
- secret、SQL、绝对路径和异常 repr 不出现在结果中；
- Schema snapshot 稳定；
- 响应序列化支持 Unicode。

### Task 1.3：Bearer 认证和 principal

**新增/修改**

- `src/refineq/mcp/auth.py`
- `tests/integration/test_mcp_auth.py`

**实现**

- 只从 `Authorization: Bearer` 读取评测密钥；
- 恒定时间比较或哈希查找；
- 映射为固定 `mcp_evaluator` principal；
- 日志只保留不可逆 principal 标识；
- 缺失、错误、过期轮换密钥返回 `unauthorized`；
- 按 principal + IP 执行 read/write 限流。

**对抗测试**

- query string、cookie、工具参数中的密钥不生效；
- 前后空白、多 Authorization 头、大小写变体有确定行为；
- 凭据不进入 access log、异常和 tracing 属性；
- 大量错误密钥触发限流。

### Task 1.4：FastAPI lifespan 与 Streamable HTTP

**修改**

- `src/refineq/api/app.py`
- `src/refineq/mcp/server.py`
- `tests/contract/test_mcp_transport.py`

**实现**

1. 将现有 startup/shutdown 资源管理迁移或组合到父 FastAPI lifespan。
2. 在父 lifespan 中运行 SDK session manager。
3. MCP 子应用内部 path 设为 `/`，父应用只挂载一次 `/mcp`。
4. 配置 transport security allowed hosts。
5. `REFINEQ_MCP_ENABLED=false` 时不挂载端点。

**测试**

- 第一次请求即可成功，不依赖预热；
- 最终路径 `/mcp` 成功，`/mcp/mcp` 不存在；
- 错误 Host 返回安全错误，正式 Host 成功；
- 父应用 shutdown 后 MCP 后台资源关闭；
- 既有 API startup/shutdown 回归通过。

---

## 4. Phase 2 · 可重置评测沙箱

### Task 2.1：持久运行记录和 lease

**修改/新增**

- 现有数据库 schema 初始化/迁移代码
- `src/refineq/mcp/sandbox.py`
- `tests/unit/test_mcp_sandbox_repository.py`
- `tests/integration/test_mcp_sandbox_lifecycle.py`

**数据模型**

`mcp_evaluation_runs` 至少包含：

```text
id
run_id_hash UNIQUE
client_run_key_hash
principal_id
status              # seeding | active | completed | released | expired | failed
seed_version
created_at
updated_at
expires_at
last_error_code
```

`mcp_evaluation_idempotency` 至少包含：

```text
principal_id
run_id_hash
tool_name
idempotency_key_hash
input_hash
result_json
created_at
retain_until
```

唯一约束：

- `(principal_id, client_run_key_hash)` 唯一；
- 同一评测 owner 同时最多一个 `seeding|active` 运行；
- `(principal_id, run_id_hash, tool_name, idempotency_key_hash)` 唯一；
- 不存储明文 run token 或 secret；run token 使用密码学安全随机数，数据库只保存哈希。

**并发测试**

- 同一 key 的 20 个并发请求只创建一个运行；
- 不同 key 并发时一个成功，其他返回 `demo_busy`；
- 过期运行被回收后可创建新运行；
- 同一 key 不同 input hash 返回 idempotency conflict；
- 底层沙箱被下一轮重置后，保留期内的旧请求仍从结果记录稳定重放；
- 进程在 `seeding` 中崩溃后能恢复为 failed/idle；
- 不跨请求持有 transaction、文件锁或连接。

### Task 2.2：独立评测账号和确定性重置

**修改/新增**

- `src/refineq/operations/demo.py`
- `src/refineq/mcp/sandbox.py`
- `tests/integration/test_mcp_sandbox_reset.py`
- `.env.example`

**要求**

- 使用独立于普通 Web 演示账号的评测账号；
- 部署时预先播种固定 workspace 和至少一份 indexed material；
- MCP 不提供资料写工具，因此每轮只重置学习状态，不重复写对象和索引；
- baseline 明确版本化为 `seed_version`；
- 重置 learning、pending question、evidence、plan session、review、journey event 和 coach session；
- workspace 和 material 必须在重置前后重新验证；
- 重置要么完整成功并激活 run，要么完整失败且不留下半重置 active run；
- 不允许通过登录普通 Web 页面修改评测账号。

不要直接调用当前“只补缺、不重置”的 `seed_demo()` 假装完成隔离。应抽取共享的 deterministic seed builder，并为评测增加显式 reset use case。

**测试**

- 两次不同运行的初始 context 完全一致；
- 第一轮提交答案后，第二轮看不到第一轮 pending/evidence/mastery；
- 资料对象和索引不因重置重复创建；
- 重置中途故障后下一次调用可以恢复；
- 普通 demo owner 和真实 owner 状态没有变化。

### Task 2.3：`refineq_begin_demo`

**修改/新增**

- `src/refineq/mcp/tools.py`
- `tests/integration/test_mcp_begin_demo.py`
- 协议 schema snapshot

**实现**

- 输入 `client_run_key`，长度和字符集有界；
- 调用 sandbox service 创建/恢复运行；
- 返回不透明的密码学安全随机 run token；
- 输出固定空间摘要、TTL、`simulation=true` 和 runtime 配置状态；
- 只报告 `configured` 和最近一次 observed status；无 canary 时为 stale；
- `next_tool=refineq_get_learning_context`。

**幂等测试**

- 同一 key 重放返回同一 run 和相同 baseline；
- 重试不重复重置；
- key 复用但输入/seed_version 冲突返回稳定错误；
- run token 伪造和篡改失败。

---

## 5. Phase 3 · 只读投影和检索

### Task 3.1：有界、无副作用学习投影

**新增**

- `src/refineq/mcp/projections.py`
- `tests/unit/test_mcp_projections.py`
- `tests/integration/test_mcp_read_side_effects.py`

**实现**

投影组合既有 owner-scoped repositories/只读服务，只返回：

- 固定 workspace 摘要；
- 最多 8 个 topic；
- 最多 8 个今日 plan session；
- pending question 摘要；
- material 数量和索引状态；
- 最新证据摘要；
- next action；
- `state_version`。

禁止：

- 调用写 journey event 的 snapshot；
- 返回 chunk 全文；
- 返回无界 evidence、sessions 或 materials；
- 在读路径创建默认 learning record；
- 用异常来探测其他 owner 是否存在。

**测试**

- 调用前后所有 record version 和 event count 不变；
- 数据超限时确定性截断并返回 `truncated=true`；
- 跨 owner/run 返回 `run_not_found` 或资源不存在；
- projection 结果的 `state_version` 可用于 submit precondition。

### Task 3.2：`refineq_get_learning_context`

**修改/新增**

- `src/refineq/mcp/tools.py`
- `tests/integration/test_mcp_learning_context.py`

**实现**

- 每次调用先验证 principal、run 和 TTL；
- 调用 projection；
- 返回正式 `CallToolResult` 和 schema；
- annotations：read-only、idempotent、closed-world；
- 响应上限 16 KiB。

**测试**

- baseline 中存在目标、计划、资料和下一行动；
- 调用不续期、不重置、不写事件；
- expired run 的恢复建议是重新 `begin_demo`；
- text fallback 不泄露完整结构或资料正文。

### Task 3.3：`refineq_search_materials`

**修改/新增**

- `src/refineq/mcp/tools.py`
- `tests/integration/test_mcp_search_materials.py`

**实现**

- 复用 `KnowledgeIndex` 的 owner/workspace-scoped 检索；
- `limit` 1～8；
- excerpt 每条最多 400 Unicode 字符；
- 总响应不超过 8 KiB；
- 返回稳定 citation id、filename、score 和 retrieval mode；
- embedding 不可用或超时后走 lexical；
- 检索内容仅进入引用数据区，不能进入系统指令和 answer-key 编译。

**对抗测试**

- 恶意资料中的权限、删除、满分和 expected-answer 指令不起作用；
- 跨 workspace/run 不能检索；
- 超长 Unicode、空 query 和极端 limit 有确定错误；
- fallback 与 hybrid 都返回真实存在的 citation。

---

## 6. Phase 4 · 练习闭环

### Task 4.1：`refineq_get_practice_task`

**修改/新增**

- `src/refineq/mcp/tools.py`
- 必要时为现有 LearningService 增加适配友好的 use case 方法
- `tests/integration/test_mcp_practice_task.py`

**实现**

- 必填 `request_id`；
- 验证 run 后使用沙箱 owner 调用现有 workspace question 路径；
- 复用 pending question；
- 最终校验 `grounding="material"` 且 sources 非空；
- AI 预算耗尽时走确定性、资料约束 fallback；
- 返回 `question_id`、topic、prompt、citations、mode 和 `state_version`；
- 不把资料文本直接晋升为 answer key；
- handler 不自行拼题或写 learning repository。

**测试**

- 同一 `request_id` 重放返回相同问题；
- 20 个并发同 key 只产生一个 pending question；
- 已存在 pending 时不重复调用模型；
- 无资料/资料无可用引用返回 `material_required`；
- 模型超时后的迟到结果不能覆盖 fallback 结果；
- 问题和 citation 都属于当前沙箱。

### Task 4.2：`refineq_submit_answer`

**修改/新增**

- `src/refineq/mcp/tools.py`
- 必要时扩展 evidence provenance，但不得改变真实用户默认语义
- `tests/integration/test_mcp_submit_answer.py`

**实现**

- 必填 `attempt_id` 和 `expected_state_version`；
- 只提交当前 run 的 pending question；
- `evidence_source="mcp_relayed"`、`simulation=true`；
- 掌握变化只应用到专用评测 owner；
- 返回 applied-to-sandbox / applied-to-real-learner；
- 使用现有可信 answer-key、fallback grading、prompt-echo 和 mastery-evidence 边界；
- handler 不直接改 mastery、plan session 或 review。
- 在判分结果和幂等 replay 结果持久化后，把运行标为 completed 并释放全局评测 lease；释放失败进入可恢复状态，不能重复提交答案。

**测试**

- 同一 `attempt_id` 重放只有一条 evidence 和一次状态变化；
- 同 key 不同答案返回 idempotency conflict；
- stale state version 不提交；
- 跨 run question id 不存在；
- prompt 原样复制、轻微改写和通用 filler 都不能形成可信 mastery evidence；
- 模型评分失败时 fallback 不接受资料注入定义的 answer key；
- 返回值明确真实用户状态没有改变。
- 成功提交后其他工具不再接受该 run，但同一 `attempt_id` 的重放仍返回原结果；
- 提交与释放之间故障时，恢复后既不会重复证据，也不会永久占用沙箱。

### Task 4.3：完整沙箱闭环

**新增**

- `tests/integration/test_mcp_learning_loop.py`

**场景**

1. 开始运行；
2. 读取初始 context；
3. 检索一个知识点；
4. 取得资料约束问题；
5. 提交正确答案；
6. 从提交结果验证 evidence、沙箱 mastery 和 next action 发生一致变化；
7. 验证运行 completed 且 lease 已释放；
8. 使用新 run 重置；
9. 验证初始状态恢复且第一轮无泄漏。

同一场景必须分别在：

- 模型可用模式；
- 模型禁用的 deterministic fallback 模式；
- 外部模型超时模式

下通过。

---

## 7. Phase 5 · 公网部署和可观测性

### Task 5.1：Caddy 路由

**修改**

- `infra/Caddyfile`
- `tests/contract/test_mcp_reverse_proxy.py` 或扩展现有 `tests/contract/test_deployment.py`

**要求**

- `/mcp` 独立 handle，不受 `/api/*` 的 path stripping 影响；
- 保留 Authorization；
- 支持 Streamable HTTP；
- 设置与工具预算一致的代理超时；
- 只允许 HTTPS；
- 不能把 MCP 请求回退到 Next.js。

**验证**

- `/mcp` 是唯一正式 MCP 地址；
- `/mcp/mcp`、`/api/mcp` 和 Web fallback 均不误成功；
- 正确和错误 Host 行为与应用 transport security 一致。

### Task 5.2：可观测性和隐私

**修改/新增**

- MCP 日志/指标装配
- `tests/integration/test_mcp_observability.py`

**指标**

- tool calls、成功/业务错误/系统错误；
- P50/P95/P99；
- AI/fallback 比例；
- `demo_busy`、run expiry、reset failure；
- idempotency replay/conflict；
- response size；
- protocol version 和匿名 client 类别。

**禁止记录**

- Authorization；
- run token 或 client run key；
- 学习资料正文；
- 题面和答案；
- owner id、邮箱；
- 模型 prompt 和完整响应。

测试通过日志捕获和 secret scanner 证明禁止字段不存在。

### Task 5.3：运行手册和 README

**修改/新增**

- `README.md`
- `docs/operations/mcp.md`
- `docs/operations/mcp-compatibility.md`
- `.env.example`

文档必须说明：

- endpoint 和认证；
- 支持的协议版本；
- 5 个工具和推荐调用顺序；
- `begin_demo`、TTL、completed 自动释放、`demo_busy` 和重置语义；
- `simulation=true` 和 evidence provenance；
- 模型/embedding 降级；
- 错误码和恢复动作；
- 限流；
- 不支持 Tasks、Elicitation、Resources、Prompts、资料上传和真实用户接入；
- 密钥轮换和故障排查。

### Task 5.4：公网 E2E

**新增**

- 可在 CI 控制环境运行时新增 `tests/contract/test_mcp_public_smoke.py`；否则提供受控脚本 `scripts/mcp_smoke.py`

**要求**

- 使用官方 SDK client；
- 通过实际 HTTPS 域名和 Caddy；
- 不导入服务端 Python 模块；
- 运行完整总体验收路径；
- 校验 output schema、引用、幂等 replay、fallback 标记和第二轮重置；
- 打印结果摘要但不打印 secret、run token、答案或资料正文。

---

## 8. Phase 6 · 全量验证与交付门

### Task 6.1：目标测试

```powershell
python -m pytest tests/unit/test_mcp_contracts.py -q
python -m pytest tests/integration/test_mcp_auth.py -q
python -m pytest tests/integration/test_mcp_sandbox_lifecycle.py -q
python -m pytest tests/integration/test_mcp_learning_loop.py -q
python -m pytest tests/contract/test_mcp_protocol.py -q
python -m pytest tests/contract/test_mcp_transport.py -q
```

文件名应按仓库实际测试布局调整，但不得把协议测试降级为直接函数测试。

### Task 6.2：后端全量质量门

```powershell
python -m pytest
python -m ruff check src tests
python -m ruff format --check src tests
python -m pip check
```

### Task 6.3：前端和部署回归

即使 MCP 没有新增前端，也必须证明 FastAPI lifespan、Caddy 和 Compose 改动没有破坏现有产品：

```powershell
Set-Location apps/web
npm test
npm run lint
npm run build
npm run test:e2e
```

然后回到仓库根目录运行现有 deployment/operations 测试。

### Task 6.4：人工验收

由未参与实现的人执行：

1. 在一台没有本地源码上下文的客户端中配置 endpoint 和 secret；
2. 只根据 `server/discover`、tool descriptions 和错误提示完成闭环；
3. 重复运行两次，确认 baseline 一致；
4. 中途重复同一请求，确认幂等；
5. 禁用模型后重新运行，确认 fallback 完整；
6. 检查 Web 中真实账号没有出现评测证据或状态变化；
7. 检查日志没有敏感正文。

只有人工验收者无需口头指导即可完成，才算“Agent 能够连通”。

---

## 9. 逐提交建议

为便于回滚和审查，建议按以下边界提交；实际提交前每一项必须通过对应测试：

1. `build: add the verified MCP SDK v2`
2. `feat: add the MCP protocol and transport skeleton`
3. `feat: add MCP authentication and typed settings`
4. `feat: add the resettable evaluation sandbox`
5. `feat: expose bounded learning context and material search`
6. `feat: expose the idempotent MCP practice loop`
7. `ops: publish and verify the MCP endpoint`
8. `docs: document MCP compatibility and operations`

不要把依赖、数据库迁移、5 个工具、部署和文档压成一个无法审查的大提交。

---

## 10. 失败处理和回滚

### 10.1 协议兼容失败

- 停在 Phase 0；
- 保留兼容性记录；
- 不合入未被目标客户端消费的业务工具；
- 比赛改走源码 ZIP 路径。

### 10.2 沙箱不可靠

如果重置、TTL 回收、幂等或并发隔离任一项不能证明：

- 不开放写工具；
- 可以临时只交付 context/search 的只读 MCP，但必须明确它不能展示完整闭环；
- 不退回共享、可变、无 lease 的服务账号。

### 10.3 外部模型不稳定

- 保留确定性 fallback；
- 不扩大超时；
- 不引入临时后台线程；
- 不让迟到结果提交；
- `mode` 必须如实返回。

### 10.4 部署失败

- `REFINEQ_MCP_ENABLED=false` 可关闭挂载；
- 不影响现有 Web/API；
- Caddy 路由可单独回滚；
- secret 发生泄露时先轮换并吊销旧值，再排查日志和客户端配置。

---

## 11. Phase B 前置清单（本计划不实施）

### 11.1 资料写工具

只有完成以下事项后才能设计 `refineq_add_material`：

- 抽取 Web/MCP 共用的 `MaterialIngestionService`；
- 覆盖文本与文件标准化、配额、对象存储、索引和 canonical link；
- 所有 attach/unlink/delete 使用一致 mutation lease；
- commit 前重验 workspace/material owner；
- crash recovery 和补偿测试完成；
- 上传拥有幂等键和稳定 replay。

### 11.2 用户级 MCP

- OAuth 2.1 或用户级可撤销 token；
- scope；
- owner、资源和 idempotency 记录绑定；
- token 撤销和账号生命周期；
- private resource cache scope；
- 安全审计和速率限制。

### 11.3 Tasks

- task repository/table；
- durable create before response；
- worker、lease 和 recovery；
- principal/scope 绑定；
- get/update/cancel；
- TTL cleanup；
- sync/task 相同幂等结果；
- crash-before/after-commit、cancel-before-commit 和跨用户 task id 对抗测试。

在这些能力真正落地前，`server/discover` 不得声明 Tasks。

### 11.4 Elicitation、Resources、Prompts

- Elicitation 仅解决交互输入，不证明真人作者；
- Resources 必须有私有缓存、TTL、分页和响应上限；
- Prompts 必须在目标客户端证明能改善发现和成功率；
- 需要强保证的多步流程应优先做成服务端 workflow tool，而不是依赖宿主模型遵循 prompt。

---

## 12. Definition of Done

Phase A 只有在以下全部为真时才允许标记完成或合并：

- [ ] 官方 SDK v2 精确版本和哈希已锁定；
- [ ] 兼容性 Spike 记录了实际客户端证据；
- [ ] `server/discover` 和 `tools/list` 经真实 SDK client 验证；
- [ ] 只声明 5 个 MVP 工具；
- [ ] FastAPI lifespan、mount path、allowed hosts 和 Caddy 均通过测试；
- [ ] 认证默认关闭、启用时 fail closed、凭据不泄露；
- [ ] 评测沙箱可重置、串行、过期、恢复且与真实用户隔离；
- [ ] 所有写工具幂等，并有状态冲突保护；
- [ ] 只读工具无事件或 record version 副作用；
- [ ] 所有工具有 output schema、annotations、响应上限和稳定错误码；
- [ ] MCP 作答明确是模拟，不污染真实 mastery；
- [ ] 模型可用、模型禁用和模型超时三种闭环都通过；
- [ ] 公网 HTTPS E2E 通过；
- [ ] Python 全量测试、ruff、pip check 全绿；
- [ ] Vitest、ESLint、Next build、Playwright 和部署回归全绿；
- [ ] README、运行手册和兼容性矩阵完成；
- [ ] 独立验收者无需实现者提示即可跑通。

“本地 handler 单测通过”“Inspector 能列出工具”或“共享账号手工跑过一次”都不等于完成。

# MCP 服务实施计划

> **For implementation agents:** Use `superpowers:executing-plans` to implement this plan task-by-task.

**Goal:** 让 RefineQ 通过 MCP 暴露学习闭环，使评测平台能直接调用并跑通「说目标 → 加资料 → 取题 → 作答 → 判分」，且零模型环境下依然可用。

**Architecture:** MCP 服务与 FastAPI **同进程**，直接调用既有应用服务层（`workspace_service` / `learning_service` / `agent_service`），不经 HTTP 自调用——这样复用全部既有不变量（owner 强制、幂等键、事务边界、确定性降级），也绕开按 IP 计的写限流。新增 `src/refineq/mcp/` 领域模块；读路径一律走新建的只读投影，绝不转发有写副作用的 `snapshot`。

**Tech Stack:** Python 3.12 · FastAPI · MCP Python SDK（协议版本 `2026-07-28`）· pytest

**设计文档：** [2026-08-09-mcp-service-design.md](2026-08-09-mcp-service-design.md)（工具/资源/模板清单、认证、延迟预算、安全边界均在该文，本文只讲怎么做）

---

## 常用命令（Windows PowerShell，仓库根目录）

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pytest tests/unit/mcp -q
.\.venv\Scripts\python.exe -m ruff check src tests
.\.venv\Scripts\python.exe -m ruff format src tests
.\.venv\Scripts\python.exe scripts\scan_secrets.py
```

**每个任务结束必须提交**，`feat:` / `fix:` / `test:` 前缀，署名 `QingJ01 <qingj1314@163.com>`。

**当前基线：** `8544130`，后端 405 passed / 3 skipped，ruff 与密钥扫描通过。

---

# Phase 0 · 前置阻塞项

这三项不做完，后面的任务无法开始或会带病上线。

## Task 0.1: 安装 uv 并验证锁文件可重生成

加 `mcp` 依赖必须重生成三个带哈希的锁文件（`requirements.lock` 有 1168 条哈希），而本机没有 uv。

**Step 1: 安装**

```powershell
.\.venv\Scripts\python.exe -m pip install uv
.\.venv\Scripts\uv --version
```

**Step 2: 先验证现状可复现（不加依赖）**

```powershell
.\.venv\Scripts\uv pip compile pyproject.toml --generate-hashes --output-file requirements.check.lock
```

用文本比对 `requirements.check.lock` 与 `requirements.lock`：除注释行外应无差异。有差异说明本机 uv 版本与生成时不同，**先解决这个再往下走**，否则会把无关升级混进锁文件。

**Step 3: 确认后删除临时文件**

```powershell
Remove-Item requirements.check.lock
```

**验收：** 能复现出与现有锁文件一致的内容。
**若失败：** 退路是不引入 SDK、手写最小 JSON-RPC 服务端（工作量上升但可控），此时跳过 Task 0.2。

## Task 0.2: 加入 MCP SDK 依赖

**Files:** `pyproject.toml`、`requirements.lock`、`requirements-dev.lock`、`requirements-build.lock`

**Step 1: 在 `pyproject.toml` 的 `dependencies` 增加**

```toml
    "mcp>=1.2.0,<2.0.0",
```

**Step 2: 重生成三个锁文件**

```powershell
.\.venv\Scripts\uv pip compile pyproject.toml --generate-hashes --output-file requirements.lock
.\.venv\Scripts\uv pip compile pyproject.toml --extra dev --generate-hashes --output-file requirements-dev.lock
```

`requirements-build.lock` 若无变化则不动。

**Step 3: 安装并验证**

```powershell
.\.venv\Scripts\python.exe -m pip install --require-hashes -r requirements.lock
.\.venv\Scripts\python.exe -c "import mcp; print(mcp.__version__)"
```

**Step 4: 全量回归 + 提交**

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Expected: 405 passed, 3 skipped（依赖变更不应影响任何测试）

```bash
git add pyproject.toml requirements*.lock
git commit -m "build: add the MCP SDK dependency"
```

## Task 0.3: 准备已播种的评测账号

**Files:** `.env.example`、`docs/deployment.md`

设计文档 §5.1 的硬要求：评测方没有资料也不会真答题，绑到空账号会在第一次 `get_practice_task` 撞 `material_required` 停住。

**Step 1: `.env.example` 增加三个变量并写清用途**

```
# MCP 评测端点绑定的学习者账号（必须已执行 seed_demo）
REFINEQ_MCP_ACCOUNT_EMAIL=
REFINEQ_MCP_ACCOUNT_PASSWORD=
# 调用方访问 /mcp 所需的共享密钥
REFINEQ_MCP_SHARED_SECRET=
```

**Step 2: `docs/deployment.md` 增加一节**，说明部署后必须：创建该账号 → 对其执行 `seed_demo` → 用 §Phase 4 的验收命令确认 `get_practice_task` 直接可用。

**Step 3: 提交**

```bash
git commit -m "docs: define the MCP evaluation account contract"
```

---

# Phase 1 · 协议骨架

## Task 1.1: 建立模块骨架与只读投影

**Files:**
- Create: `src/refineq/mcp/__init__.py`
- Create: `src/refineq/mcp/projections.py`
- Test: `tests/unit/mcp/test_projections.py`

投影层是整个服务的地基：**它保证读操作没有写副作用、体积有界**。设计文档记录了 `GET /snapshot` 会写 journey event 且返回全量 evidence/materials/chunk 全文，所以不能转发它。

**Step 1: 写失败测试**

```python
"""Read projections must be side-effect free and bounded."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from refineq.api.app import create_app
from refineq.config import Settings
from refineq.mcp.projections import space_state, space_summaries


def test_space_summary_is_bounded_and_has_no_chunk_text(tmp_path: Path) -> None:
    app = create_app(Settings(data_root=tmp_path / "data", _env_file=None))
    with TestClient(app) as client:
        owner_id, workspace_id = _seed_workspace_with_material(app, client)
        before = len(app.state.journey_events.list(owner_id, workspace_id))

        summaries = space_summaries(app.state, owner_id)

        after = len(app.state.journey_events.list(owner_id, workspace_id))

    assert after == before, "读投影不得写 journey event"
    assert summaries[0].id == workspace_id
    serialized = summaries[0].model_dump_json()
    assert "chunk" not in serialized.lower()
    assert len(serialized) < 2_000


def test_space_state_omits_source_text(tmp_path: Path) -> None:
    app = create_app(Settings(data_root=tmp_path / "data", _env_file=None))
    with TestClient(app) as client:
        owner_id, workspace_id = _seed_workspace_with_material(app, client)
        before = len(app.state.journey_events.list(owner_id, workspace_id))

        state = space_state(app.state, owner_id, workspace_id, detail="full")

        after = len(app.state.journey_events.list(owner_id, workspace_id))

    assert after == before
    assert state.material_count == 1
    assert "如果矩阵" not in state.model_dump_json(), "投影不得回传资料正文"
```

`_seed_workspace_with_material` 参照 `tests/integration/test_learning_journey.py` 的注册 + `/workspaces/resolve` + 上传写法自行实现。

**Step 2: 确认失败**

Run: `.\.venv\Scripts\python.exe -m pytest tests/unit/mcp -q`
Expected: `ModuleNotFoundError: refineq.mcp.projections`

**Step 3: 实现投影**

`projections.py` 提供两个纯读函数，内部只调用既有仓储与 `select_next_action`，**不得**调用 `workspace_service.snapshot()`：

```python
class SpaceSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str
    title: str
    goal: str
    exam_at: datetime | None = None
    days_left: int | None = None
    mastery_avg: float
    material_count: int
    next_action: NextActionSummary


def space_summaries(state, owner_id: str) -> list[SpaceSummary]: ...
def space_state(state, owner_id: str, space_id: str, *, detail: str = "concise"): ...
```

**候选上限 8**（设计文档 §6.3）：`space_summaries` 按 `last_active_at` 倒序截断，并在返回里带 `truncated: bool`。

**Step 4: 验证并提交**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/mcp -q
```

```bash
git add src/refineq/mcp tests/unit/mcp
git commit -m "feat: add side-effect free MCP read projections"
```

## Task 1.2: 服务账号认证

**Files:**
- Create: `src/refineq/mcp/auth.py`
- Test: `tests/unit/mcp/test_auth.py`

JWT 只有 12 小时且改密即失效，所以 MCP 自己维护身份：进程内解析服务账号，401 时刷新。

**Step 1: 写失败测试**

```python
def test_resolves_owner_from_configured_account(tmp_path: Path) -> None:
    ...
    resolver = ServiceAccountResolver(app.state, email=email, password=password)
    assert resolver.owner_id() == expected_user_id


def test_missing_configuration_is_reported_clearly(tmp_path: Path) -> None:
    resolver = ServiceAccountResolver(app.state, email=None, password=None)
    with pytest.raises(McpAccountNotConfiguredError) as excinfo:
        resolver.owner_id()
    assert "REFINEQ_MCP_ACCOUNT_EMAIL" in str(excinfo.value)
```

**Step 2-4:** 同进程直接用 `app.state.identity` 校验凭据取 `user.id` 并缓存；**不要**签发或存储 JWT——同进程调用服务层不需要 token。错误信息要指明缺哪个环境变量。

**Step 5: 提交**

```bash
git commit -m "feat: resolve the MCP service account in process"
```

## Task 1.3: `server/discover` 与工具列表

**Files:**
- Create: `src/refineq/mcp/server.py`、`src/refineq/mcp/tools.py`
- Test: `tests/unit/mcp/test_server_contract.py`

`server/discover` 是规范**强制**服务端实现的，v1/v2 设计漏了。

**Step 1: 写失败测试**

```python
def test_discover_declares_only_implemented_capabilities() -> None:
    server = build_server(...)
    discovered = server.discover()

    assert "2026-07-28" in discovered.supported_versions
    assert discovered.capabilities.tools is not None
    assert discovered.capabilities.resources is not None
    assert discovered.capabilities.prompts is not None


def test_tool_names_use_the_underscore_prefix() -> None:
    names = {tool.name for tool in list_tools()}
    assert names == {
        "refineq_get_capabilities",
        "refineq_list_learning_spaces",
        "refineq_get_space_state",
        "refineq_start_learning",
        "refineq_add_material",
        "refineq_search_materials",
        "refineq_get_practice_task",
        "refineq_submit_answer",
        "refineq_ask_coach",
        "refineq_update_plan_session",
    }
    assert all(tool.title and tool.description for tool in list_tools())
```

**声明什么就必须真支持什么**——不要为了好看在 discover 里声明未实现的能力。

**Step 2-4:** 实现 stdio 入口，用 MCP Inspector 手工确认握手与 `tools/list`。

**Step 5: 提交**

```bash
git commit -m "feat: expose the MCP discovery handshake and tool list"
```

---

# Phase 2 · 只读工具与资源

## Task 2.1: 四个只读工具

`refineq_get_capabilities`、`refineq_list_learning_spaces`、`refineq_get_space_state`、`refineq_search_materials`。

**关键测试（每个工具至少一条）：**

```python
def test_capabilities_report_matches_actual_behaviour(tmp_path: Path) -> None:
    """声明 healthy 的能力必须真能用；未配置模型时 coach 必须报 unavailable。"""
    result = call_tool("refineq_get_capabilities", {})
    assert result["capabilities"]["coach"]["status"] == "unavailable"
    assert result["capabilities"]["question"]["mode"] == "deterministic"


def test_search_truncates_excerpts(tmp_path: Path) -> None:
    result = call_tool("refineq_search_materials", {"space_id": ..., "query": "极限"})
    for item in result["results"]:
        assert len(item["excerpt"]) <= 400


def test_cross_owner_space_is_not_found(tmp_path: Path) -> None:
    """归属隔离：别人的 space_id 必须表现为不存在，而不是权限错误。"""
    result = call_tool("refineq_get_space_state", {"space_id": other_owner_space})
    assert result["error"]["code"] == "space_not_found"
```

**提交：** `feat: add read-only MCP tools`

## Task 2.2: 四个 Resources

`refineq://spaces`、`refineq://space/{id}/plan`、`refineq://space/{id}/evidence`、`refineq://space/{id}/materials`。

**关键测试：**

```python
def test_evidence_resource_is_capped_at_fifty_entries(...) -> None: ...
def test_materials_resource_excludes_body_text(...) -> None: ...
def test_reading_a_resource_writes_no_journey_event(...) -> None: ...
def test_resource_of_another_owner_is_not_found(...) -> None: ...
```

**提交：** `feat: publish learning state as MCP resources`

---

# Phase 3 · 闭环写工具

## Task 3.1: 五个写工具

`refineq_start_learning`、`refineq_add_material`、`refineq_get_practice_task`、`refineq_submit_answer`、`refineq_update_plan_session`。

**幂等键在 MCP 层一律必填**（HTTP 层 `turn_id` 是可选的，这里收紧）。

**关键测试：**

```python
def test_practice_task_is_idempotent_by_request_id(...) -> None:
    first = call_tool("refineq_get_practice_task", {..., "request_id": "r1"})
    second = call_tool("refineq_get_practice_task", {..., "request_id": "r1"})
    assert first["question_id"] == second["question_id"]


def test_submit_answer_replays_by_attempt_id(...) -> None:
    """同一 attempt_id 只产生一条证据。"""


def test_answer_source_is_recorded_as_mcp_relayed(...) -> None:
    result = call_tool("refineq_submit_answer", {..., "answer": "..."})
    assert result["source"] == "mcp_relayed"


def test_added_material_never_becomes_an_instruction(...) -> None:
    """注入样本进资料后，出题与判分都不受其指令影响。"""
    call_tool("refineq_add_material", {..., "content": INJECTION_SAMPLE})
    task = call_tool("refineq_get_practice_task", {..., "request_id": "inj"})
    assert "PWNED" not in task["prompt"]
```

最后一条与 `8544130` 的 P0-5 修复配套——MCP 是新的资料入口，必须在协议层再证一次。

**提交：** `feat: add the MCP learning-loop tools`

## Task 3.2: 证据来源标记

**Files:** `src/refineq/learning/service.py`、`src/refineq/learning/models.py`、前端证据台账组件

设计文档 §8 决策一：来源分三档 `web` / `mcp_elicited` / `mcp_relayed`，**且必须在台账 UI 显示**——不显示等于没标注。

**测试：** 后端断言字段落库与回显；前端组件测试断言两种 MCP 来源分别渲染出对应文案。

**提交：** `feat: record and surface answer provenance`

---

# Phase 4 · Tasks 与 Elicitation

## Task 4.1: Tasks 扩展（双路径）

长耗时调用不能阻塞——客户端与中间代理的超时会造成"前端报失败、服务端已提交"，这是全产品审查 P0-4 记录的真实故障。规范已有 `io.modelcontextprotocol/tasks`。

**必须实现双路径**：客户端声明支持才返回 `CreateTaskResult`；未声明则同步返回并遵守设计文档 §6 的超时预算。

**关键测试：**

```python
def test_task_is_not_returned_to_clients_without_the_capability(...) -> None:
    """规范硬性要求：绝不能给未声明支持的客户端返回 task。"""


def test_same_attempt_id_yields_one_evidence_across_both_paths(...) -> None:
    """同步路径与 task 路径的幂等语义必须一致。"""
```

**提交：** `feat: carry long-running MCP calls as tasks`

## Task 4.2: Elicitation 索取本人作答

把「不要替学习者答题」从提示词约束升级为协议级约束：客户端支持 Elicitation 时，`answer` 留空，服务端返回 `InputRequiredResult` 让**学习者本人**填表单。

**关键测试：**

```python
def test_elicits_the_answer_when_the_client_supports_it(...) -> None:
    result = call_tool("refineq_submit_answer", {..., "answer": None})
    assert result["inputRequests"][0]["method"] == "elicitation/create"


def test_elicited_answer_is_recorded_as_mcp_elicited(...) -> None: ...


def test_falls_back_to_direct_answer_without_elicitation_support(...) -> None:
    assert result["source"] == "mcp_relayed"
```

**注意（规范要求）：** form 模式不得索取密码、令牌等敏感信息。本服务只索取学习作答，符合约束。

**提交：** `feat: elicit the learner's own answer over MCP`

---

# Phase 5 · Prompts 与部署

## Task 5.1: 四个 Prompt 模板

`start_today`、`quiz_me`、`explain_with_my_materials`、`weekly_review`。

**`quiz_me` 必须内嵌**：「把题目呈现给学习者本人并等待 TA 的回答，不要自己写答案」。

**验收：** 在 MCP 客户端选择 `quiz_me`，**不手工指定任何工具顺序**即可完成"出题 → 用户作答 → 判分 → 掌握度变化"。

**提交：** `feat: ship MCP prompt templates for the learning loop`

## Task 5.2: Streamable HTTP 与 Caddy

**Files:** `src/refineq/api/app.py`、`infra/Caddyfile`、`README.md`

挂 `/mcp`，共享密钥头鉴权。**Caddy 注意**：现有 `handle_path /api/*` 会剥前缀，`/mcp` 需要独立 `handle`，不要复用那条规则。

README 增加 MCP 章节：端点地址、鉴权方式、工具/资源/模板清单、示例调用。

**提交：** `feat: serve MCP over streamable HTTP`

## Task 5.3: 部署验收

按设计文档 §5.1 与 §12 逐条核对。**最关键的一条**：

```
不做任何前置操作，直接调 refineq_get_practice_task
→ 必须返回一道带资料引用的题（证明服务账号已播种）
```

其余：外网客户端能连上并跑通闭环；冷启动到首个工具响应 ≤ 10 秒；各工具耗时落在 §6 预算内。

---

# 完成定义

- 10 工具 / 4 资源 / 4 模板全部可列出可调用，工具描述四段齐备。
- 零模型下 9 个工具可用，`ask_coach` 明确报 `model_not_configured` 并说明其余可用。
- 一键可用：选 `quiz_me` 即可完成闭环。
- 归属隔离：工具参数无 `owner_id`；跨用户表现为不存在。
- 注入资料不产生副作用，且不进入 `expected_answer`。
- 三个写工具幂等键必填，同步与 task 两条路径语义一致。
- 日志不含参数正文、返回正文与凭据。
- 全量验收：pytest / ruff / 密钥扫描 / vitest / eslint / build / Playwright + 新增 MCP 测试全绿。

# 风险

| 风险 | 对策 |
| --- | --- |
| uv 不可用 | Task 0.1 先验证；退路是手写最小 JSON-RPC，跳过 SDK |
| 评测账号被改密或"退出所有会话" | 专用账号、部署后不再登录 Web |
| 平台调用产生真实模型费用 | MCP 侧写操作限流 60/分钟；降级路径本身可用 |
| 时间不足 | Phase 1–3（stdio）即可交付本地可验证的 MCP；Phase 4–5 是增量 |

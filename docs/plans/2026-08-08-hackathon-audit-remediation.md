# 黑客松审查 · 剩余工作与解决方案

> 审查日期：2026-08-08 · 审查基线：`a92b180` · 已完成基线：`ae14046`
> 上一轮前端审查：[2026-08-08-frontend-audit-findings.md](2026-08-08-frontend-audit-findings.md)（F-01…F-40，P0 已由 PR #6 修复）
> 本轮视角：黑客松评分规则（[HACKATHON.md](../../HACKATHON.md)）+ 产品八步体验闭环

本文只管**代码**。部署、访谈、提交材料由你自己安排，清单在最后一节备查。

## 当前状态

| 关卡 | 结果 |
| --- | --- |
| 后端 pytest | 342 passed, 3 skipped ✅ |
| 前端 vitest | 142 passed ✅ |
| Playwright E2E | 5 passed ✅ |
| ruff check / format / 密钥扫描 | 全过 ✅ |

### 已完成

**H-01 绝对日期解析**（`ae14046`）。`constraints.py` 原先只认相对日期（`N天后` / `in N days`），演示台词「10月25日考计算机组成原理期中」静默回落成 7 天计划。现已支持中文 `M月D日`、`M/D`、英文 `Oct 25`、以及 `下周` / `下个月`；日期已过则顺延到明年；非法日期（`2月30日`、`13月1日`）返回 `None` 不瞎猜；相对日期优先级高于日历日期。

实测：

```
10月25日考计算机组成原理期中，每天能学90分钟  →  exam=2026-10-25 daily=90
下周考数据库系统                            →  exam=2026-08-15
12月20日考研                               →  exam=2026-12-20
2月30日考试                                →  exam=None
```

---

# A 组 · 演示直接相关

## A-02 首页与 README 仍用被赛制点名的宽泛画像

**证据：** `README.md:3` "面向高中生、大学生和高级学习者的个人学习 Agent"；`apps/web/lib/i18n.ts:18,19`（中）与 `:213,214`（英）。

`HACKATHON.md:290` 与 §8.4 第 5 条把这类表述列为硬性要求违规；[01-positioning.md:21](../product/01-positioning.md#L21) 两天前已标红，[05-roadmap.md](../product/05-roadmap.md) 列为 P0-2，至今未改。

**解决方案（不依赖访谈，先把违规表述去掉）：**

`README.md` 首段改为描述**具体处境**而非受众标签：

> RefineQ（砺问）是一个个人学习 Agent，为"手里有自己的讲义和笔记、有明确考试日期、但说不清自己到底掌握了多少"的备考者而做。通用聊天工具记不住这些资料，也不会主动出题验证掌握情况。RefineQ 接住完整链路：说明目标、上传资料、生成计划、主动练习、结构化判分、积累掌握证据。它不把"聊过了"当成"学会了"。

访谈完成后，再把首句替换成「RefineQ 最初为【化名】设计。TA 是……」。

`i18n.ts` 四条（中英各二）：

| 键 | 改为（zh） | 改为（en） |
| --- | --- | --- |
| `learningPromptHint` | 说清目标和时间，RefineQ 会建立你的学习空间：资料、计划、练习和掌握证据都留在这里。 | Tell it your goal and deadline. RefineQ opens a space that keeps your sources, plan, practice, and mastery evidence together. |
| `learningIntentPlaceholder` | 例如：10月25日考计算机组成原理期中，每天能学90分钟，先补流水线和缓存…… | For example: final exam Oct 25, 90 minutes a day, start with pipelining and caches… |

placeholder 现在可以放心用绝对日期——H-01 已让系统真的解析得出来。

**验收：** `npm test` 通过；输入 placeholder 示范句，路由结果标题为「计算机组成原理」，计划终点是 10 月 25 日而非 7 天后。

**注意：** `apps/web/tests/contracts.test.ts` 可能断言了旧文案，改完一起跑。

## A-03 前后端"最弱主题"平局规则不一致

**证据：** 后端 `learning/service.py:739-745` 用 `min(topics, key=(p_mastery, topic_id))`，平局按 `topic_id` 字典序，而 topic_id 是 `topic_<sha256前16位>`（伪随机）；前端 `progress-insights.tsx:29-31` 用 `.sort((l, r) => l[1] - r[1])` 取 `[0]`，平局保留 `Object.entries` 的插入顺序。

Day 0 所有主题掌握度同为 0.2 时，**界面推荐 A、点击后出的是 B 的题**。评委点两个按钮就能看到。

**解决方案：** 前端排序对齐后端，改为按 `(mastery, topicId)` 二级排序：

```typescript
const topics = Object.entries(progress?.mastery ?? {})
  .sort((left, right) => left[1] - right[1] || left[0].localeCompare(right[0]));
```

**验收：** 新增组件测试——构造两个 mastery 相同、插入顺序与字典序相反的主题，断言推荐的是字典序靠前的那个。

---

# B 组 · 正确性缺陷

## B-01 重做同一道题可以刷高掌握度

**证据：** `retry_question`（`learning/service.py:839-875`）把历史题恢复为 pending，而 `submit_answer` 只按 `attempt_id` 去重（`:954`、`:995`），**不按 question_id 去重 BKT**。同一道题反复重做、每次换新 `attempt_id` 提交同样的正确答案：

```
0.2 → 0.60 → 0.89 → 0.977
```

难度模型明确防了这一手（`difficulty.py:22-23` 用 `question_id not in correct_ids`，还有专门测试 `test_retrying_same_question_does_not_raise_difficulty`），唯独 BKT 没防。

**解决方案：** 在 BKT 更新处复用难度模型已有的去重信号。`BKTState` 增加 `credited_question_ids: list[str]`（有界，保留最近 50 条），`submit_answer` 里：

```python
already_credited = payload.question_id in current_bkt.credited_question_ids
bkt_state = (
    update_bkt(current_bkt, is_correct=is_correct)
    if grade.mastery_evidence and not already_credited
    else current_bkt
)
```

答错不必去重（重复答错不会刷分，且惩罚重复练习不合理），只对**答对**记入 credited 列表。

**验收：** 新增测试——同一 question_id 重做三次并提交正确答案，断言掌握度只变化一次；不同 question_id 正常累积。

## B-02 难度在交替作答时永久卡死

**证据：** `difficulty.py:26-34` 每次返回都新构造 `DifficultyState`：答对时丢弃 `consecutive_wrong`，答错时丢弃 `recent_correct_question_ids`。实测「对-错」交替八次：

```
初始 2 → 2 2 2 2 2 2 2 2   （连对四次则正常升到 4）
```

**解决方案：** 两个计数器互不清零地各自维护，只在触发升降时重置对应那个：

```python
def update_difficulty(state, *, is_correct, question_id):
    if is_correct:
        if question_id in state.recent_correct_question_ids:
            return state                      # 保留既有的重做去重
        correct_ids = [*state.recent_correct_question_ids, question_id][-20:]
        streak = state.consecutive_correct + 1
        if streak >= 2:
            return state.model_copy(update={
                "level": min(5, state.level + 1),
                "consecutive_correct": 0,
                "consecutive_wrong": 0,
                "recent_correct_question_ids": correct_ids,
            })
        return state.model_copy(update={
            "consecutive_correct": streak,
            "recent_correct_question_ids": correct_ids,
        })
    streak = state.consecutive_wrong + 1
    if streak >= 2:
        return state.model_copy(update={
            "level": max(1, state.level - 1),
            "consecutive_correct": 0,
            "consecutive_wrong": 0,
        })
    return state.model_copy(update={"consecutive_wrong": streak})
```

注意"对-错-对-错"**仍然不应该改变难度**——那是正确行为（没有连续两次同向证据）。真正的 bug 是"对-对-错-对-对"这类序列里 `consecutive_correct` 被错误清零。写测试时要把这两种情况分开断言。

**验收：** 参数化测试覆盖：连对 2 次升级、连错 2 次降级、交替不变、"对-错-对-对"应在最后一次升级。

## B-03 AI 判分路径的"掌握证据"门槛不存在

**证据：** `intelligence.py:420-430` 的 AI 判分无条件返回 `mastery_evidence=True`；`GradingModelOutput`（`:43-51`）根本没有这个字段，模型从未被问"这次作答是否构成掌握证据"。只有降级路径 `fallback_grade:240` 真的算了。

后果：**配好模型后，任何一次作答都会改掌握度**。PRD §3 目标第 3 条"掌握度可信"与反向护栏"不虚增掌握度"在主路径上是空的——而这正是产品最核心的差异化主张。

**解决方案：** 给 `GradingModelOutput` 增加字段，让模型显式判定：

```python
class GradingModelOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    score: int = Field(ge=0, le=100)
    ...
    sufficient_evidence: bool = Field(
        description="True only when the answer contains enough substance to judge "
                    "the learner's mastery. False for blank, off-topic, or "
                    "'I don't know' style answers."
    )
```

提示词补一句说明，`grade_answer` 返回时 `mastery_evidence=output.sufficient_evidence`。

**验收：** 集成测试用假 transport 分别返回 `sufficient_evidence` 真/假，断言掌握度只在为真时变化。

## B-04 认证限流不覆盖密码找回

**证据：** `api/limits.py:346` 的认证白名单只有 `{"/auth/register", "/auth/login"}`，而 `/auth/password-reset/request` 与 `/auth/password-reset/complete` 走 240/min 的写操作限流——比文档承诺的 30/min 宽 8 倍，而这是最需要防爆破的接口。

**解决方案：** 一行：

```python
is_auth_request = request.url.path in {
    "/auth/register",
    "/auth/login",
    "/auth/password-reset/request",
    "/auth/password-reset/complete",
}
```

**验收：** 补一条测试，对 `/auth/password-reset/request` 连发 31 次，断言第 31 次返回 429。

## B-05 BKT 有硬地板与三题饱和（较大，建议赛后）

**证据：** 用默认参数（`p_learn=0.15 / p_guess=0.2 / p_slip=0.1`）实测：

```
连错 8 次:  0.1758 0.1721 0.1715 0.1714 0.1714 0.1714 0.1714 0.1714
连对 5 次:  0.6000 0.8903 0.9774 0.9956 0.9992
```

`bkt.py:22` 的 `learned = posterior + (1 - posterior) * p_learn` 无条件加学习项，不动点为 `p* = 0.1714`。**连错 10 次和连错 100 次在界面上完全一样**；连对 3 次就到 0.977。

同时 `mastery_is_stable()`（`bkt.py:31-44`，要求 `evidence_count >= 3` 且 `p >= 0.85`）**在 `src/` 里 0 个调用点**，只有测试引用——设计里最能支撑"不把概率当掌握"的规则没接进产品。

**解决方案（分两步，第一步低风险可现在做）：**

1. **接线 `mastery_is_stable`，界面区分"概率"与"已掌握"。** `BKTState` 增加 `evidence_count`，每次真正更新时 +1；`ProgressResponse` 增加 `stable: dict[str, bool]`；前端在掌握度条旁只有 `stable=True` 时才显示"已掌握"字样，否则显示"进行中"。**这不改变任何数值，只是不再让 97.7% 冒充"掌握"。**
2. **（赛后）调整地板。** 把学习项改为只在答对时应用，或引入随连错次数衰减的 `p_learn`。这会改变所有历史数据的语义，不适合赛前动。

**路演话术（无论是否修）：** 主动说"连续答错后掌握度会收敛到一个下界，这是 BKT 的已知特性；我们用证据计数门槛来避免把概率当成掌握"——主动说出来比被问出来强得多。

---

# C 组 · 部署与运维（代码部分）

这几项虽然服务于部署，但改的都是仓库里的代码/配置，属于本文范围。

## C-01 限流可被一个请求头绕过

**证据：** `infra/compose.yml:34` 把 `REFINEQ_FORWARDED_ALLOW_IPS` 默认设为 `*`（覆盖了 `config.py:27` 的安全默认 `127.0.0.1`），`__main__.py:16-17` 带 `proxy_headers=True`。uvicorn 在 `always_trust` 下取 `X-Forwarded-For` 的**最左值**——完全由攻击者控制——写进 `scope["client"]`，而限流器正是按 `request.client.host` 取 key（`api/limits.py:317-318`）。

**每个请求换一个 `X-Forwarded-For` 即可无限撞库**，审计日志里的 IP 也全部可伪造。公网开放注册的场景下风险不对等。

**解决方案：** 改成 Docker 默认网段，只信任反向代理：

```yaml
REFINEQ_FORWARDED_ALLOW_IPS: "${REFINEQ_FORWARDED_ALLOW_IPS:-172.16.0.0/12}"
```

`.env.example:7` 同步改并加注释说明"只应填反向代理所在网段，填 `*` 会让限流失效"。

**验收：** 补一条测试，带伪造 `X-Forwarded-For` 连续请求登录接口，断言仍会触发 429。

## C-02 健康检查公网返回 404

**证据：** `infra/Caddyfile:8-13` 用 `handle_path /api/*` 剥前缀，所以公网只有 `/api/health/live`；裸 `/health/live` 落到 `handle { reverse_proxy web:3000 }` → Next.js 无此路由 → 404。而 [06-demo-script.md:64](../product/06-demo-script.md#L64) 断言"公网可达"。

**解决方案：** Caddyfile 在 `handle_path /api/*` 之前插入健康检查直通：

```caddy
    handle /health/* {
        reverse_proxy api:8000
    }
```

**验收：** `docker compose up -d` 后 `curl -f http://localhost/health/ready` 返回 200；同步修正 06-demo-script 的表述。

## C-03 启动有约 60 秒黑窗

**证据：** `infra/Dockerfile.api:26` 与 `Dockerfile.web:36` 的 HEALTHCHECK 都是 `--interval=30s --start-period=10s`；`compose.yml:95-97,122-124` 让 web 等 api 健康、caddy 等 web 健康。首探要等一个完整 interval，于是 api ~30s → web ~30s → caddy 才绑定端口。**`up -d` 后前 60–70 秒公网端口根本没监听**，平台探测撞上就是 connection refused。

**解决方案：** 两个 Dockerfile 的 HEALTHCHECK 加 `--start-interval=2s`（Docker 25+ 支持），或把 `--interval` 降到 `5s`：

```dockerfile
HEALTHCHECK --interval=30s --start-interval=2s --start-period=30s --timeout=5s --retries=3 CMD ...
```

**验收：** 冷启动计时，从 `up -d` 到 `curl http://localhost/health/ready` 成功 ≤ 20 秒。

## C-04 演示账号在生产环境种不进去

**证据：** 三处叠加——

1. `operations/demo.py:68-69` 写死 `sqlite+pysqlite:///{data_root}/system/refineq.sqlite3`，**完全忽略 `REFINEQ_DATABASE_URL`**。compose 跑的是 Postgres，种子只会写进一个没人读的 SQLite 文件。
2. `infra/Dockerfile.api:15-16` 只 COPY `pyproject/locks/README/LICENSE/src`，**`scripts/` 不在镜像里** → `docker compose exec api python scripts/seed_demo.py` 直接 "No such file or directory"。同样影响 `backup.py` / `restore.py` / `migrate_*.py`，而 operations 文档把它们当生产命令写。
3. 密码 `learn-with-refineq` 硬编码在 `demo.py:30`，`scripts/seed_demo.py:14` 没有 `--password` 参数也没有环境变量覆盖。而 [07-submission-kit.md:37](../product/07-submission-kit.md#L37) 已经写好给评委的话术"`learner@refineq.local` / 【部署时设定的密码】"——这个能力不存在。

**解决方案：**

```python
# demo.py：改为读配置
settings = Settings() if database_url is None else Settings(database_url=database_url)
database = Database(settings.resolved_database_url)

# 密码参数化
def seed_demo(data_root: Path, *, password: str | None = None) -> DemoResult:
    password = password or os.environ.get("REFINEQ_DEMO_PASSWORD") or DEMO_PASSWORD
```

`scripts/seed_demo.py` 增加 `--password` 参数；`pyproject.toml:33-35` 注册 console script：

```toml
refineq-seed-demo = "refineq.operations.demo:main"
```

`Dockerfile.api` 增加 `COPY scripts ./scripts`。

**验收：** 在 compose 环境执行 `docker compose exec api refineq-seed-demo --password '<强密码>'`，用该账号登录成功且看到演示数据。

## C-05 管理后台"创建备份"在生产环境必然失败

**证据：** `operations/admin.py:40-42` 计算 `backup_root = data_root.parent / f"{data_root.name}-backups"` = **`/data-backups`**，位于容器根文件系统；而 api 容器是 `read_only: true`（`compose.yml:70-72`），只有 `/data` 卷和 tmpfs `/tmp` 可写 → `backup.py:400` 的 `mkdir` 抛 EROFS。而 [operations.md:49-56](../operations.md) 把它写成可用功能。即便根文件系统可写，`/data-backups` 也不是卷，重建容器就全丢。

**解决方案：** 备份根移到数据卷内，并允许环境变量覆盖：

```python
backup_root = Path(os.environ.get("REFINEQ_BACKUP_ROOT") or (data_root / "backups"))
```

同时确认 `backup.py` 的归档不会把 `backups/` 自身递归打包（排除该子目录）。

**验收：** 生产拓扑下管理后台创建备份成功、列表可见、恢复校验通过；容器重建后备份仍在。

---

# D 组 · 可见性（低风险，收益直接）

## D-01 误区（misconceptions）不上判分卡

**证据：** `learning-session-canvas.tsx:414-422` 的 `feedback-columns` 只渲染 `strengths` 和 `gaps`；`misconceptions` 全应用只在 `evidence-ledger.tsx:212-213` 出现（证据台账详情里，要展开两层才看得到）。

PRD M3 声称"判分含六要素 100%，契约测试保证"——**这条契约测试不存在**；[04-experience.md:34](../product/04-experience.md#L34) 也写着"优势/缺口/误区三栏（已有）"，实际只有两栏。

降级路径更硬：`intelligence.py:268` 的 `misconceptions=[]` 永远为空。

**解决方案：** 判分卡加第三栏（约 6 行 JSX，i18n 键 `misconceptions` 已存在于 `i18n.ts:84`），空数组时不渲染该栏。同时给 `fallback_grade` 在"答案偏题"时补一条保底 misconception，让降级路径也不是恒空。

**验收：** 组件测试断言三栏都渲染；补一条契约测试覆盖 PRD M3。

## D-02 教练看到的薄弱点是内部 ID 而非主题名

**证据：** `agent/context.py:25-27` 的 `weakest_knowledge_points` 直接用 `mastery` 字典的键，而键是 `topic_<sha256前16位>`（`workspaces/service.py:101-102`）。教练无法把薄弱点说成人话。

`FR-E1` 专门要求"显示可读主题名（不是内部 ID）"，说明团队知道这个坑，但只在前端修了，没修 Agent 上下文。

**解决方案：** `build_agent_context` 增加 `topic_names: dict[str, str]` 参数，`agent/service.py` 从 `progress["topics"]` 取名字传入：

```python
"weakest_knowledge_points": [
    {"topic": topic_names.get(topic, topic), "mastery": round(score, 3)}
    for topic, score in weak_points
],
```

**验收：** 单元测试断言组装出的 context 里出现主题名、不出现 `topic_` 前缀。

## D-03 降级标识文案已备好但无组件引用

**证据：** `i18n.ts:112-116`（中）与 `:307-311`（英）已有 `aiQuestion` / `fallbackQuestion` / `aiGrading` / `fallbackGrading` 四条文案，**全仓库没有任何组件引用**。后端 `QuestionResponse.mode` 与 `AnswerResponse.grading_mode` 一直在返回。

NFR-2"降级状态对用户可见"因此是文案 100%、渲染 0%。

**解决方案：** 题目卡与判分卡各加一个小徽章，`mode === "fallback"` 时显示"基础题库出题"/"规则判分"。这既补上 NFR-2，也是评测环境未配模型时**主动澄清而非被误判为套壳**的关键——建议同时在 README 显著位置说明降级行为。

**验收：** 组件测试断言两种 mode 下徽章文案正确。

## D-04 核心 AI 链路无任何可观测性

**证据：** 全仓只有 2 个文件用 `logging`（`api/routers/admin.py`、`knowledge/index.py`）。模型调用延迟、失败率、**AI→fallback 降级率**、意图抽取被 `BoundedIntentExecutor` 拒绝的次数（`actions.py:477` 静默 `return None`）、检索命中率——一条日志都没有。`agent/service.py:446` 一次性吞掉四类异常且不记录。

**解决方案：** 在四个降级分支和 `BoundedIntentExecutor.submit` 返回 `None` 处各加一条 `logger.info`，字段含 owner_id 哈希、路径、原因。不需要引入指标系统，日志足够回答"演示当天有多少比例走了降级"。

---

# E 组 · 闭环补强（中等规模，视时间取舍）

八步闭环里有两步的产物没有下游消费，宣传的是信息丰富的反馈回路，实现的是 **1 bit 回路**（只有 `grade.passed` 进入模型）。

## E-01 计划对出题零影响

**证据：** `next_question` 选题只用 `min(mastery)`（`service.py:736-746`），**完全不看计划今天排的 topic 和 activity**。走计划的 learn 日和 apply 日产出的请求完全一样——`ACTIVITY_SEQUENCE`（`planning.py:11`）只是日历标签。非 review 的计划会话也永远不会自动完成。

**解决方案（小）：** `practiceTopic` 从计划发起时把 `session.activity` 映射到 `learning_mode`（learn→concept、practice→case、apply→project、review→exam），并在提交作答后把对应会话标记完成。**这让"按计划学习"和"随便点"产生可见区别**，是最小改动里效果最明显的一个。

## E-02 证据不反哺出题

**证据：** grep 确认 `gaps` / `misconceptions` **从不进入任何 prompt**。出题的全部输入只有 `topic_name / topic_id / learning_mode / mastery / difficulty / 材料`（`intelligence.py:317-342`），没有任何历史。`make_recommendation()`（`evidence.py:41-57`）是死代码。

评委只要问"你记录的误区，在下一道题里体现在哪"，答案是哪都没有——而反例就在同屏。

**解决方案：** `generate_question` 增加 `recent_gaps: list[str]` 参数，从最近 3 条同主题证据的 `gaps` / `misconceptions` 取值，拼进 user message：

```
Previously observed gaps for this learner on this topic:
- 分不清诉求与需求
- 缺少行为证据
Design the task so it targets at least one of these gaps.
```

这是**把已有数据接上已有通道**，不需要新存储。做完之后"证据台账 → 下一道题"这条线才真正闭合，也是回应"这不是 CRUD"最有力的一处。

## E-03 上传资料不改变主题体系

**证据：** topics 只来自建空间那一刻的意图字符串（`routing.py:285-288`，最多 3 个），`api/routers/materials.py` 里 grep `topic` 只命中一句错误文案。传 100 页讲义，主题列表、计划、掌握度一个都不动。

**解决方案（较大，建议赛后）：** 上传完成后触发一次"主题建议"——用已配置的模型从新增 chunk 里抽取候选主题，与现有主题去重后作为**建议**呈现给用户确认，不自动写入。自动写入会破坏掌握度的连续性。

---

# F 组 · 架构风险（赛后）

| 编号 | 问题 | 证据 | 解决方向 |
| --- | --- | --- | --- |
| F-01 | **LLM 调用在数据库事务和 advisory lock 内部** | `learning/service.py:693`→`:756`（出题）、`workspaces/service.py:135`→`:147`（路由）、`agent/service.py:347`→`:432`（对话），三处都在 `owner_transaction` 内做 30s×2 的网络调用；`engine.py:36` 未配 pool，默认 5+10。**15 个慢请求打空连接池** | 照抄 `submit_answer` 的写法（`:970` 先调模型、`:1113` 再进事务）。同一作者在那一处做对了 |
| F-02 | **嵌套事务静默跳过 advisory lock** | `sql_store.py:88-91` 已有活动会话时直接 `yield`，于是 `agent/service.py:502` 的会话配额锁**从未生效**。当前单 worker 掩盖了它，compose 一扩容就破；同进程并发测试结构上测不出来 | 嵌套时改为显式断言或重入计数；配额校验移到最外层事务 |
| F-03 | **中文词法检索基本失效** | `index.py:402-414` 用 `re.findall(r"\w+", query)` 分词，中文整句变成一个 token；Postgres 侧 `to_tsvector('simple')` 同样不分词。有 `pg_trgm` + ILIKE 兜底，但只有整串子串命中才有分。**未配 embedding 的中文用户，对话检索几乎恒为空** | 引入中文分词（jieba）或改用 `zhparser`；至少把 query 按二元组切分再匹配 |
| F-04 | **分块零 overlap、按 `\n` 切、超长段按字符硬砍** | `index.py:131-145` | 加 10–15% overlap，按句号/分号优先切分 |
| F-05 | **混合排序融合公式尺度不一致** | `index.py:558-585` 把 min-max 归一的词法分与绝对余弦直接加权；且 `if score > 0` 没有相关性下限，**永远返回 6 条来源** | 改用 RRF，或双边归一 + 相关性阈值 |
| F-06 | **死代码** | `learning/diagnostic.py`、`learning/errors.py`、`learning/review.py`（完整 SM-2 引擎）、`agent/settings.py:64-211`（文件版仓储，生产未接线）、`evidence.py:41-57` 的 `make_recommendation` —— 全部只被测试引用 | 接上或删掉。留着会被静态评审判为"演示用假实现" |
| F-07 | 前端诊断流程完全不可达 | `apps/web/lib/api.ts` 没有任何 diagnostic 方法，而掌握度定义、证据类型、术语表都建立在它之上 | 要么补入口，要么把文档里的"诊断"降级为内部概念 |

---

# 建议执行顺序

赛前（按性价比）：**A-02 → A-03 → C-01 → C-02 → C-03 → C-04 → D-01 → D-03 → B-04 → B-01 → B-02**。

这一串的共同点是改动小、边界清楚、都有明确验收，且每一项都直接对应一个评分点或一个会翻车的现场问题。

赛前可选（收益大但需谨慎）：**B-03、E-01、E-02、B-05 第 1 步**。这四项动的是核心语义，要留出跑全量测试和手工复核的时间。

赛后：**E-03、F 组全部**。

---

# 非代码清单（你自己安排，此处仅备查）

这些不在本文范围，但会决定成败：

1. **公网部署 + README 补体验链接与演示账号**——§11 明列"无法提供有效可访问链接"为取消资格情形。
2. **一次真实访谈 + 授权**——洞察占复赛 30%，[02-persona.md](../product/02-persona.md) 现有 11 处占位符，代码补不了，且有外部等待时间。
3. **文档与代码对齐**——PRD 附录 A 有 4 处虚报（FR-A1 已由 H-01 修复、FR-A4 七秒收起、NFR-1 性能预算、FR-E3 报告卡指标口径）、2 处反向低报（掌握度变化与报告卡其实已上线）；architecture.md 漏了整个 `operations/` 模块和 `calendar` 路由；Agent 动作提案系统（`agent/actions.py` 491 行）在所有文档里一字未提——这是赛道最看重的"Agent 主动性"证据，白白浪费。
4. **`admin_cli.py:18` 的默认邮箱**是你的真实邮箱，会随源码 ZIP 一起交出去，且是攻击者优先撞的管理员账号——建议改成必填参数。

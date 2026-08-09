"""Deterministic home routing boundaries that a model cannot override."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from refineq.workspaces.models import LearningWorkspace

MAX_DISPATCH_CANDIDATES = 8
CLASSIFIER_TEXT_LIMIT = 500


class PolicyKind(StrEnum):
    EXPLICIT_WORKSPACE = "explicit_workspace"
    CROSS_WORKSPACE = "cross_workspace"
    WORKSPACE_ACTION = "workspace_action"
    STRONG_LONG_TERM = "strong_long_term"
    AMBIGUOUS_LONG_TERM = "ambiguous_long_term"
    EVALUATION = "evaluation"
    DIRECT_ANSWER = "direct_answer"
    CLARIFY = "clarify"
    OUT_OF_SCOPE = "out_of_scope"
    SEMANTIC = "semantic"


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    kind: PolicyKind
    reason: str
    workspace_ids: tuple[str, ...] = ()


_OPEN_COMMAND = re.compile(
    r"(?:打开|进入|继续|回到|open|enter|continue|resume|go\s+to)\s*[《\"“']?",
    re.IGNORECASE,
)
_CROSS_SPACE = re.compile(
    r"今天.*(?:先|优先|做什么|学什么)|(?:先|优先).*(?:哪个|什么)|"
    r"(?:只有|有)\s*\d+\s*(?:分钟|小時|小时)|时间.*冲突|"
    r"what\s+should\s+i\s+(?:study|do)|prioriti[sz]e|schedule\s+conflict",
    re.IGNORECASE,
)
_ACTION = re.compile(
    r"(?:改到|移到|挪到|延期|改期|调整到|改成)\s*(?:周|星期|明天|后天|\d)|"
    r"(?:调整|改成|缩短|延长).{0,10}\d+\s*(?:分钟|小时)|"
    r"reschedule|move\s+.+\s+to|change\s+.+\s+to\s+\d+\s*(?:minutes?|hours?)",
    re.IGNORECASE,
)
_EVALUATION = re.compile(
    r"出题|考考我|考我|判分|评分|批改|掌握度|练习题|模拟考试|"
    r"quiz\s+me|test\s+me|grade\s+(?:me|this)|score\s+(?:me|this)|practice\s+questions?",
    re.IGNORECASE,
)
_LEARNING_OBJECT = re.compile(
    r"数学|高数|微积分|英语|雅思|托福|编程|算法|物理|化学|生物|历史|"
    r"经济学|产品|写作|研究|[A-Za-z][A-Za-z0-9+#.-]{1,30}",
    re.IGNORECASE,
)
_LEARNING_VERB = re.compile(
    r"学习|复习|备考|掌握|练习|理解|系统学|学一下|"
    r"learn|study|review|prepare\s+for|master|practice|understand",
    re.IGNORECASE,
)
_TIME_CONSTRAINT = re.compile(
    r"\d{4}[-/年]\d{1,2}(?:[-/月]\d{1,2})?|\d{1,2}月\d{1,2}日|"
    r"(?:明天|后天|下周|本周|月底|期末|考试|截止)|"
    r"(?:每天|每日|每周)\s*\d+\s*(?:分钟|小时|次)|"
    r"\d+\s*(?:天|周|星期|个月|月)\s*(?:内|后|系统|坚持)?|"
    r"by\s+\w+|exam\s+on|deadline|daily\s+\d+|for\s+\d+\s*(?:days?|weeks?|months?)",
    re.IGNORECASE,
)
_DIRECT_TASK = re.compile(
    r"是什么|什么意思|解释|区别|为什么|总结|概括|翻译|改写|润色|举例|"
    r"what\s+is|what\s+does|explain|difference\s+between|why\s+does|"
    r"summari[sz]e|translate|rewrite|paraphrase|give\s+an\s+example",
    re.IGNORECASE,
)
_HIGH_RISK_OR_REALTIME = re.compile(
    r"今天.*(?:天气|新闻|股价|汇率)|最新(?:新闻|价格|政策)|实时|"
    r"诊断|处方|用药|法律意见|投资建议|买哪只股|"
    r"weather|latest\s+news|current\s+(?:price|rate)|medical\s+advice|"
    r"legal\s+advice|investment\s+advice|stock\s+pick",
    re.IGNORECASE,
)
_DESTRUCTIVE = re.compile(
    r"删除.*(?:计划|空间|资料)|清空|归档.*空间|"
    r"delete\s+(?:all|the).*(?:plan|workspace|material)|archive\s+workspace",
    re.IGNORECASE,
)
_CLEAR_NON_LEARNING = re.compile(
    r"写(?:营销|广告|销售)文案|发.{0,8}(?:邮件|消息)|订机票|点外卖|"
    r"marketing\s+copy|send\s+(?:an\s+)?email|book\s+(?:a\s+)?flight|order\s+food",
    re.IGNORECASE,
)
_LOW_INFORMATION = re.compile(
    r"^(?:继续|帮帮我|怎么办|开始|hi|hello|continue|help|start)[!！。.\s]*$",
    re.IGNORECASE,
)


def _normalized(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().casefold())


def _named_workspaces(text: str, workspaces: list[LearningWorkspace]) -> list[LearningWorkspace]:
    normalized = _normalized(text)
    return [item for item in workspaces if _normalized(item.title) in normalized]


def select_dispatch_candidates(
    text: str,
    workspaces: list[LearningWorkspace],
) -> tuple[list[LearningWorkspace], bool]:
    """Return the recent bounded set while preserving explicitly named old spaces."""

    ordered = sorted(
        (item for item in workspaces if not item.archived),
        key=lambda item: (item.last_active_at, item.id),
        reverse=True,
    )
    selected = ordered[:MAX_DISPATCH_CANDIDATES]
    named = _named_workspaces(text, ordered)
    for workspace in named:
        if workspace in selected:
            continue
        if len(selected) == MAX_DISPATCH_CANDIDATES:
            selected.pop()
        selected.append(workspace)
    selected.sort(key=lambda item: (item.last_active_at, item.id), reverse=True)
    return selected, len(ordered) > MAX_DISPATCH_CANDIDATES


class HomeRoutingPolicy:
    """Classify non-negotiable boundaries before optional semantic assistance."""

    def decide(self, text: str, workspaces: list[LearningWorkspace]) -> PolicyDecision:
        normalized = _normalized(text)
        named = _named_workspaces(text, workspaces)

        if _DESTRUCTIVE.search(normalized) or _HIGH_RISK_OR_REALTIME.search(normalized):
            return PolicyDecision(
                PolicyKind.OUT_OF_SCOPE,
                "该请求需要实时或高风险判断，或涉及主页禁止的破坏性操作。",
            )

        if _OPEN_COMMAND.search(normalized) and named:
            if len(named) == 1:
                return PolicyDecision(
                    PolicyKind.EXPLICIT_WORKSPACE,
                    "用户明确命令打开唯一命名的学习空间。",
                    (named[0].id,),
                )
            return PolicyDecision(
                PolicyKind.CLARIFY,
                "存在多个同名或同时被点名的学习空间。",
                tuple(item.id for item in named[:3]),
            )

        if _ACTION.search(normalized):
            return PolicyDecision(
                PolicyKind.WORKSPACE_ACTION,
                "请求会修改计划会话，必须先展示前后差异并确认。",
                tuple(item.id for item in named[:1]),
            )

        if _CROSS_SPACE.search(normalized):
            return PolicyDecision(
                PolicyKind.CROSS_WORKSPACE,
                "请求需要比较多个学习空间的确定性下一行动。",
            )

        if _EVALUATION.search(normalized):
            return PolicyDecision(
                PolicyKind.EVALUATION,
                "出题、评分和掌握度更新必须在有资料约束的学习空间完成。",
                tuple(item.id for item in named[:1]),
            )

        has_learning_object = bool(_LEARNING_OBJECT.search(normalized))
        has_learning_verb = bool(_LEARNING_VERB.search(normalized))
        has_time_constraint = bool(_TIME_CONSTRAINT.search(normalized))
        if has_learning_object and has_time_constraint:
            return PolicyDecision(
                PolicyKind.STRONG_LONG_TERM,
                "明确学习对象与时间约束构成无歧义的长期学习信号。",
            )
        if has_learning_verb:
            return PolicyDecision(
                PolicyKind.AMBIGUOUS_LONG_TERM,
                "存在长期学习意图，但缺少足够约束，先预览再创建。",
            )

        if _DIRECT_TASK.search(normalized):
            return PolicyDecision(
                PolicyKind.DIRECT_ANSWER,
                "这是可在本次完成的稳定概念解释或文本转换。",
            )
        if _CLEAR_NON_LEARNING.search(normalized):
            return PolicyDecision(
                PolicyKind.OUT_OF_SCOPE,
                "这不是 RefineQ 当前支持的学习任务。",
            )
        if _LOW_INFORMATION.fullmatch(normalized):
            return PolicyDecision(
                PolicyKind.CLARIFY,
                "信息不足，无法安全判断是一次性问题还是长期任务。",
            )
        return PolicyDecision(
            PolicyKind.SEMANTIC,
            "硬边界未命中，需要在受限候选集中做一次语义判断。",
        )

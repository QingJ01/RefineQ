"""Deterministic home routing boundaries that a model cannot override."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from refineq.workspaces.constraints import _strip_quoted_spans, infer_intent_constraints
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
_KNOWN_LEARNING_OBJECT = re.compile(
    r"数学|高数|微积分|英语|雅思|托福|编程|算法|计算机|组成原理|操作系统|数据库|"
    r"机器学习|人工智能|网络|物理|化学|生物|历史|"
    r"经济学|产品|写作|研究",
    re.IGNORECASE,
)
_LATIN_LEARNING_OBJECT = re.compile(r"[A-Za-z][A-Za-z0-9+#.-]{1,30}", re.IGNORECASE)
_LEARNING_VERB = re.compile(
    r"学习|复习|备考|掌握|练习|理解|系统学|学一下|"
    r"learn|study|review|prepare\s+for|master|practice|understand",
    re.IGNORECASE,
)
_EXAM_CONTEXT = re.compile(r"考试|期中|期末|备考|\b(?:exam|midterm|final)\b", re.IGNORECASE)
_DIRECT_TASK = re.compile(
    r"是什么|什么意思|解释|区别|为什么|总结|概括|翻译|改写|润色|举例|"
    r"what\s+is|what\s+does|explain|difference\s+between|why\s+does|"
    r"summari[sz]e|translate|rewrite|paraphrase|give\s+an\s+example",
    re.IGNORECASE,
)
_EXPLICIT_TEXT_TRANSFORM = re.compile(
    r"(?:总结|概括|翻译|改写|润色)(?:一下)?(?:我)?(?:粘贴(?:的)?|贴出(?:的)?)?"
    r"(?:下面|以下|这段|这份|这篇).{0,12}(?:文字|文本|内容|文章|：|:)|"
    r"(?:summari[sz]e|translate|rewrite|paraphrase)\s+(?:the\s+)?"
    r"(?:following|below|this(?:\s+pasted)?\s+text)",
    re.IGNORECASE,
)
_EXPLICIT_QUOTED_EXPLANATION = re.compile(
    r"(?:[“\"「『].{1,500}[”\"」』]\s*(?:是什么意思|表示什么|如何理解)|"
    r"(?:解释|说明|解读).{0,6}(?:这句(?:话)?|这段(?:话|文字|内容)?|以下|下面).{0,8}[：:]|"
    r"what\s+does\s+[\"“].{1,500}[\"”]\s+mean|"
    r"what\s+does\s+(?:this|the)\s+(?:quoted\s+|following\s+|above\s+)?"
    r"(?:sentence|text|passage|phrase|line|quote|quotation)\s+mean|"
    r"explain\s+(?:this|the\s+following)\s+(?:sentence|text|passage)|"
    # "explain it" only counts as a quoted-explanation request when a quoted span
    # is actually present. Unanchored, it sits ahead of the destructive and
    # high-risk gates and lets "…and explain it." defeat them.
    r"(?<=[\"”」』])[\s\S]{0,40}?explain\s+it\b)",
    re.IGNORECASE,
)
_NEGATED_CREATION_OR_ONE_SHOT = re.compile(
    r"do\s+not\s+create|don'?t\s+create|without\s+creating|"
    r"explain\s+it\s+only|only\s+explain|just\s+answer|answer\s+(?:it\s+)?only|"
    r"不要创建|不用创建|别创建|不要建|不用建|别建|"
    r"一次性|仅解释|只解释|仅回答|只回答|只需回答",
    re.IGNORECASE,
)
_ONE_SHOT_STUDY_PLAN = re.compile(
    r"(?:今天|今晚|今夜).{0,20}[一二两三四五六七八九十\d]+\s*(?:分钟|小时)"
    r".{0,20}(?:临时)?(?:安排|计划)|"
    r"(?:one[- ]off|just\s+for\s+tonight|tonight).{0,30}(?:study\s+)?(?:plan|schedule)",
    re.IGNORECASE,
)
_HIGH_RISK_OR_REALTIME = re.compile(
    r"今天.*(?:天气|新闻|股价|汇率)|最新(?:新闻|价格|政策)|实时|"
    r"诊断|处方|用药|医疗建议|医嘱|法律意见|投资建议|买哪只股|"
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


def _topic_matched_workspaces(
    text: str,
    workspaces: list[LearningWorkspace],
) -> list[LearningWorkspace]:
    normalized = _normalized(text)
    return [
        item
        for item in workspaces
        if not item.archived
        and any(
            len(_normalized(term)) >= 2 and _normalized(term) in normalized
            for term in (*item.topics, *item.keywords)
        )
    ]


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
    preserved = [*_named_workspaces(text, workspaces), *_topic_matched_workspaces(text, workspaces)]
    preserved_by_id = {item.id: item for item in preserved}
    for workspace in preserved_by_id.values():
        if workspace in selected:
            continue
        if len(selected) == MAX_DISPATCH_CANDIDATES:
            selected.pop()
        selected.append(workspace)
    selected.sort(key=lambda item: (item.last_active_at, item.id), reverse=True)
    return selected, len(ordered) > MAX_DISPATCH_CANDIDATES


class HomeRoutingPolicy:
    """Classify non-negotiable boundaries before optional semantic assistance."""

    @staticmethod
    def allows_learning_recovery(text: str) -> bool:
        """Return whether an out-of-scope result may be reclaimed as a learning task."""

        normalized = _normalized(text)
        return not (_DESTRUCTIVE.search(normalized) or _HIGH_RISK_OR_REALTIME.search(normalized))

    def decide(
        self,
        text: str,
        workspaces: list[LearningWorkspace],
        *,
        now: datetime | None = None,
    ) -> PolicyDecision:
        normalized = _normalized(text)
        named = _named_workspaces(text, workspaces)

        if _EXPLICIT_TEXT_TRANSFORM.search(normalized) or _EXPLICIT_QUOTED_EXPLANATION.search(
            normalized
        ):
            return PolicyDecision(
                PolicyKind.DIRECT_ANSWER,
                "这是对本次明确标记文本的一次性转换；正文只作为不可信数据处理。",
            )

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

        if _CLEAR_NON_LEARNING.search(normalized):
            return PolicyDecision(
                PolicyKind.OUT_OF_SCOPE,
                "这不是 RefineQ 当前支持的学习任务。",
            )

        if _ACTION.search(normalized):
            return PolicyDecision(
                PolicyKind.WORKSPACE_ACTION,
                "请求会修改计划会话，必须先展示前后差异并确认。",
                tuple(item.id for item in named[:3]),
            )

        if _CROSS_SPACE.search(normalized):
            return PolicyDecision(
                PolicyKind.CROSS_WORKSPACE,
                "请求需要比较多个学习空间的确定性下一行动。",
            )

        if _EVALUATION.search(normalized):
            matched = named or _topic_matched_workspaces(text, workspaces)
            return PolicyDecision(
                PolicyKind.EVALUATION,
                "出题、评分和掌握度更新必须在有资料约束的学习空间完成。",
                tuple(item.id for item in matched[:3]),
            )

        if _ONE_SHOT_STUDY_PLAN.search(normalized) and not named:
            return PolicyDecision(
                PolicyKind.DIRECT_ANSWER,
                "这是不依赖既有长期状态的一次性学习时间建议。",
            )

        # Long-term learning signals must come from the learner's OWN words, not
        # from quoted material to be explained nor from a negated-creation clause.
        # Strip quoted spans first, then honour an explicit request to only answer
        # this once ("do not create a workspace", "explain it only", "只回答"...).
        unquoted_normalized = _normalized(_strip_quoted_spans(text))
        if _NEGATED_CREATION_OR_ONE_SHOT.search(unquoted_normalized):
            return PolicyDecision(
                PolicyKind.DIRECT_ANSWER,
                "用户明确要求只做一次性解答，不建立长期学习空间。",
            )

        has_learning_verb = bool(_LEARNING_VERB.search(unquoted_normalized))
        has_exam_context = bool(_EXAM_CONTEXT.search(unquoted_normalized))
        has_learning_object = bool(_KNOWN_LEARNING_OBJECT.search(unquoted_normalized)) or (
            bool(_LATIN_LEARNING_OBJECT.search(unquoted_normalized))
            and (has_learning_verb or has_exam_context)
        )
        constraints = infer_intent_constraints(text, now=now or datetime.now(UTC))
        has_time_constraint = (
            constraints.exam_at is not None or constraints.daily_minutes is not None
        )
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
        if _LOW_INFORMATION.fullmatch(normalized):
            return PolicyDecision(
                PolicyKind.CLARIFY,
                "信息不足，无法安全判断是一次性问题还是长期任务。",
            )
        return PolicyDecision(
            PolicyKind.SEMANTIC,
            "硬边界未命中，需要在受限候选集中做一次语义判断。",
        )

"""Deterministic workspace routing used alone or as an AI safety fallback."""

from __future__ import annotations

import re

from refineq.workspaces.models import LearningWorkspace, WorkspaceRoutingDecision

_SUBJECT_HINTS: dict[str, tuple[str, ...]] = {
    "mathematics": (
        "数学",
        "高数",
        "微积分",
        "极限",
        "导数",
        "积分",
        "代数",
        "geometry",
        "calculus",
        "limit",
        "limits",
        "derivative",
        "derivatives",
        "integral",
        "integrals",
        "cross product",
        "vector",
        "vectors",
        "math",
    ),
    "language": (
        "英语",
        "四级",
        "六级",
        "雅思",
        "托福",
        "单词",
        "语法",
        "english",
        "ielts",
        "toefl",
    ),
    "programming": (
        "编程",
        "代码",
        "算法",
        "数据结构",
        "python",
        "javascript",
        "typescript",
        "java",
        "rust",
        "coding",
    ),
    "product": (
        "产品思维",
        "产品设计",
        "用户需求",
        "需求验证",
        "用户研究",
        "product thinking",
        "product discovery",
        "product",
        "user needs",
    ),
    "operations": (
        "运营思维",
        "增长运营",
        "内容运营",
        "活动策划",
        "运营",
        "growth operations",
        "campaign analysis",
        "operations",
        "growth",
    ),
    "writing": (
        "写作",
        "结构化表达",
        "文案",
        "内容创作",
        "structured writing",
        "copywriting",
        "storytelling",
        "argumentation",
        "writing",
    ),
    "research": (
        "研究",
        "调研",
        "信息检索",
        "文献综述",
        "research synthesis",
        "literature review",
        "research",
    ),
    "science": (
        "物理",
        "化学",
        "生物",
        "physics",
        "chemistry",
        "biology",
    ),
    "humanities": (
        "历史",
        "政治",
        "哲学",
        "文学",
        "history",
        "philosophy",
        "literature",
    ),
}

_LOW_INFORMATION = {
    "继续",
    "继续学习",
    "开始学习",
    "接着学",
    "复习一下",
    "continue",
    "keep going",
    "study",
}

_ENGLISH_STOPWORDS = {
    "a",
    "an",
    "and",
    "as",
    "at",
    "be",
    "for",
    "from",
    "have",
    "i",
    "in",
    "is",
    "it",
    "my",
    "of",
    "on",
    "the",
    "to",
    "two",
    "want",
    "with",
    "exam",
    "review",
    "learn",
    "practice",
    "today",
    "week",
    "weeks",
}

_BROAD_SUBJECT_TERMS = {
    "数学",
    "高数",
    "微积分",
    "英语",
    "编程",
    "科学",
    "calculus",
    "math",
    "mathematics",
    "language",
    "english",
    "programming",
    "coding",
    "product",
    "product thinking",
    "operations",
    "growth operations",
    "writing",
    "research",
    "science",
    "humanities",
}


def _normalized(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().casefold())


def _subject(intent: str) -> str:
    normalized = _normalized(intent)
    if re.search(r"\boperations research\b", normalized):
        return "research"
    if re.search(r"\bbiological growth\b", normalized):
        return "science"

    def includes(hint: str) -> bool:
        if not hint.isascii():
            return hint in normalized
        return bool(
            re.search(
                rf"(?<![a-z0-9]){re.escape(hint)}(?![a-z0-9])",
                normalized,
            )
        )

    scores = {
        subject: sum(includes(hint) for hint in hints) for subject, hints in _SUBJECT_HINTS.items()
    }
    selected, score = max(scores.items(), key=lambda item: item[1])
    return selected if score else "general"


def _keywords(intent: str) -> list[str]:
    normalized = _normalized(intent)
    keywords = {
        word
        for word in re.findall(r"[a-z][a-z0-9+#.-]{1,30}", normalized)
        if word not in _ENGLISH_STOPWORDS
    }
    for hints in _SUBJECT_HINTS.values():
        keywords.update(hint for hint in hints if not hint.isascii() and hint in normalized)
    if not keywords:
        compact = re.sub(r"[，。！？、,.!?\s]", "", intent.strip())
        if compact and compact not in _LOW_INFORMATION:
            keywords.add(compact[:30])
    return sorted(keywords, key=lambda item: (normalized.find(item), item))


def _capability_topics(subject: str, normalized: str) -> list[str]:
    mappings: dict[str, tuple[tuple[tuple[str, ...], str], ...]] = {
        "product": (
            (("用户需求", "需求验证", "user needs", "validate", "validation"), "用户需求验证"),
            (("用户访谈", "访谈", "interview"), "用户访谈分析"),
            (("产品发现", "product discovery", "discovery"), "产品发现"),
        ),
        "operations": (
            (("增长", "growth"), "增长实验"),
            (("活动", "campaign"), "活动复盘"),
            (("内容", "content"), "内容运营"),
        ),
        "writing": (
            (("结构", "structured"), "结构化表达"),
            (("论证", "argument"), "观点论证"),
            (("文案", "copywriting"), "文案写作"),
        ),
        "research": (
            (("检索", "综合", "synthesis", "literature review"), "证据检索与综合"),
            (("研究问题", "research question"), "研究问题定义"),
        ),
    }
    return [
        label
        for hints, label in mappings.get(subject, ())
        if any(hint in normalized for hint in hints)
    ]


def _topics(subject: str, keywords: list[str], title: str, normalized: str) -> list[str]:
    capability_topics = _capability_topics(subject, normalized)
    if capability_topics:
        return capability_topics[:3]
    capability_defaults = {
        "product": "产品问题分析",
        "operations": "运营问题分析",
        "writing": "内容写作",
        "research": "研究方法",
    }
    if subject in capability_defaults:
        return [capability_defaults[subject]]
    candidates = [item for item in keywords if item != subject]
    specific = [item for item in candidates if item not in _BROAD_SUBJECT_TERMS]
    return (specific or candidates or [title])[:3]


def _suggested_title(intent: str, subject: str) -> str:
    normalized = _normalized(intent)
    if subject == "programming":
        for name in ("Python", "JavaScript", "TypeScript", "Java", "Rust"):
            if name.casefold() in normalized:
                return f"{name} 学习"
        return "编程学习"
    if subject == "product":
        return "产品思维"
    if subject == "operations":
        return "运营思维"
    if subject == "writing":
        return "写作能力"
    if subject == "research":
        return "研究能力"
    if subject == "mathematics":
        is_advanced = any(key in normalized for key in ("高数", "微积分", "极限"))
        return "高等数学" if is_advanced else "数学学习"
    if subject == "language":
        if "四级" in normalized:
            return "英语四级"
        if "六级" in normalized:
            return "英语六级"
        return "语言学习"
    if subject == "science":
        return "理科学习"
    if subject == "humanities":
        return "人文学习"
    compact = intent.strip().splitlines()[0][:24].strip("，。！？,.!? ")
    return compact or "个人学习"


def route_workspace(
    intent: str,
    workspaces: list[LearningWorkspace],
) -> WorkspaceRoutingDecision:
    """Choose an existing workspace or describe a safe new one."""

    normalized = _normalized(intent)
    if not normalized:
        raise ValueError("intent must not be blank")
    subject = _subject(intent)
    keywords = _keywords(intent)
    latest = max(workspaces, key=lambda item: item.last_active_at) if workspaces else None

    if latest and normalized in _LOW_INFORMATION:
        return WorkspaceRoutingDecision(
            action="reused",
            workspace_id=latest.id,
            title=latest.title,
            subject=latest.subject,
            topics=latest.topics[:20],
            keywords=latest.keywords[:50],
            confidence=0.45,
            reason="信息较少，继续最近一次学习。",
        )

    best: LearningWorkspace | None = None
    best_score = 0.0
    intent_terms = set(keywords)
    for candidate in workspaces:
        candidate_terms = {item.casefold() for item in candidate.keywords}
        candidate_terms.update(
            _keywords(" ".join([candidate.title, candidate.goal, *candidate.topics]))
        )
        matching_terms = intent_terms & candidate_terms
        overlap = len(matching_terms) / max(1, len(intent_terms))
        title_match = candidate.title.casefold() in normalized
        score = overlap * 0.7
        if subject != "general" and subject == candidate.subject:
            score += 0.25
        if title_match:
            score += 0.2
        if not matching_terms and not title_match:
            score = 0.0
        if score > best_score:
            best, best_score = candidate, score

    if best is not None and best_score >= 0.6:
        action = "reused" if latest is not None and latest.id == best.id else "switched"
        return WorkspaceRoutingDecision(
            action=action,
            workspace_id=best.id,
            title=best.title,
            subject=best.subject,
            topics=best.topics[:20],
            keywords=sorted(set(best.keywords) | set(keywords))[:50],
            confidence=min(0.98, 0.55 + best_score * 0.35),
            reason=f"当前内容与“{best.title}”的主题和关键词匹配。",
        )

    title = _suggested_title(intent, subject)
    return WorkspaceRoutingDecision(
        action="created",
        title=title,
        subject=subject,
        topics=_topics(subject, keywords, title, normalized),
        keywords=keywords or [title],
        confidence=0.92 if subject != "general" else 0.72,
        reason="当前内容与已有学习方向差异明显，建立新的学习空间。",
    )

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


def _normalized(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().casefold())


def _subject(intent: str) -> str:
    normalized = _normalized(intent)
    scores = {
        subject: sum(hint in normalized for hint in hints)
        for subject, hints in _SUBJECT_HINTS.items()
    }
    selected, score = max(scores.items(), key=lambda item: item[1])
    return selected if score else "general"


def _keywords(intent: str) -> list[str]:
    normalized = _normalized(intent)
    keywords = set(re.findall(r"[a-z][a-z0-9+#.-]{1,30}", normalized))
    for hints in _SUBJECT_HINTS.values():
        keywords.update(hint for hint in hints if hint in normalized)
    if not keywords:
        compact = re.sub(r"[，。！？、,.!?\s]", "", intent.strip())
        if compact and compact not in _LOW_INFORMATION:
            keywords.add(compact[:30])
    return sorted(keywords)


def _suggested_title(intent: str, subject: str) -> str:
    normalized = _normalized(intent)
    if subject == "programming":
        for name in ("Python", "JavaScript", "TypeScript", "Java", "Rust"):
            if name.casefold() in normalized:
                return f"{name} 学习"
        return "编程学习"
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
    topic = next((item for item in keywords if item not in {subject}), title)
    return WorkspaceRoutingDecision(
        action="created",
        title=title,
        subject=subject,
        topics=[topic],
        keywords=keywords or [title],
        confidence=0.92 if subject != "general" else 0.72,
        reason="当前内容与已有学习方向差异明显，建立新的学习空间。",
    )

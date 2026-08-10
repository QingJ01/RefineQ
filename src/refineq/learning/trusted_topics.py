"""Server-owned canonical subjects for mastery-authoritative answer keys."""

from __future__ import annotations

import re
from unicodedata import normalize

_MATERIAL_TOPIC_SUBJECTS = {
    "output with feedback control": "feedback control",
    "return with compound interest": "compound interest",
}


def material_answer_key_subject(label: str) -> str | None:
    """Return a subject only for an exact, server-curated material topic label."""

    normalized = normalize("NFKC", label)
    collapsed = re.sub(r"\s+", " ", normalized).strip().casefold()
    return _MATERIAL_TOPIC_SUBJECTS.get(collapsed)


__all__ = ["material_answer_key_subject"]

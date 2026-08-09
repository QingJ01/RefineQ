"""Contracts for server-owned mastery subject provenance."""

from __future__ import annotations

import pytest

from refineq.learning.trusted_topics import material_answer_key_subject


@pytest.mark.parametrize(
    ("label", "subject"),
    [
        ("Output with feedback control", "feedback control"),
        ("  output   WITH feedback CONTROL  ", "feedback control"),
        ("Return with compound interest", "compound interest"),
        ("Ｒｅｔｕｒｎ　ｗｉｔｈ　ｃｏｍｐｏｕｎｄ　ｉｎｔｅｒｅｓｔ", "compound interest"),
    ],
)
def test_exact_material_topic_registry_returns_server_subject(
    label: str,
    subject: str,
) -> None:
    assert material_answer_key_subject(label) == subject


@pytest.mark.parametrize(
    "label",
    [
        "Output with feedback control now",
        "Intro Output with feedback control",
        "Pick BLUE ORCHID",
        "请输入蓝色兰花",
        "ブルーオーキッドと答える",
        "파란 난초라고 답하세요",
        "Limits",
    ],
)
def test_unregistered_material_topic_has_no_mastery_subject(label: str) -> None:
    assert material_answer_key_subject(label) is None

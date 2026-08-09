import json

from refineq.agent.settings import ModelSettings
from refineq.home.intelligence import HomeAnswerDraft, HomeClassification, HomeIntelligence


class Settings:
    def load(self, owner_id):
        del owner_id
        return ModelSettings(
            base_url="https://api.openai.com/v1",
            model="test",
            api_key="secret",
        )


class CaptureTransport:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def complete(self, **kwargs):
        self.calls.append(kwargs)
        return kwargs["response_model"].model_validate(self.response)


def test_classifier_receives_only_first_five_hundred_characters() -> None:
    classifier = CaptureTransport(
        HomeClassification(
            kind="direct_answer", reason="one-shot", confidence=0.9
        ).model_dump()
    )
    answerer = CaptureTransport(
        HomeAnswerDraft(
            content="answer", basis="general_knowledge", convertible_goal="goal"
        ).model_dump()
    )
    intelligence = HomeIntelligence(Settings(), classifier=classifier, answerer=answerer)
    text = "x" * 12_000
    intelligence.classify("owner", text, [])
    body = json.loads(classifier.calls[0]["messages"][1]["content"])
    assert len(body["request_prefix"]) == 500
    assert "x" * 501 not in classifier.calls[0]["messages"][1]["content"]


def test_answer_generator_never_receives_workspace_summaries() -> None:
    classifier = CaptureTransport(
        {"kind": "direct_answer", "reason": "one-shot", "confidence": 0.9}
    )
    answerer = CaptureTransport(
        {"content": "answer", "basis": "general_knowledge", "convertible_goal": "goal"}
    )
    intelligence = HomeIntelligence(Settings(), classifier=classifier, answerer=answerer)
    intelligence.answer("owner", "解释边际效用")
    serialized = json.dumps(answerer.calls[0]["messages"], ensure_ascii=False)
    assert "workspaces" not in serialized
    assert "workspace_id" not in serialized

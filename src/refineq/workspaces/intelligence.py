"""Schema-constrained AI routing with a deterministic safety fallback."""

from __future__ import annotations

import json

from openai import OpenAIError
from pydantic import ValidationError

from refineq.agent.settings import ModelNotConfiguredError, ModelSettingsRepository
from refineq.agent.structured import StructuredModelResponseError, StructuredModelTransport
from refineq.workspaces.models import LearningWorkspace, WorkspaceRoutingDecision
from refineq.workspaces.routing import route_workspace


class WorkspaceRoutingIntelligence:
    def __init__(
        self,
        settings: ModelSettingsRepository,
        transport: StructuredModelTransport,
    ) -> None:
        self._settings = settings
        self._transport = transport

    def route(
        self,
        intent: str,
        owner_id: str,
        workspaces: list[LearningWorkspace],
    ) -> WorkspaceRoutingDecision:
        """Ask the configured model to route, then validate all referenced IDs."""

        fallback = route_workspace(intent, workspaces)
        try:
            settings = self._settings.load(owner_id)
            decision = self._transport.complete(
                settings=settings,
                response_model=WorkspaceRoutingDecision,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You route a learner's intent into one private learning workspace. "
                            "Reuse or switch only to an ID in the supplied list. Create a new "
                            "workspace when the subject or learning goal is materially different. "
                            "Return only JSON matching the requested schema."
                        ),
                    },
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "intent": intent,
                                "workspaces": [
                                    item.model_dump(mode="json") for item in workspaces
                                ],
                            },
                            ensure_ascii=False,
                        ),
                    },
                ],
            )
        except (
            ModelNotConfiguredError,
            StructuredModelResponseError,
            OpenAIError,
            ValidationError,
        ):
            return fallback

        valid_ids = {item.id for item in workspaces}
        if decision.action in {"reused", "switched"}:
            if decision.workspace_id not in valid_ids:
                return fallback
        elif decision.workspace_id is not None:
            return fallback
        return decision

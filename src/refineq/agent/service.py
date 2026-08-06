"""Grounded chat orchestration with pluggable model transport."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol
from uuid import uuid4

from openai import OpenAI
from pydantic import BaseModel, ConfigDict, Field

from refineq.agent.context import build_agent_context
from refineq.agent.settings import ModelSettings, ModelSettingsRepository
from refineq.knowledge.index import KnowledgeIndex, SearchResult
from refineq.learning.models import BKTState
from refineq.storage.json_store import RecordNotFoundError, validate_identifier
from refineq.storage.learning import LearningRepository
from refineq.storage.projects import ProjectRepository
from refineq.storage.sessions import SessionRepository


class AgentServiceError(RuntimeError):
    code = "agent_error"


class AgentProjectNotFoundError(AgentServiceError):
    code = "project_not_found"


class AgentLearningStateError(AgentServiceError):
    code = "learning_not_seeded"


class AgentSessionConflictError(AgentServiceError):
    code = "agent_session_conflict"


@dataclass(frozen=True, slots=True)
class ModelReply:
    text: str
    citations: list[str]


class ModelTransport(Protocol):
    def complete(
        self,
        *,
        settings: ModelSettings,
        messages: list[dict[str, str]],
    ) -> ModelReply: ...


class OpenAICompatibleTransport:
    def complete(
        self,
        *,
        settings: ModelSettings,
        messages: list[dict[str, str]],
    ) -> ModelReply:
        client = OpenAI(
            api_key=settings.api_key.get_secret_value(),
            base_url=str(settings.base_url),
        )
        response = client.chat.completions.create(
            model=settings.model,
            messages=messages,
            temperature=settings.temperature,
        )
        text = response.choices[0].message.content or ""
        citations = list(dict.fromkeys(re.findall(r"\[([A-Za-z0-9_-]+#\d+)\]", text)))
        return ModelReply(text=text, citations=citations)


class AgentChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=20_000)
    session_id: str | None = Field(
        default=None,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$",
    )


class AgentChatResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    session_id: str
    message: str
    citations: list[str]
    sources: list[SearchResult]


class AgentService:
    def __init__(
        self,
        *,
        projects: ProjectRepository,
        learning: LearningRepository,
        knowledge: KnowledgeIndex,
        sessions: SessionRepository,
        model_settings: ModelSettingsRepository,
        transport: ModelTransport,
    ) -> None:
        self._projects = projects
        self._learning = learning
        self._knowledge = knowledge
        self._sessions = sessions
        self._model_settings = model_settings
        self._transport = transport

    def _require_project(self, owner_id: str, project_id: str) -> None:
        try:
            self._projects.get(owner_id, project_id)
        except RecordNotFoundError as error:
            raise AgentProjectNotFoundError("Project not found") from error

    def chat(
        self,
        owner_id: str,
        project_id: str,
        payload: AgentChatRequest,
    ) -> AgentChatResponse:
        self._require_project(owner_id, project_id)
        try:
            learning_record = self._learning.get(owner_id, project_id)
            progress = learning_record.data["progress"]
            if not progress.get("seeded"):
                raise KeyError("seeded")
        except (RecordNotFoundError, KeyError) as error:
            raise AgentLearningStateError("Learning project has not been seeded") from error

        settings = self._model_settings.load()
        try:
            sources = self._knowledge.search(
                owner_id=owner_id,
                project_id=project_id,
                query=payload.message,
                limit=6,
            )
        except ValueError:
            sources = []
        mastery = {
            topic_id: BKTState.model_validate(state).p_mastery
            for topic_id, state in progress["bkt_states"].items()
        }
        context = build_agent_context(
            goal=progress["goal"],
            plan=progress.get("plan"),
            mastery=mastery,
            sources=sources,
        )

        session_id = payload.session_id or uuid4().hex
        validate_identifier(session_id, field="session_id")
        try:
            session = self._sessions.get(owner_id, session_id)
            if session.data.get("project_id") != project_id:
                raise AgentSessionConflictError("Session belongs to another project")
        except RecordNotFoundError:
            session = self._sessions.create(
                owner_id,
                session_id,
                {"project_id": project_id, "messages": []},
            )

        history = [
            {"role": item["role"], "content": item["content"]}
            for item in session.data["messages"]
        ]
        messages = [
            {"role": "system", "content": context},
            *history,
            {"role": "user", "content": payload.message.strip()},
        ]
        reply = self._transport.complete(settings=settings, messages=messages)
        available = {source.citation_id: source for source in sources}
        citations = [
            citation
            for citation in dict.fromkeys(reply.citations)
            if citation in available
        ]

        def append_messages(data):
            data["messages"].extend(
                [
                    {"role": "user", "content": payload.message.strip()},
                    {
                        "role": "assistant",
                        "content": reply.text,
                        "citations": citations,
                    },
                ]
            )
            return data

        self._sessions.mutate(owner_id, session_id, append_messages)
        return AgentChatResponse(
            session_id=session_id,
            message=reply.text,
            citations=citations,
            sources=[available[citation] for citation in citations],
        )

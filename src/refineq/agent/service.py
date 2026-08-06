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

MAX_SESSION_MESSAGES = 20
MAX_SESSION_TURNS = 20
MAX_HISTORY_CHARACTERS = 40_000
MAX_MODEL_REPLY_CHARACTERS = 20_000
_CITATION_MARKER = re.compile(r"\[([A-Za-z0-9_-]+#\d+)\]")


class AgentServiceError(RuntimeError):
    code = "agent_error"


class AgentProjectNotFoundError(AgentServiceError):
    code = "project_not_found"


class AgentLearningStateError(AgentServiceError):
    code = "learning_not_seeded"


class AgentSessionConflictError(AgentServiceError):
    code = "agent_session_conflict"


class AgentSessionLimitError(AgentServiceError):
    code = "agent_session_limit"


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
            timeout=30.0,
            max_retries=2,
        )
        response = client.chat.completions.create(
            model=settings.model,
            messages=messages,
            temperature=settings.temperature,
            max_tokens=4_000,
        )
        text = response.choices[0].message.content or ""
        citations = list(dict.fromkeys(re.findall(r"\[([A-Za-z0-9_-]+#\d+)\]", text)))
        return ModelReply(text=text, citations=citations)


def _bounded_history(messages: list[dict[str, str]]) -> list[dict[str, str]]:
    """Keep the newest messages inside both count and character budgets."""

    selected: list[dict[str, str]] = []
    remaining = MAX_HISTORY_CHARACTERS
    for item in reversed(messages[-MAX_SESSION_MESSAGES:]):
        content = str(item.get("content", ""))
        if not content:
            continue
        if len(content) > remaining:
            if selected or remaining <= 0:
                break
            content = content[-remaining:]
        selected.append({"role": str(item.get("role", "user")), "content": content})
        remaining -= len(content)
        if remaining <= 0:
            break
    return list(reversed(selected))


def _sanitize_reply(text: str, available: set[str]) -> str:
    bounded = text[:MAX_MODEL_REPLY_CHARACTERS]
    cleaned = _CITATION_MARKER.sub(
        lambda match: match.group(0) if match.group(1) in available else "",
        bounded,
    )
    return re.sub(r"[ \t]+([,.;:!?，。；：！？])", r"\1", cleaned).strip()


class AgentChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=20_000)
    session_id: str | None = Field(
        default=None,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$",
    )
    turn_id: str | None = Field(
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
        max_sessions: int = 200,
    ) -> None:
        self._projects = projects
        self._learning = learning
        self._knowledge = knowledge
        self._sessions = sessions
        self._model_settings = model_settings
        self._transport = transport
        self._max_sessions = max_sessions

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

        settings = self._model_settings.load(owner_id)
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
        available = {source.citation_id: source for source in sources}
        with self._sessions.conversation_transaction(owner_id, session_id):
            return self._chat_in_session(
                owner_id=owner_id,
                project_id=project_id,
                session_id=session_id,
                payload=payload,
                settings=settings,
                context=context,
                available=available,
            )

    def _chat_in_session(
        self,
        *,
        owner_id: str,
        project_id: str,
        session_id: str,
        payload: AgentChatRequest,
        settings: ModelSettings,
        context: str,
        available: dict[str, SearchResult],
    ) -> AgentChatResponse:
        session = None
        try:
            session = self._sessions.get(owner_id, session_id)
            session_workspace_id = session.data.get("workspace_id") or session.data.get(
                "project_id"
            )
            if session_workspace_id != project_id:
                raise AgentSessionConflictError("Session belongs to another learning space")
        except RecordNotFoundError as error:
            if self._sessions.count(owner_id) >= self._max_sessions:
                raise AgentSessionLimitError("Agent session quota reached") from error

        if session is not None and payload.turn_id:
            turns = session.data.get("turns", {})
            stored_turn = turns.get(payload.turn_id) if isinstance(turns, dict) else None
            if isinstance(stored_turn, dict) and isinstance(stored_turn.get("message"), str):
                stored_citations = stored_turn.get("citations", [])
                citations = [
                    citation
                    for citation in stored_citations
                    if isinstance(citation, str) and citation in available
                ]
                return AgentChatResponse(
                    session_id=session_id,
                    message=_sanitize_reply(stored_turn["message"], set(available)),
                    citations=citations,
                    sources=[available[citation] for citation in citations],
                )

        history = _bounded_history(
            [
                {"role": item["role"], "content": item["content"]}
                for item in (session.data["messages"] if session is not None else [])
            ]
        )
        messages = [
            {"role": "system", "content": context},
            *history,
            {"role": "user", "content": payload.message.strip()},
        ]
        reply = self._transport.complete(settings=settings, messages=messages)
        citations = [
            citation for citation in dict.fromkeys(reply.citations) if citation in available
        ]
        reply_text = _sanitize_reply(reply.text, set(available))

        def append_messages(data):
            data["messages"].extend(
                [
                    {"role": "user", "content": payload.message.strip()},
                    {
                        "role": "assistant",
                        "content": reply_text,
                        "citations": citations,
                    },
                ]
            )
            data["messages"] = _bounded_history(data["messages"])
            if payload.turn_id:
                turns = data.get("turns")
                if not isinstance(turns, dict):
                    turns = {}
                    data["turns"] = turns
                turns[payload.turn_id] = {
                    "message": reply_text,
                    "citations": citations,
                }
                while len(turns) > MAX_SESSION_TURNS:
                    turns.pop(next(iter(turns)))
            return data

        if session is not None:
            self._sessions.mutate(owner_id, session_id, append_messages)
        else:
            with self._sessions.quota_transaction(owner_id):
                try:
                    concurrent_session = self._sessions.get(owner_id, session_id)
                except RecordNotFoundError as error:
                    if self._sessions.count(owner_id) >= self._max_sessions:
                        raise AgentSessionLimitError("Agent session quota reached") from error
                    self._sessions.create(
                        owner_id,
                        session_id,
                        append_messages({"workspace_id": project_id, "messages": [], "turns": {}}),
                    )
                else:
                    concurrent_workspace_id = concurrent_session.data.get(
                        "workspace_id"
                    ) or concurrent_session.data.get("project_id")
                    if concurrent_workspace_id != project_id:
                        raise AgentSessionConflictError("Session belongs to another learning space")
                    self._sessions.mutate(owner_id, session_id, append_messages)
        return AgentChatResponse(
            session_id=session_id,
            message=reply_text,
            citations=citations,
            sources=[available[citation] for citation in citations],
        )

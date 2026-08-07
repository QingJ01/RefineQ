"use client";

import {
  Bot,
  Copy,
  ExternalLink,
  History,
  Plus,
  RotateCcw,
  Send,
  Square,
  Trash2,
} from "lucide-react";
import { FormEvent, KeyboardEvent, useCallback, useEffect, useRef, useState } from "react";

import { SourceDrawer } from "@/components/source-drawer";
import { api, ApiError } from "@/lib/api";
import type { Translator } from "@/lib/i18n";
import type { AgentMessage, AgentSessionSummary, SearchSource } from "@/lib/types";


interface ChatMessage extends AgentMessage {
  sources?: SearchSource[];
  pending?: boolean;
}

interface AgentTurn {
  message: string;
  sessionId: string;
  turnId: string;
}

function errorMessage(caught: unknown, t: Translator): string {
  if (caught instanceof ApiError && caught.code === "model_not_configured") {
    return t("modelRequired");
  }
  if (caught instanceof ApiError) return `${caught.code}: ${caught.message}`;
  return caught instanceof Error ? caught.message : t("error");
}

export function AgentPanel({
  token,
  workspaceId,
  t,
}: {
  token: string;
  workspaceId: string;
  t: Translator;
}) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [message, setMessage] = useState("");
  const [sessionId, setSessionId] = useState<string>();
  const [sessions, setSessions] = useState<AgentSessionSummary[]>([]);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [modelConfigured, setModelConfigured] = useState<boolean | null>(null);
  const [error, setError] = useState("");
  const [failedTurn, setFailedTurn] = useState<AgentTurn | null>(null);
  const [selectedSources, setSelectedSources] = useState<SearchSource[]>([]);
  const [copiedIndex, setCopiedIndex] = useState<number | null>(null);
  const requestController = useRef<AbortController | null>(null);

  const loadSessions = useCallback(async () => {
    setSessions(await api.listWorkspaceAgentSessions(token, workspaceId));
  }, [token, workspaceId]);

  useEffect(() => {
    let active = true;
    Promise.all([api.getModelSettings(token), api.listWorkspaceAgentSessions(token, workspaceId)])
      .then(([settings, history]) => {
        if (!active) return;
        setModelConfigured(settings.configured);
        setSessions(history);
      }).catch((caught: unknown) => {
        if (active) setError(errorMessage(caught, t));
      });
    return () => {
      active = false;
      requestController.current?.abort();
    };
  }, [token, workspaceId, t]);

  async function sendMessage(sent: string, retry?: AgentTurn) {
    if (!sent || busy) return;
    const turn = retry ?? {
      message: sent,
      sessionId: sessionId ?? crypto.randomUUID().replaceAll("-", ""),
      turnId: crypto.randomUUID().replaceAll("-", ""),
    };
    const controller = new AbortController();
    requestController.current = controller;
    setSessionId(turn.sessionId);
    setBusy(true);
    setError("");
    setMessage("");
    if (!retry) {
      setMessages((current) => [
        ...current,
        { role: "user", content: turn.message, citations: [] },
      ]);
    }
    try {
      const reply = await api.chatWorkspace(
        token,
        workspaceId,
        turn.message,
        turn.sessionId,
        turn.turnId,
        controller.signal,
      );
      setSessionId(reply.session_id);
      setFailedTurn(null);
      setMessages((current) => [
        ...current,
        {
          role: "assistant",
          content: reply.message,
          citations: reply.citations,
          sources: reply.sources,
        },
      ]);
      await loadSessions();
    } catch (caught) {
      if (controller.signal.aborted) {
        setError(t("agentStopped"));
        setFailedTurn(turn);
        setMessage(turn.message);
      } else {
        setFailedTurn(turn);
        setError(errorMessage(caught, t));
        if (caught instanceof ApiError && caught.code === "model_not_configured") {
          setModelConfigured(false);
        }
      }
    } finally {
      if (requestController.current === controller) requestController.current = null;
      setBusy(false);
    }
  }

  async function send(event: FormEvent) {
    event.preventDefault();
    await sendMessage(message.trim());
  }

  function stopResponse() {
    requestController.current?.abort();
  }

  function newConversation() {
    requestController.current?.abort();
    setSessionId(undefined);
    setMessages([]);
    setMessage("");
    setError("");
    setFailedTurn(null);
    setHistoryOpen(false);
  }

  async function openSession(id: string) {
    setError("");
    try {
      const detail = await api.getWorkspaceAgentSession(token, workspaceId, id);
      setSessionId(detail.id);
      setMessages(detail.messages);
      setHistoryOpen(false);
    } catch (caught) {
      setError(errorMessage(caught, t));
    }
  }

  async function deleteSession(id: string) {
    if (!window.confirm(t("deleteConversationConfirm"))) return;
    try {
      await api.deleteWorkspaceAgentSession(token, workspaceId, id);
      setSessions((current) => current.filter((item) => item.id !== id));
      if (id === sessionId) newConversation();
    } catch (caught) {
      setError(errorMessage(caught, t));
    }
  }

  async function copyMessage(content: string, index: number) {
    await navigator.clipboard.writeText(content);
    setCopiedIndex(index);
    window.setTimeout(() => setCopiedIndex(null), 1500);
  }

  function composerKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      if (message.trim() && !busy) void sendMessage(message.trim());
    }
  }

  return (
    <section className="content-card agent-card">
      <div className="section-heading agent-heading">
        <div>
          <span className="kicker">GROUNDED / LEARNING MEMORY</span>
          <h2>{t("askCoach")}</h2>
        </div>
        <div className="agent-heading-actions">
          <button type="button" data-testid="agent-history" className="quiet-button" aria-expanded={historyOpen} onClick={() => setHistoryOpen((current) => !current)}><History size={15} /> {t("conversationHistory")}</button>
          <button type="button" data-testid="agent-new-conversation" className="quiet-button" onClick={newConversation}><Plus size={15} /> {t("newConversation")}</button>
          <span data-testid="model-status" className={modelConfigured ? "agent-model-status ready" : "agent-model-status"}>
            {modelConfigured ? "AI READY" : "ADMIN SETUP REQUIRED"}
          </span>
        </div>
      </div>
      {historyOpen && (
        <aside className="agent-history-panel" aria-label={t("conversationHistory")}>
          {sessions.length === 0 ? <p>{t("noConversations")}</p> : sessions.map((session) => (
            <div key={session.id} className={session.id === sessionId ? "active" : ""}>
              <button type="button" onClick={() => void openSession(session.id)}><strong>{session.preview}</strong><span>{session.message_count} {t("messages")}</span></button>
              <button type="button" aria-label={t("deleteConversation")} onClick={() => void deleteSession(session.id)}><Trash2 size={14} /></button>
            </div>
          ))}
        </aside>
      )}
      {error && (
        <div className="error-banner" role="alert">
          <span>{error}</span>
          {failedTurn && (
            <button data-testid="agent-retry" type="button" onClick={() => void sendMessage(failedTurn.message, failedTurn)} disabled={busy}>
              <RotateCcw size={14} /> {t("retry")}
            </button>
          )}
        </div>
      )}
      <div className="chat-log" role="log" aria-live="polite" aria-busy={busy}>
        {messages.length === 0 && (
          <div className="agent-empty"><Bot size={32} strokeWidth={1.2} /><p>{t("messagePlaceholder")}</p></div>
        )}
        {messages.map((item, index) => (
          <article key={`${item.role}-${index}`} className={`chat-message ${item.role}`}>
            <span>{item.role === "user" ? "YOU" : "REFINEQ"}</span>
            <p>{item.content}</p>
            <div className="chat-message-actions">
              <button type="button" aria-label={t("copyMessage")} onClick={() => void copyMessage(item.content, index)}><Copy size={12} /> {copiedIndex === index ? t("copied") : t("copy")}</button>
              {item.sources && item.sources.length > 0 && (
                <button type="button" onClick={() => setSelectedSources(item.sources ?? [])}><ExternalLink size={12} /> {t("sources")} ({item.sources.length})</button>
              )}
            </div>
          </article>
        ))}
        {busy && <div className="agent-thinking" role="status"><span /><span /><span /> {t("agentThinking")}</div>}
      </div>
      <form className="chat-composer" onSubmit={send}>
        <textarea rows={3} value={message} onChange={(event) => setMessage(event.target.value)} onKeyDown={composerKeyDown} placeholder={t("messagePlaceholder")} aria-label={t("messagePlaceholder")} />
        {busy ? (
          <button type="button" data-testid="agent-stop" className="secondary-action" onClick={stopResponse}><Square size={15} /> {t("stop")}</button>
        ) : (
          <button className="primary-action" disabled={!message.trim()}>{t("send")} <Send size={17} /></button>
        )}
      </form>
      {selectedSources.length > 0 && <SourceDrawer title={t("sources")} sources={selectedSources} onClose={() => setSelectedSources([])} />}
    </section>
  );
}

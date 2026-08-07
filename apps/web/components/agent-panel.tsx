"use client";

import { Bot, ExternalLink, RotateCcw, Send } from "lucide-react";
import { FormEvent, useEffect, useState } from "react";

import { api, ApiError } from "@/lib/api";
import type { Translator } from "@/lib/i18n";


interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  citations?: string[];
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
  const [busy, setBusy] = useState(false);
  const [modelConfigured, setModelConfigured] = useState<boolean | null>(null);
  const [error, setError] = useState("");
  const [failedTurn, setFailedTurn] = useState<AgentTurn | null>(null);

  useEffect(() => {
    let active = true;
    void api.getModelSettings(token).then((settings) => {
      if (!active) return;
      setModelConfigured(settings.configured);
    }).catch((caught: unknown) => {
      if (active) setError(errorMessage(caught, t));
    });
    return () => { active = false; };
  }, [token, workspaceId, t]);

  async function sendMessage(sent: string, retry?: AgentTurn) {
    if (!sent || busy) return;
    const turn = retry ?? {
      message: sent,
      sessionId: sessionId ?? crypto.randomUUID().replaceAll("-", ""),
      turnId: crypto.randomUUID().replaceAll("-", ""),
    };
    setSessionId(turn.sessionId);
    setBusy(true);
    setError("");
    try {
      const reply = await api.chatWorkspace(
        token,
        workspaceId,
        turn.message,
        turn.sessionId,
        turn.turnId,
      );
      setSessionId(reply.session_id);
      setFailedTurn(null);
      setMessages((current) => [
        ...current,
        { role: "user", content: turn.message },
        { role: "assistant", content: reply.message, citations: reply.citations },
      ]);
      setMessage("");
    } catch (caught) {
      setFailedTurn(turn);
      setMessage(turn.message);
      setError(errorMessage(caught, t));
      if (caught instanceof ApiError && caught.code === "model_not_configured") {
        setModelConfigured(false);
      }
    } finally {
      setBusy(false);
    }
  }

  async function send(event: FormEvent) {
    event.preventDefault();
    await sendMessage(message.trim());
  }

  return (
    <section className="content-card agent-card">
      <div className="section-heading">
        <div>
          <span className="kicker">GROUNDED / LEARNING MEMORY</span>
          <h2>{t("askCoach")}</h2>
        </div>
        <span
          data-testid="model-status"
          className={modelConfigured ? "agent-model-status ready" : "agent-model-status"}
        >
          {modelConfigured ? "AI READY" : "ADMIN SETUP REQUIRED"}
        </span>
      </div>
      {error && (
        <div className="error-banner" role="alert">
          <span>{error}</span>
          {failedTurn && (
            <button
              data-testid="agent-retry"
              type="button"
              onClick={() => void sendMessage(failedTurn.message, failedTurn)}
              disabled={busy}
            >
              <RotateCcw size={14} /> {t("retry")}
            </button>
          )}
        </div>
      )}
      <div className="chat-log">
        {messages.length === 0 && (
          <div className="agent-empty">
            <Bot size={32} strokeWidth={1.2} />
            <p>{t("messagePlaceholder")}</p>
          </div>
        )}
        {messages.map((item, index) => (
          <article key={`${item.role}-${index}`} className={`chat-message ${item.role}`}>
            <span>{item.role === "user" ? "YOU" : "REFINEQ"}</span>
            <p>{item.content}</p>
            {item.citations?.map((citation) => (
              <em key={citation}>
                <ExternalLink size={12} /> {t("source")} [{citation}]
              </em>
            ))}
          </article>
        ))}
      </div>
      <form className="chat-composer" onSubmit={send}>
        <textarea
          rows={3}
          value={message}
          onChange={(event) => setMessage(event.target.value)}
          placeholder={t("messagePlaceholder")}
        />
        <button className="primary-action" disabled={busy || !message.trim()}>
          {busy ? t("loading") : t("send")} <Send size={17} />
        </button>
      </form>
    </section>
  );
}

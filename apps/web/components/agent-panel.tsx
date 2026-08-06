"use client";

import { Bot, ExternalLink, RotateCcw, Send, Settings2 } from "lucide-react";
import { FormEvent, useEffect, useState } from "react";

import { api, ApiError } from "@/lib/api";
import type { Translator } from "@/lib/i18n";


interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  citations?: string[];
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
  const [showSettings, setShowSettings] = useState(false);
  const [baseUrl, setBaseUrl] = useState("https://api.openai.com/v1");
  const [model, setModel] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  useEffect(() => {
    let active = true;
    void api.getModelSettings(token).then((settings) => {
      if (!active) return;
      setBaseUrl(settings.base_url);
      setModel(settings.model);
      setShowSettings(!settings.configured);
    }).catch((caught: unknown) => {
      if (active) setError(errorMessage(caught, t));
    });
    return () => { active = false; };
  }, [token, workspaceId, t]);

  async function sendMessage(sent: string) {
    if (!sent || busy) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const reply = await api.chatWorkspace(token, workspaceId, sent, sessionId);
      setSessionId(reply.session_id);
      setMessages((current) => [
        ...current,
        { role: "user", content: sent },
        { role: "assistant", content: reply.message, citations: reply.citations },
      ]);
      setMessage("");
    } catch (caught) {
      setMessage(sent);
      setError(errorMessage(caught, t));
      if (caught instanceof ApiError && caught.code === "model_not_configured") {
        setShowSettings(true);
      }
    } finally {
      setBusy(false);
    }
  }

  async function send(event: FormEvent) {
    event.preventDefault();
    await sendMessage(message.trim());
  }

  async function saveSettings(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await api.updateModelSettings(token, {
        base_url: baseUrl,
        model,
        api_key: apiKey,
        temperature: 0.2,
      });
      setApiKey("");
      setShowSettings(false);
      setNotice(t("settingsSaved"));
    } catch (caught) {
      setError(errorMessage(caught, t));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="paper-card agent-card">
      <div className="section-heading">
        <div>
          <span className="kicker">GROUNDED / LEARNING MEMORY</span>
          <h2>{t("askCoach")}</h2>
        </div>
        <button
          data-testid="model-settings"
          className="icon-button"
          onClick={() => setShowSettings((value) => !value)}
          aria-label={t("modelSettings")}
        >
          <Settings2 size={20} />
        </button>
      </div>
      {error && (
        <div className="error-banner" role="alert">
          <span>{error}</span>
          {message.trim() && (
            <button
              data-testid="agent-retry"
              type="button"
              onClick={() => void sendMessage(message.trim())}
              disabled={busy}
            >
              <RotateCcw size={14} /> {t("retry")}
            </button>
          )}
        </div>
      )}
      {notice && <p role="status">{notice}</p>}
      {showSettings && (
        <form className="settings-strip" onSubmit={saveSettings}>
          <label>
            {t("baseUrl")}
            <input value={baseUrl} onChange={(event) => setBaseUrl(event.target.value)} required />
          </label>
          <label>
            {t("model")}
            <input value={model} onChange={(event) => setModel(event.target.value)} required />
          </label>
          <label>
            {t("apiKey")}
            <input
              type="password"
              value={apiKey}
              onChange={(event) => setApiKey(event.target.value)}
              required
            />
          </label>
          <button className="secondary-action" disabled={busy}>{t("save")}</button>
        </form>
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
            <span>{item.role === "user" ? "YOU" : "RQ"}</span>
            <p>{item.content}</p>
            {item.citations?.map((citation) => (
              <em key={citation}>
                <ExternalLink size={12} /> {t("source")} [{citation}]
              </em>
            ))}
          </article>
        ))}
      </div>
      <form className="chat-compose" onSubmit={send}>
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

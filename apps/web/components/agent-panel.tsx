"use client";

import { Bot, ExternalLink, Send, Settings2 } from "lucide-react";
import { FormEvent, useState } from "react";

import { api } from "@/lib/api";
import type { Translator } from "@/lib/i18n";


interface ChatMessage { role: "user" | "assistant"; content: string; citations?: string[] }

export function AgentPanel({ token, workspaceId, t }: { token: string; workspaceId: string; t: Translator }) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [message, setMessage] = useState("");
  const [sessionId, setSessionId] = useState<string>();
  const [busy, setBusy] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [baseUrl, setBaseUrl] = useState("https://api.openai.com/v1");
  const [model, setModel] = useState("");
  const [apiKey, setApiKey] = useState("");

  async function send(event: FormEvent) {
    event.preventDefault();
    if (!message.trim()) return;
    const sent = message.trim();
    setMessage("");
    setMessages((current) => [...current, { role: "user", content: sent }]);
    setBusy(true);
    try {
      const reply = await api.chatWorkspace(token, workspaceId, sent, sessionId);
      setSessionId(reply.session_id);
      setMessages((current) => [...current, { role: "assistant", content: reply.message, citations: reply.citations }]);
    } finally {
      setBusy(false);
    }
  }

  async function saveSettings(event: FormEvent) {
    event.preventDefault();
    await api.updateModelSettings(token, { base_url: baseUrl, model, api_key: apiKey, temperature: 0.2 });
    setApiKey("");
    setShowSettings(false);
  }

  return (
    <section className="paper-card agent-card">
      <div className="section-heading"><div><span className="kicker">GROUNDED / PROJECT</span><h2>{t("askCoach")}</h2></div><button className="icon-button" onClick={() => setShowSettings((value) => !value)} aria-label={t("modelSettings")}><Settings2 size={20} /></button></div>
      {showSettings && <form className="settings-strip" onSubmit={saveSettings}><label>{t("baseUrl")}<input value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} required /></label><label>{t("model")}<input value={model} onChange={(e) => setModel(e.target.value)} required /></label><label>{t("apiKey")}<input type="password" value={apiKey} onChange={(e) => setApiKey(e.target.value)} required /></label><button className="secondary-action">{t("save")}</button></form>}
      <div className="chat-log">
        {messages.length === 0 && <div className="agent-empty"><Bot size={32} strokeWidth={1.2} /><p>{t("messagePlaceholder")}</p></div>}
        {messages.map((item, index) => <article key={`${item.role}-${index}`} className={`chat-message ${item.role}`}><span>{item.role === "user" ? "YOU" : "RQ"}</span><p>{item.content}</p>{item.citations?.map((citation) => <em key={citation}><ExternalLink size={12} /> {t("source")} [{citation}]</em>)}</article>)}
      </div>
      <form className="chat-compose" onSubmit={send}><textarea rows={3} value={message} onChange={(e) => setMessage(e.target.value)} placeholder={t("messagePlaceholder")} /><button className="primary-action" disabled={busy || !message.trim()}>{busy ? t("loading") : t("send")} <Send size={17} /></button></form>
    </section>
  );
}

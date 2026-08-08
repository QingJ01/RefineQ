"use client";

import Image from "next/image";
import { ArrowUp, LoaderCircle, MessageCircleMore, Settings2, Sparkles } from "lucide-react";
import { FormEvent, useState } from "react";

import type { AgentReply, Locale } from "@/lib/types";


const copy = {
  zh: {
    title: "RefineQ 教练 · 当前步骤",
    intro: "我会结合当前目标、资料和你的回答，帮助你完成这一步。",
    suggestions: ["解释这个框架", "给我一个反例", "我想先动手"],
    placeholder: "向教练提问…",
    send: "发送",
    error: "暂时无法连接教练，你仍可以继续当前学习任务。",
    modelMissing: "学习 Agent 尚未配置模型。练习、资料和进度仍可继续使用。",
    configure: "前往配置",
    fullCoach: "完整对话与历史",
  },
  en: {
    title: "RefineQ coach · Current step",
    intro: "I use your goal, sources, and answers to help with this step.",
    suggestions: ["Explain this framework", "Give me a counterexample", "Let me try first"],
    placeholder: "Ask your coach…",
    send: "Send",
    error: "The coach is temporarily unavailable. You can continue the current task.",
    modelMissing: "The learning Agent has not been configured. Practice, material, and progress remain available.",
    configure: "Open settings",
    fullCoach: "Full conversation and history",
  },
} as const;

export function SessionCoach({
  locale,
  onAsk,
  modelConfigured = true,
  isAdmin = false,
  onConfigure,
  onOpenFullCoach,
}: {
  locale: Locale;
  onAsk: (message: string) => Promise<AgentReply>;
  modelConfigured?: boolean;
  isAdmin?: boolean;
  onConfigure?: () => void;
  onOpenFullCoach?: () => void;
}) {
  const text = copy[locale];
  const [message, setMessage] = useState("");
  const [reply, setReply] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function ask(value: string) {
    const normalized = value.trim();
    if (!normalized || busy) return;
    setBusy(true);
    setError("");
    try {
      const response = await onAsk(normalized);
      setReply(response.message);
      setMessage("");
    } catch {
      setError(text.error);
    } finally {
      setBusy(false);
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    void ask(message);
  }

  return (
    <section className="session-coach" data-testid="session-coach" aria-labelledby="session-coach-title">
      <div className="session-coach-heading">
        <span className="coach-avatar">
          <Image
            src="/assets/refineq-coach-avatar.png"
            alt=""
            aria-hidden="true"
            width={56}
            height={56}
          />
        </span>
        <div>
          <span className="coach-kicker"><Sparkles size={13} /> COACH</span>
          <h3 id="session-coach-title">{text.title}</h3>
        </div>
      </div>
      <p className="coach-intro">{reply || text.intro}</p>
      {onOpenFullCoach && (
        <button
          type="button"
          className="coach-full-link"
          data-testid="open-full-coach"
          onClick={onOpenFullCoach}
        >
          <MessageCircleMore size={14} /> {text.fullCoach}
        </button>
      )}
      {!modelConfigured && (
        <div className="coach-capability-notice" role="status">
          <p>{text.modelMissing}</p>
          {isAdmin && onConfigure && (
            <button
              type="button"
              data-testid="coach-configure-model"
              onClick={onConfigure}
            >
              <Settings2 size={14} /> {text.configure}
            </button>
          )}
        </div>
      )}
      <div className="coach-suggestions" aria-label={locale === "zh" ? "教练快捷问题" : "Coach suggestions"}>
        {text.suggestions.map((suggestion) => (
          <button
            key={suggestion}
            type="button"
            data-testid="session-coach-suggestion"
            disabled={busy || !modelConfigured}
            onClick={() => void ask(suggestion)}
          >
            {suggestion}
          </button>
        ))}
      </div>
      {error && <p className="coach-error" role="status">{error}</p>}
      <form className="session-coach-form" onSubmit={submit}>
        <label className="sr-only" htmlFor="session-coach-input">{text.placeholder}</label>
        <input
          id="session-coach-input"
          data-testid="session-coach-input"
          value={message}
          onChange={(event) => setMessage(event.target.value)}
          placeholder={text.placeholder}
          disabled={busy || !modelConfigured}
        />
        <button type="submit" aria-label={text.send} disabled={busy || !message.trim() || !modelConfigured}>
          {busy ? <LoaderCircle className="spin" size={17} /> : <ArrowUp size={17} />}
        </button>
      </form>
    </section>
  );
}

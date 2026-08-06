"use client";

import { ArrowRight, BrainCircuit, Clock3, Sparkles } from "lucide-react";
import { FormEvent, useState } from "react";

import type { Translator } from "@/lib/i18n";
import type { LearningWorkspace } from "@/lib/types";


export function LearningHome({
  t,
  busy,
  workspaces,
  onResolve,
  onOpen,
}: {
  t: Translator;
  busy: boolean;
  workspaces: LearningWorkspace[];
  onResolve: (intent: string) => void | Promise<void>;
  onOpen: (workspace: LearningWorkspace) => void | Promise<void>;
}) {
  const [intent, setIntent] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!intent.trim()) return;
    await onResolve(intent.trim());
  }

  return (
    <main className="learning-home">
      <section className="learning-home-hero">
        <span className="kicker">PERSONAL LEARNING AGENT</span>
        <BrainCircuit size={46} strokeWidth={1.25} />
        <h1>{t("learningPrompt")}</h1>
        <p>{t("learningPromptHint")}</p>
        <form className="intent-compose" onSubmit={submit}>
          <textarea
            data-testid="learning-intent"
            value={intent}
            onChange={(event) => setIntent(event.target.value)}
            placeholder={t("learningIntentPlaceholder")}
            rows={4}
            autoFocus
          />
          <button data-testid="start-learning" className="primary-action" disabled={busy || !intent.trim()}>
            <Sparkles size={17} /> {busy ? t("loading") : t("startLearning")}
            <ArrowRight size={18} />
          </button>
        </form>
        <small className="routing-note"><Sparkles size={13} /> {t("autoRouting")}</small>
      </section>
      {workspaces.length > 0 && (
        <section className="recent-learning">
          <div className="section-heading">
            <div><span className="kicker">MEMORY / CONTINUE</span><h2>{t("recentLearning")}</h2></div>
            <Clock3 size={22} />
          </div>
          <div className="recent-grid">
            {workspaces.map((workspace) => (
              <button key={workspace.id} onClick={() => onOpen(workspace)}>
                <span>{workspace.subject}</span>
                <strong>{workspace.title}</strong>
                <p>{workspace.goal}</p>
                <ArrowRight size={16} />
              </button>
            ))}
          </div>
        </section>
      )}
    </main>
  );
}

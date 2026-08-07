"use client";

import {
  ArrowRight,
  Clock3,
  History,
  Languages,
  LogOut,
  MessageSquarePlus,
  Settings2,
  Sparkles,
} from "lucide-react";
import { FormEvent, useState } from "react";

import { BrandMark, BrandName } from "@/components/brand";
import type { Translator } from "@/lib/i18n";
import type { LearningWorkspace } from "@/lib/types";


export function LearningHome({
  t,
  busy,
  workspaces,
  onResolve,
  onOpen,
  isAdmin = false,
  onAdmin,
  onLogout,
  onToggleLocale,
}: {
  t: Translator;
  busy: boolean;
  workspaces: LearningWorkspace[];
  onResolve: (intent: string) => void | Promise<void>;
  onOpen: (workspace: LearningWorkspace) => void | Promise<void>;
  isAdmin?: boolean;
  onAdmin?: () => void;
  onLogout: () => void;
  onToggleLocale: () => void;
}) {
  const [intent, setIntent] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!intent.trim()) return;
    await onResolve(intent.trim());
  }

  return (
    <main className="home-shell">
      <aside className="home-sidebar">
        <div className="sidebar-brand">
          <BrandMark className="brand-mark" size={36} />
          <BrandName />
        </div>
        <div className="home-nav-item active"><MessageSquarePlus size={19} /><span>{t("startLearning")}</span></div>
        <div className="home-nav-item"><History size={19} /><span>{t("recentLearning")}</span></div>
        {isAdmin && (
          <button className="home-nav-item home-admin-link" onClick={onAdmin}>
            <Settings2 size={19} /><span>平台控制台</span>
          </button>
        )}
        <div className="home-sidebar-actions">
          <button
            data-testid="home-language"
            className="home-nav-item home-admin-link"
            onClick={onToggleLocale}
          >
            <Languages size={19} /><span>{t("language")}</span>
          </button>
          <button
            data-testid="home-logout"
            className="home-nav-item home-admin-link"
            onClick={onLogout}
          >
            <LogOut size={19} /><span>{t("logout")}</span>
          </button>
          <p className="sidebar-footnote">Personal learning, remembered.</p>
        </div>
      </aside>
      <section className="learning-home">
        <div className="learning-home-hero">
          <div className="learning-brand-hero" aria-hidden="true"><BrandMark size={58} /></div>
          <span className="kicker">PERSONAL LEARNING AGENT</span>
          <h1>{t("learningPrompt")}</h1>
          <p>{t("learningPromptHint")}</p>
          <form className="learning-composer" onSubmit={submit}>
            <textarea
              data-testid="learning-intent"
              value={intent}
              onChange={(event) => setIntent(event.target.value)}
              placeholder={t("learningIntentPlaceholder")}
              rows={3}
              autoFocus
            />
            <div className="composer-footer">
              <small className="routing-note"><Sparkles size={14} /> {t("autoRouting")}</small>
              <button data-testid="start-learning" className="composer-send" disabled={busy || !intent.trim()} aria-label={t("startLearning")}>
                {busy ? <span>{t("loading")}</span> : <ArrowRight size={19} />}
              </button>
            </div>
          </form>
        </div>
        {workspaces.length > 0 && (
          <section className="recent-learning">
            <div className="section-heading compact">
              <div><span className="kicker">CONTINUE LEARNING</span><h2>{t("recentLearning")}</h2></div>
              <Clock3 size={20} />
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
      </section>
    </main>
  );
}

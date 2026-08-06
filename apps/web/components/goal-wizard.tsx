"use client";

import { ArrowRight, Target } from "lucide-react";
import { FormEvent, useState } from "react";

import type { Translator } from "@/lib/i18n";
import type { TopicSeed } from "@/lib/types";


export interface GoalDraft {
  projectName: string;
  goal: string;
  examAt: string;
  dailyMinutes: number;
  topics: TopicSeed[];
}

export function GoalWizard({
  t,
  busy,
  onCreate,
}: {
  t: Translator;
  busy: boolean;
  onCreate: (draft: GoalDraft) => Promise<void>;
}) {
  const [projectName, setProjectName] = useState("");
  const [goal, setGoal] = useState("");
  const [examAt, setExamAt] = useState("");
  const [dailyMinutes, setDailyMinutes] = useState(45);
  const [topics, setTopics] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    const parsed = topics.split(/[,，]/).map((name) => name.trim()).filter(Boolean);
    await onCreate({
      projectName,
      goal,
      examAt: new Date(`${examAt}T09:00:00`).toISOString(),
      dailyMinutes,
      topics: parsed.map((name, index) => ({
        id: `topic-${index + 1}`,
        name,
        knowledge_type: "concept",
      })),
    });
  }

  return (
    <main className="wizard-stage">
      <section className="wizard-intro">
        <span className="kicker">DOSSIER SETUP / 02</span>
        <Target size={42} strokeWidth={1.3} />
        <h1>{t("createProject")}</h1>
        <p>{t("brandTagline")}</p>
      </section>
      <form className="paper-card wizard-form" onSubmit={submit}>
        <label>{t("projectName")}<input value={projectName} onChange={(e) => setProjectName(e.target.value)} required /></label>
        <label>{t("goal")}<textarea value={goal} onChange={(e) => setGoal(e.target.value)} rows={3} required /></label>
        <div className="form-pair">
          <label>{t("examDate")}<input type="date" value={examAt} onChange={(e) => setExamAt(e.target.value)} required /></label>
          <label>{t("dailyMinutes")}<input type="number" min={5} max={480} value={dailyMinutes} onChange={(e) => setDailyMinutes(Number(e.target.value))} required /></label>
        </div>
        <label>{t("topics")}<textarea value={topics} onChange={(e) => setTopics(e.target.value)} placeholder="Limits, Derivatives, Integrals" rows={3} required /></label>
        <button className="primary-action wide" disabled={busy}>{busy ? t("loading") : t("startPlan")} <ArrowRight size={18} /></button>
      </form>
    </main>
  );
}

import type { Translator } from "@/lib/i18n";
import type { Locale, StudyPlan } from "@/lib/types";
import { buildPlanRows } from "@/lib/view-models";


export function PlanTimeline({
  plan,
  locale,
  t,
}: {
  plan: StudyPlan | null;
  locale: Locale;
  t: Translator;
}) {
  if (!plan) {
    return <div className="empty-note">{t("noPlan")}</div>;
  }
  const rows = buildPlanRows(plan, locale === "zh" ? "zh-CN" : "en-US");
  return (
    <section className="content-card plan-card" aria-labelledby="plan-heading">
      <div className="section-heading">
        <div>
          <span className="kicker">PLAN / {String(rows.length).padStart(2, "0")}</span>
          <h2 id="plan-heading">{t("plan")}</h2>
        </div>
        <span className="minute-badge">{plan.daily_minutes} {t("minutes")}</span>
      </div>
      <ol className="plan-timeline">
        {rows.map((row) => (
          <li key={row.id} className="plan-session">
            <span className="sequence">{String(row.sequence).padStart(2, "0")}</span>
            <span className="timeline-rule" aria-hidden="true" />
            <div className="plan-topic">
              <strong>{row.topic}</strong>
              <span>{row.dateLabel}</span>
            </div>
            <span className="plan-minutes">{row.minutesLabel}</span>
          </li>
        ))}
      </ol>
    </section>
  );
}

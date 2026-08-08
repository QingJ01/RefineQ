import { Activity, CalendarCheck2, TrendingUp } from "lucide-react";

import type { LearningInsights, Locale, Progress } from "@/lib/types";


const DAY_MS = 24 * 60 * 60 * 1000;

export function summarizeLearningWeek(
  progress: Progress,
  insights: LearningInsights,
  now: Date = new Date(),
) {
  const windowStart = now.getTime() - (7 * DAY_MS);
  const attempts = insights.attempts.filter((attempt) => {
    const observedAt = new Date(attempt.observed_at).getTime();
    return observedAt >= windowStart && observedAt <= now.getTime();
  });
  const activeDays = new Set(attempts.map((attempt) => attempt.observed_at.slice(0, 10))).size;
  const averageScore = attempts.length > 0
    ? Math.round(attempts.reduce((total, attempt) => total + attempt.score, 0) / attempts.length)
    : null;
  const masteryChanges = Object.entries(progress.mastery).flatMap(([topicId, current]) => {
    const baseline = insights.mastery_history
      .filter((point) => point.topic_id === topicId && new Date(point.observed_at).getTime() < windowStart)
      .sort((left, right) => right.observed_at.localeCompare(left.observed_at))[0];
    return baseline ? [current - baseline.mastery] : [];
  });
  const masteryChange = masteryChanges.length > 0
    ? masteryChanges.reduce((total, value) => total + value, 0) / masteryChanges.length
    : null;

  return { activeDays, attempts: attempts.length, averageScore, masteryChange };
}

export function LearningReport({
  locale,
  progress,
  insights,
  now,
}: {
  locale: Locale;
  progress: Progress;
  insights: LearningInsights;
  now?: Date;
}) {
  const zh = locale === "zh";
  const summary = summarizeLearningWeek(progress, insights, now);
  const attemptLabel = zh
    ? `${summary.attempts} 次练习`
    : `${summary.attempts} ${summary.attempts === 1 ? "attempt" : "attempts"}`;
  const masteryLabel = summary.masteryChange === null
    ? (zh ? "暂无对比" : "No baseline yet")
    : `${summary.masteryChange >= 0 ? "+" : ""}${Math.round(summary.masteryChange * 100)}%`;

  return (
    <section className="content-card learning-report" data-testid="learning-report" aria-labelledby="learning-report-heading">
      <div className="section-heading">
        <div>
          <span className="kicker">REPORT / LAST 7 DAYS</span>
          <h2 id="learning-report-heading">{zh ? "近 7 天学习报告" : "Last 7 days"}</h2>
        </div>
        <Activity size={22} strokeWidth={1.5} />
      </div>
      <div className="learning-report-grid">
        <div><CalendarCheck2 size={18} /><strong>{summary.activeDays}</strong><span>{zh ? "活跃天数" : "active days"}</span></div>
        <div><Activity size={18} /><strong>{attemptLabel}</strong><span>{zh ? "窗口内练习" : "in this window"}</span></div>
        <div><TrendingUp size={18} /><strong>{masteryLabel}</strong><span>{zh ? "平均掌握度变化" : "average mastery change"}</span></div>
        <div><strong>{summary.averageScore ?? "—"}</strong><span>{zh ? "平均得分" : "average score"}</span></div>
      </div>
    </section>
  );
}

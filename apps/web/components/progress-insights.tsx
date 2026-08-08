import { ArrowUpRight, Target } from "lucide-react";

import type { Translator } from "@/lib/i18n";
import type { LearningInsights, Progress } from "@/lib/types";


export function ProgressInsights({
  progress,
  t,
  onPracticeTopic,
  insights,
  onSelectTopic,
  topicLabels = {},
  busy = false,
  loading = false,
}: {
  progress: Progress | null;
  t: Translator;
  onPracticeTopic?: (topicId: string) => void | Promise<void>;
  insights?: LearningInsights | null;
  onSelectTopic?: (topicId: string) => void;
  topicLabels?: Record<string, string>;
  busy?: boolean;
  loading?: boolean;
}) {
  const labels = { ...(progress?.topics ?? {}), ...topicLabels };
  const topics = Object.entries(progress?.mastery ?? {})
    .sort((left, right) => left[1] - right[1]);
  const recommended = topics[0];

  if (loading) {
    return <section className="content-card progress-insights" data-testid="progress-insights-loading"><div className="empty-note">{t("loading")}</div></section>;
  }

  if (!progress || topics.length === 0) {
    return <div className="empty-note">{t("noProgress")}</div>;
  }

  return (
    <section className="content-card progress-insights" aria-labelledby="progress-heading">
      <div className="section-heading">
        <div>
          <span className="kicker">MASTERY / INSIGHTS</span>
          <h2 id="progress-heading">{t("progressInsights")}</h2>
        </div>
        <Target size={22} strokeWidth={1.5} />
      </div>
      <div className="topic-mastery-list">
        {topics.map(([topic, mastery]) => {
          const topicInsight = insights?.topics.find((item) => item.topic_id === topic);
          return (
          <div key={topic} className="topic-mastery-row">
            <button
              type="button"
              data-testid={`progress-topic-${topic}`}
              onClick={() => onSelectTopic?.(topic)}
            >
              <span>{labels[topic] ?? topic}</span>
              {topicInsight && <small>{topicInsight.attempt_count} · {topicInsight.error_count}</small>}
            </button>
            <div role="progressbar" aria-label={labels[topic] ?? topic} aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(mastery * 100)}>
              <i style={{ width: `${Math.round(mastery * 100)}%` }} />
            </div>
            <strong>{Math.round(mastery * 100)}%</strong>
          </div>
          );
        })}
      </div>
      {recommended && (
        <div className="progress-recommendation" data-testid="progress-recommendation">
          <ArrowUpRight size={17} />
          <span>{t("recommendedNext")} <strong>{labels[recommended[0]] ?? recommended[0]}</strong></span>
          <button
            type="button"
            data-testid="practice-recommended-topic"
            disabled={busy}
            onClick={() => void onPracticeTopic?.(recommended[0])}
          >{t("practiceRecommended")}</button>
        </div>
      )}
    </section>
  );
}

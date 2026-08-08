import { Activity, X } from "lucide-react";

import type { Locale, MasteryHistoryPoint, TopicInsight } from "@/lib/types";


const copy = {
  zh: { attempts: "次练习", errors: "次错误", history: "掌握度变化", close: "关闭主题明细", empty: "还没有这个主题的练习记录。" },
  en: { attempts: "attempts", errors: "errors", history: "Mastery history", close: "Close topic detail", empty: "No practice history for this topic yet." },
} as const;

export function ProgressTopicDetail({
  locale,
  topic,
  history,
  onClose,
}: {
  locale: Locale;
  topic: TopicInsight;
  history: MasteryHistoryPoint[];
  onClose: () => void;
}) {
  const text = copy[locale];
  const topicHistory = history.filter((item) => item.topic_id === topic.topic_id);
  return (
    <section className="content-card progress-topic-detail" data-testid="progress-topic-detail" aria-labelledby="progress-topic-heading">
      <header>
        <div><span className="kicker">TOPIC / DETAIL</span><h2 id="progress-topic-heading">{topic.topic_name}</h2></div>
        <button type="button" aria-label={text.close} onClick={onClose}><X size={17} /></button>
      </header>
      <div className="topic-detail-metrics">
        <strong>{Math.round(topic.mastery * 100)}%</strong>
        <span>{topic.attempt_count} {text.attempts}</span>
        <span>{topic.error_count} {topic.error_count === 1 && locale === "en" ? "error" : text.errors}</span>
      </div>
      <h3><Activity size={16} /> {text.history}</h3>
      {topicHistory.length === 0 ? <div className="empty-note">{text.empty}</div> : (
        <ol>
          {topicHistory.map((item) => (
            <li key={item.attempt_id}><time dateTime={item.observed_at}>{new Intl.DateTimeFormat(locale === "zh" ? "zh-CN" : "en-US", { month: "short", day: "numeric" }).format(new Date(item.observed_at))}</time><i style={{ width: `${Math.round(item.mastery * 100)}%` }} /><strong>{Math.round(item.mastery * 100)}%</strong></li>
          ))}
        </ol>
      )}
    </section>
  );
}

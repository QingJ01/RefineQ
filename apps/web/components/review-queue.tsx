import { ArrowRight, Clock3, RotateCcw } from "lucide-react";

import type { DueReviewInsight, Locale } from "@/lib/types";


const copy = {
  zh: {
    title: "到期复习",
    empty: "当前没有到期复习，继续按计划学习即可。",
    overdue: "已到期",
    due: "应复习",
    start: "开始复习",
    minutes: "分钟",
  },
  en: {
    title: "Due reviews",
    empty: "Nothing is due now. Continue with the current plan.",
    overdue: "Overdue",
    due: "Due",
    start: "Start review",
    minutes: "min",
  },
} as const;

export function ReviewQueue({
  locale,
  reviews,
  onStartReview,
}: {
  locale: Locale;
  reviews: DueReviewInsight[];
  onStartReview: (review: DueReviewInsight) => void | Promise<void>;
}) {
  const text = copy[locale];
  return (
    <section className="content-card review-queue" data-testid="review-queue" aria-labelledby="review-queue-heading">
      <div className="section-heading">
        <div><span className="kicker">REVIEW / {String(reviews.length).padStart(2, "0")}</span><h2 id="review-queue-heading">{text.title}</h2></div>
        <RotateCcw size={21} strokeWidth={1.5} />
      </div>
      {reviews.length === 0 ? (
        <div className="empty-note" data-testid="review-queue-empty">{text.empty}</div>
      ) : (
        <ol>
          {reviews.map((review) => (
            <li key={review.session_id}>
              <div><strong>{review.topic_name}</strong><span><Clock3 size={13} /> {review.minutes} {text.minutes}</span></div>
              <small>{review.overdue ? text.overdue : text.due} · {new Intl.DateTimeFormat(locale === "zh" ? "zh-CN" : "en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }).format(new Date(review.due_at))}</small>
              <button type="button" data-testid={`start-review-${review.session_id}`} onClick={() => void onStartReview(review)}>{text.start} <ArrowRight size={15} /></button>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

import { BookOpenCheck } from "lucide-react";

import type { Translator } from "@/lib/i18n";
import type { LearningEvidence, Locale } from "@/lib/types";
import { evidenceTone } from "@/lib/view-models";


export function EvidenceLedger({
  evidence,
  locale,
  t,
}: {
  evidence: LearningEvidence[];
  locale: Locale;
  t: Translator;
}) {
  return (
    <section className="paper-card ledger" aria-labelledby="ledger-heading">
      <div className="section-heading">
        <div>
          <span className="kicker">EVIDENCE / {String(evidence.length).padStart(2, "0")}</span>
          <h2 id="ledger-heading">{t("evidenceLedger")}</h2>
        </div>
        <BookOpenCheck size={22} strokeWidth={1.5} />
      </div>
      {evidence.length === 0 ? (
        <div className="empty-note">{t("noEvidence")}</div>
      ) : (
        <ol className="ledger-list">
          {evidence.map((item) => (
            <li key={item.id} data-tone={evidenceTone(item.kind)}>
              <div className="ledger-date">
                {new Intl.DateTimeFormat(locale === "zh" ? "zh-CN" : "en-US", {
                  month: "short",
                  day: "numeric",
                  hour: "2-digit",
                  minute: "2-digit",
                }).format(new Date(item.observed_at))}
              </div>
              <div className="ledger-mark" aria-hidden="true" />
              <div>
                <span className="evidence-kind">{item.kind}</span>
                <p>{item.summary}</p>
              </div>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

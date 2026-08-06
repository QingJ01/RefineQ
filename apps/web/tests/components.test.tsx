import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { EvidenceLedger } from "../components/evidence-ledger";
import { PlanTimeline } from "../components/plan-timeline";
import { PracticeCard } from "../components/practice-card";
import { translator } from "../lib/i18n";


const t = translator("en");

describe("focused learning components", () => {
  it("renders plan sessions as a numbered study path", () => {
    const html = renderToStaticMarkup(
      <PlanTimeline
        locale="en"
        t={t}
        plan={{
          id: "plan-1",
          goal: "Pass calculus",
          exam_at: "2026-08-10T08:00:00Z",
          daily_minutes: 45,
          sessions: [
            {
              id: "session-1",
              topic_id: "limits",
              planned_at: "2026-08-06T08:00:00Z",
              minutes: 45,
            },
          ],
        }}
      />,
    );

    expect(html).toContain("limits");
    expect(html).toContain("01");
    expect(html).toContain("45 min");
  });

  it("renders evidence as a dated ledger", () => {
    const html = renderToStaticMarkup(
      <EvidenceLedger
        locale="en"
        t={t}
        evidence={[
          {
            id: "evidence-1",
            kind: "attempt",
            source_id: "attempt-1",
            summary: "Practice response for limits was correct.",
            observed_at: "2026-08-06T08:00:00Z",
            details: {},
          },
        ]}
      />,
    );

    expect(html).toContain("Learning evidence ledger");
    expect(html).toContain("Practice response for limits was correct.");
    expect(html).toContain("data-tone=\"jade\"");
  });

  it("never renders an expected answer in the practice card", () => {
    const html = renderToStaticMarkup(
      <PracticeCard
        t={t}
        question={{ id: "question-1", topic_id: "limits", prompt: "Explain a limit" }}
        answer=""
        result={null}
        busy={false}
        onAnswerChange={() => undefined}
        onGetQuestion={() => undefined}
        onSubmit={() => undefined}
      />,
    );

    expect(html).toContain("Explain a limit");
    expect(html).not.toContain("expected_answer");
  });
});

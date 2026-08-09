import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const styles = readFileSync(
  fileURLToPath(new URL("../app/styles.css", import.meta.url)),
  "utf8",
);

describe("mobile session layout", () => {
  it("keeps the reflect-stage primary action in flow so it cannot cover the feedback text", () => {
    // The practice stage keeps its sticky submit button (an input-time affordance),
    // but the reflect stage is a reading surface: a floating button there overlaps
    // the score and feedback the learner is still reading.
    expect(styles).toMatch(
      /\.session-feedback\s+\.mobile-sticky-task-action\s*\{[^}]*position:\s*static/s,
    );
  });
});

import { describe, expect, it, vi } from "vitest";

import { loadNextQuestion } from "../lib/practice-flow";
import type { PracticeQuestion } from "../lib/types";

function makeQuestion(id: string): PracticeQuestion {
  return { id, topic_id: "t", prompt: `prompt ${id}` };
}

describe("loadNextQuestion staleness guard", () => {
  it("drops a response that was superseded while it was loading", async () => {
    let current = true;
    const apply = vi.fn();

    await loadNextQuestion(
      async () => {
        // A newer request started while this one was in flight.
        current = false;
        return makeQuestion("A");
      },
      apply,
      () => current,
    );

    expect(apply).not.toHaveBeenCalled();
  });

  it("applies a response that is still the latest request", async () => {
    const apply = vi.fn();

    await loadNextQuestion(async () => makeQuestion("B"), apply, () => true);

    expect(apply).toHaveBeenCalledTimes(1);
    expect(apply).toHaveBeenCalledWith(makeQuestion("B"));
  });

  it("applies when no guard is supplied (backward compatible)", async () => {
    const apply = vi.fn();

    await loadNextQuestion(async () => makeQuestion("C"), apply);

    expect(apply).toHaveBeenCalledTimes(1);
  });
});

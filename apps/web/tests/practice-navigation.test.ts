import { describe, expect, it, vi } from "vitest";

import {
  guardPracticeNavigation,
  hasUnsavedPracticeDraft,
  navigationBlockReason,
} from "../lib/practice-navigation";


describe("practice draft navigation", () => {
  it("runs immediately without a draft", () => {
    const action = vi.fn();
    const defer = vi.fn();

    expect(guardPracticeNavigation(false, action, defer)).toBe(true);
    expect(action).toHaveBeenCalledOnce();
    expect(defer).not.toHaveBeenCalled();
  });

  it("defers replacement until the learner confirms", () => {
    const action = vi.fn();
    const pending: Array<() => void | Promise<void>> = [];

    expect(guardPracticeNavigation(true, action, (next) => { pending.push(next); })).toBe(false);
    expect(action).not.toHaveBeenCalled();
    pending[0]?.();
    expect(action).toHaveBeenCalledOnce();
  });

  it("only treats an ungraded non-empty answer as an unsaved draft", () => {
    expect(hasUnsavedPracticeDraft(" work ", true, false)).toBe(true);
    expect(hasUnsavedPracticeDraft("", true, false)).toBe(false);
    expect(hasUnsavedPracticeDraft(" work ", false, false)).toBe(false);
    expect(hasUnsavedPracticeDraft(" work ", true, true)).toBe(false);
  });

  it("prioritizes an active upload when deciding whether route navigation must pause", () => {
    expect(navigationBlockReason({ uploadActive: true, unsavedDraft: true })).toBe("upload");
    expect(navigationBlockReason({ uploadActive: false, unsavedDraft: true })).toBe("draft");
    expect(navigationBlockReason({ uploadActive: false, unsavedDraft: false })).toBeNull();
  });
});

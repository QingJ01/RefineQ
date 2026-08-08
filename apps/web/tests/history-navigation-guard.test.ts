import { describe, expect, it, vi } from "vitest";

import {
  consumeHistoryUploadContinuation,
  installHistoryNavigationGuard,
} from "../lib/history-navigation-guard";


class FakeNavigation {
  private listener: ((event: Event) => void) | null = null;
  traverseTo = vi.fn();

  addEventListener(_type: "navigate", listener: (event: Event) => void) {
    this.listener = listener;
  }

  removeEventListener(_type: "navigate", listener: (event: Event) => void) {
    if (this.listener === listener) this.listener = null;
  }

  emit(event: Event) {
    this.listener?.(event);
  }
}

class FakePopstateTarget {
  private listener: (() => void) | null = null;

  addEventListener(_type: "popstate", listener: () => void) {
    this.listener = listener;
  }

  removeEventListener(_type: "popstate", listener: () => void) {
    if (this.listener === listener) this.listener = null;
  }

  emit() {
    this.listener?.();
  }
}

function traversalEvent() {
  return {
    canIntercept: true,
    navigationType: "traverse",
    destination: { key: "previous-entry" },
    preventDefault: vi.fn(),
  } as unknown as Event;
}

describe("history navigation guard", () => {
  it("cancels a traversal and resumes the exact history entry after confirmation", () => {
    const navigation = new FakeNavigation();
    let resume: (() => void) | null = null;
    const stop = installHistoryNavigationGuard(
      navigation,
      () => "upload",
      (_reason, next) => { resume = next; },
    );
    const event = traversalEvent();

    navigation.emit(event);

    expect((event as unknown as { preventDefault: () => void }).preventDefault).toHaveBeenCalledOnce();
    expect(resume).not.toBeNull();
    (resume as unknown as () => void)();
    expect(navigation.traverseTo).toHaveBeenCalledWith("previous-entry");
    stop();
  });

  it("does not interfere when no upload or draft blocks navigation", () => {
    const navigation = new FakeNavigation();
    const onBlocked = vi.fn();
    installHistoryNavigationGuard(navigation, () => null, onBlocked);
    const event = traversalEvent();

    navigation.emit(event);

    expect((event as unknown as { preventDefault: () => void }).preventDefault).not.toHaveBeenCalled();
    expect(onBlocked).not.toHaveBeenCalled();
  });

  it("keeps an upload running during history traversal when Navigation API is unavailable", () => {
    const fallback = new FakePopstateTarget();
    installHistoryNavigationGuard(undefined, () => "upload", vi.fn(), fallback);

    fallback.emit();

    expect(consumeHistoryUploadContinuation()).toBe(true);
    expect(consumeHistoryUploadContinuation()).toBe(false);
  });
});

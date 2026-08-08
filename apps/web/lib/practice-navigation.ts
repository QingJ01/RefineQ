export type PracticeNavigationAction = () => void | Promise<void>;

export type NavigationBlockReason = "upload" | "draft";

export function navigationBlockReason({
  uploadActive,
  unsavedDraft,
}: {
  uploadActive: boolean;
  unsavedDraft: boolean;
}): NavigationBlockReason | null {
  if (uploadActive) return "upload";
  if (unsavedDraft) return "draft";
  return null;
}

export function hasUnsavedPracticeDraft(
  answer: string,
  hasQuestion: boolean,
  hasResult: boolean,
): boolean {
  return hasQuestion && !hasResult && answer.trim().length > 0;
}

export function guardPracticeNavigation(
  hasDraft: boolean,
  action: PracticeNavigationAction,
  defer: (action: PracticeNavigationAction) => void,
): boolean {
  if (hasDraft) {
    defer(action);
    return false;
  }
  void action();
  return true;
}

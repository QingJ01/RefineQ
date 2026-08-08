import type { NavigationBlockReason } from "./practice-navigation";


interface HistoryDestination {
  key: string;
}

interface HistoryNavigateEvent extends Event {
  canIntercept: boolean;
  navigationType: string;
  destination: HistoryDestination;
}

export interface HistoryNavigation {
  addEventListener(type: "navigate", listener: (event: Event) => void): void;
  removeEventListener(type: "navigate", listener: (event: Event) => void): void;
  traverseTo(key: string): unknown;
}

export interface HistoryTraversalTarget {
  addEventListener(type: "popstate", listener: () => void): void;
  removeEventListener(type: "popstate", listener: () => void): void;
}

let continueUploadUntil = 0;

export function browserHistoryNavigation(target: Window): HistoryNavigation | undefined {
  return (target as Window & { navigation?: HistoryNavigation }).navigation;
}

export function browserHistoryTraversalTarget(target: Window): HistoryTraversalTarget {
  return target as unknown as HistoryTraversalTarget;
}

export function consumeHistoryUploadContinuation(now = Date.now()): boolean {
  const shouldContinue = now <= continueUploadUntil;
  continueUploadUntil = 0;
  return shouldContinue;
}

export function installHistoryNavigationGuard(
  navigation: HistoryNavigation | undefined,
  blockReason: () => NavigationBlockReason | null,
  onBlocked: (reason: NavigationBlockReason, resume: () => void) => void,
  fallbackTarget?: HistoryTraversalTarget,
): () => void {
  if (!navigation) {
    if (!fallbackTarget) return () => undefined;
    const onPopstate = () => {
      if (blockReason() === "upload") continueUploadUntil = Date.now() + 1_000;
    };
    fallbackTarget.addEventListener("popstate", onPopstate);
    return () => fallbackTarget.removeEventListener("popstate", onPopstate);
  }
  let resumedDestinationKey: string | null = null;
  const onNavigate = (rawEvent: Event) => {
    const event = rawEvent as HistoryNavigateEvent;
    if (
      !event.canIntercept
      || event.navigationType !== "traverse"
      || !event.destination?.key
    ) return;
    if (resumedDestinationKey === event.destination.key) {
      resumedDestinationKey = null;
      return;
    }
    const reason = blockReason();
    if (!reason) return;
    event.preventDefault();
    const destinationKey = event.destination.key;
    onBlocked(reason, () => {
      resumedDestinationKey = destinationKey;
      navigation.traverseTo(destinationKey);
    });
  };
  navigation.addEventListener("navigate", onNavigate);
  return () => navigation.removeEventListener("navigate", onNavigate);
}

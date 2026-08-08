export const learningSections = ["today", "path", "materials", "calendar", "progress"] as const;

export type LearningSection = (typeof learningSections)[number];

export function parseLearningSection(value: string): LearningSection | null {
  if (value === "evidence") return "progress";
  if (value === "coach") return "today";
  return learningSections.includes(value as LearningSection) ? value as LearningSection : null;
}

export function learningPath(workspaceId: string, section: LearningSection): string {
  return `/learn/${encodeURIComponent(workspaceId)}/${section}`;
}

export type LearningShellRoute =
  | { kind: "home" }
  | { kind: "workspace"; workspaceId: string; section: LearningSection }
  | { kind: "other" };

export function resolveLearningShellPath(pathname: string): LearningShellRoute {
  if (pathname === "/") return { kind: "home" };
  const match = pathname.match(/^\/learn\/([^/]+)\/([^/]+)\/?$/);
  if (!match) return { kind: "other" };
  const section = parseLearningSection(match[2]);
  if (!section) return { kind: "other" };
  try {
    const workspaceId = decodeURIComponent(match[1]);
    return workspaceId ? { kind: "workspace", workspaceId, section } : { kind: "other" };
  } catch {
    return { kind: "other" };
  }
}

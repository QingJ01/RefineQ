export const learningSections = ["today", "path", "materials", "progress"] as const;

export type LearningSection = (typeof learningSections)[number];

export function parseLearningSection(value: string): LearningSection | null {
  if (value === "evidence") return "progress";
  if (value === "coach") return "today";
  return learningSections.includes(value as LearningSection) ? value as LearningSection : null;
}

export function learningPath(workspaceId: string, section: LearningSection): string {
  return `/learn/${encodeURIComponent(workspaceId)}/${section}`;
}

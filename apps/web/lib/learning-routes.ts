export const learningSections = ["today", "materials", "calendar", "evidence", "coach"] as const;

export type LearningSection = (typeof learningSections)[number];

export function parseLearningSection(value: string): LearningSection | null {
  return learningSections.includes(value as LearningSection) ? value as LearningSection : null;
}

export function learningPath(workspaceId: string, section: LearningSection): string {
  return `/learn/${encodeURIComponent(workspaceId)}/${section}`;
}

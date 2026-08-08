import { StudyWorkspace } from "@/components/study-workspace";
import type { LearningSection } from "@/lib/learning-routes";


export function LearningRoute({
  workspaceId,
  section,
}: {
  workspaceId: string;
  section: LearningSection;
}) {
  return (
    <StudyWorkspace
      key={workspaceId}
      initialWorkspaceId={workspaceId}
      initialSection={section}
    />
  );
}

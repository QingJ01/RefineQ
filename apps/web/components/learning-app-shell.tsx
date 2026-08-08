"use client";

import { usePathname } from "next/navigation";

import { StudyWorkspace } from "@/components/study-workspace";
import { resolveLearningShellPath } from "@/lib/learning-routes";


export function LearningAppShell({ children }: { children: React.ReactNode }) {
  const route = resolveLearningShellPath(usePathname());
  if (route.kind === "home") return <StudyWorkspace />;
  if (route.kind === "workspace") {
    return (
      <StudyWorkspace
        initialWorkspaceId={route.workspaceId}
        initialSection={route.section}
      />
    );
  }
  return children;
}

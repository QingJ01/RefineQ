"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { StudyWorkspace } from "@/components/study-workspace";
import { api, subscribeUnauthorized } from "@/lib/api";
import { clearUserScopedSessionState, isCurrentUserSession } from "@/lib/client-session-state";
import { resolveLearningShellPath } from "@/lib/learning-routes";


export function LearningAppShell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [sessionEpoch, setSessionEpoch] = useState(0);
  const route = resolveLearningShellPath(usePathname());

  useEffect(() => subscribeUnauthorized((token) => {
    api.clearReadCache(token);
    if (!isCurrentUserSession(window.sessionStorage, token)) return;
    clearUserScopedSessionState(window.sessionStorage);
    setSessionEpoch((current) => current + 1);
    router.replace("/");
  }), [router]);

  if (route.kind === "home") return <StudyWorkspace key={sessionEpoch} />;
  if (route.kind === "workspace") {
    return (
      <StudyWorkspace
        key={sessionEpoch}
        initialWorkspaceId={route.workspaceId}
        initialSection={route.section}
      />
    );
  }
  return children;
}

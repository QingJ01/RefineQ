export type WorkspaceRouteResolution<T> =
  | { kind: "home" }
  | { kind: "workspace"; workspace: T }
  | { kind: "unavailable" };


export function resolveRequestedWorkspace<T extends { id: string }>(
  requestedWorkspaceId: string | undefined,
  workspaces: T[],
): WorkspaceRouteResolution<T> {
  if (!requestedWorkspaceId) return { kind: "home" };
  const workspace = workspaces.find((item) => item.id === requestedWorkspaceId);
  return workspace ? { kind: "workspace", workspace } : { kind: "unavailable" };
}

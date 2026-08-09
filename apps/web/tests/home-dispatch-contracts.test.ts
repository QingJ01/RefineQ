import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";


const homeSource = readFileSync(
  fileURLToPath(new URL("../components/learning-home.tsx", import.meta.url)),
  "utf8",
);
const workspaceSource = readFileSync(
  fileURLToPath(new URL("../components/study-workspace.tsx", import.meta.url)),
  "utf8",
);
const apiSource = readFileSync(
  fileURLToPath(new URL("../lib/api.ts", import.meta.url)),
  "utf8",
);
const styles = readFileSync(
  fileURLToPath(new URL("../app/styles.css", import.meta.url)),
  "utf8",
);


describe("home supervisor contracts", () => {
  it("renders one typed card surface for all six server result kinds", () => {
    for (const kind of [
      "direct_answer",
      "open_workspace",
      "workspace_action",
      "propose_workspace",
      "clarify",
      "out_of_scope",
    ]) {
      expect(homeSource).toContain(`latestResult.kind === "${kind}"`);
    }
    expect(homeSource).toContain("setLatestResult(null)");
    expect(homeSource).not.toContain("setMessages(");
  });

  it("keeps results transient and rejects stale or cancelled replies", () => {
    expect(homeSource).toContain("requestRef.current?.controller.abort()");
    expect(homeSource).toContain("requestRef.current?.id !== current.id");
    expect(homeSource).toContain("current.controller.signal.aborted");
    expect(homeSource).toContain("result.request_id !== current.id");
    expect(homeSource).not.toContain("sessionStorage.setItem");
    expect(homeSource).not.toContain("localStorage.setItem");
    expect(homeSource).toContain("normalized.length > 12_000");
    expect(homeSource).toContain('t("homeTooLong")');
    expect(homeSource).toContain('window.location.assign("/admin/integrations/chat")');
    expect(workspaceSource).toContain("authRef.current?.access_token !== token");
  });

  it("trusts only the server auto-navigation field and confirms every write", () => {
    expect(workspaceSource).toContain("!result.workspace_target.auto_navigate");
    expect(workspaceSource).not.toMatch(/match_kind\s*===\s*["']explicit_command/);
    expect(homeSource).toContain("confirmResult()");
    expect(apiSource).toContain('"/home/actions/revise"');
    expect(apiSource).toContain('"/home/actions/confirm"');
    expect(apiSource).toContain('"/home/actions/cancel"');
    expect(apiSource).toContain('"/home/actions/undo"');
    expect(apiSource).toContain('result.workspace_target.route_action === "created"');
    expect(apiSource).toContain('receipt.operation === "create_workspace"');
    expect(homeSource).toContain('caught.code === "home_action_conflict"');
    expect(homeSource).toContain('caught.code === "invalid_home_confirmation"');
    expect(homeSource).toContain("latestRequestTextRef.current || intent");
    expect(homeSource).toContain('t("homeProposalUpdated")');
    expect(workspaceSource).toContain("await api.undoHomeCreation");
    expect(workspaceSource).toContain("authRef.current = null");
  });

  it("keeps mobile actions touchable and respects reduced motion", () => {
    expect(styles).toMatch(/\.home-result-actions button\s*\{[^}]*min-height:\s*44px/s);
    expect(styles).toContain("@media (prefers-reduced-motion: reduce)");
    expect(homeSource).toContain('aria-live="polite"');
    expect(homeSource).toContain("resultHeadingRef.current?.focus()");
  });
});

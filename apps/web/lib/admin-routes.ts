import type { IntegrationKind } from "./types";

export type AdminSection = "overview" | "operations";


export function parseAdminSection(value: string): AdminSection | null {
  return value === "overview" || value === "operations" ? value : null;
}

const integrationKinds = new Set<IntegrationKind>([
  "chat",
  "embedding",
  "ocr",
  "object_storage",
]);

export function parseIntegrationKind(value: string): IntegrationKind | null {
  return integrationKinds.has(value as IntegrationKind) ? value as IntegrationKind : null;
}

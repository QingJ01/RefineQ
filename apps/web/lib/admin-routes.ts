import type { IntegrationKind } from "./types";


const integrationKinds = new Set<IntegrationKind>([
  "chat",
  "embedding",
  "ocr",
  "object_storage",
]);

export function parseIntegrationKind(value: string): IntegrationKind | null {
  return integrationKinds.has(value as IntegrationKind) ? value as IntegrationKind : null;
}

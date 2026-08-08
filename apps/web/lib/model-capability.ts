export async function loadModelCapability(
  load: () => Promise<{ configured: boolean }>,
): Promise<boolean | null> {
  try {
    return (await load()).configured;
  } catch {
    return null;
  }
}

export function resolveModelCapability(
  configuredFromWorkspace: boolean | null | undefined,
  detectedLocally: boolean | null,
): boolean | null {
  if (configuredFromWorkspace === false || detectedLocally === false) return false;
  if (configuredFromWorkspace === true) return true;
  return detectedLocally;
}

export async function refreshModelCapability(
  load: () => Promise<{ configured: boolean }>,
  publish: (configured: boolean | null) => void,
): Promise<boolean | null> {
  const configured = await loadModelCapability(load);
  publish(configured);
  return configured;
}

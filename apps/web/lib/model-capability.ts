export async function loadModelCapability(
  load: () => Promise<{ configured: boolean }>,
): Promise<boolean | null> {
  try {
    return (await load()).configured;
  } catch {
    return null;
  }
}

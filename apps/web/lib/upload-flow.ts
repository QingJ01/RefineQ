export function clearSelectedFiles(input: { value: string } | null): void {
  if (input) input.value = "";
}

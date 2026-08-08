export function clearSelectedFiles(input: { value: string } | null): void {
  if (input) input.value = "";
}

const SUPPORTED_EXTENSIONS = new Set(["pdf", "docx", "txt", "md"]);
const MAX_UPLOAD_BYTES = 20 * 1024 * 1024;

export type UploadValidationError = "unsupported_type" | "file_too_large";

export function validateUploadFile(file: Pick<File, "name" | "size">): UploadValidationError | null {
  const extension = file.name.split(".").pop()?.toLowerCase() ?? "";
  if (!SUPPORTED_EXTENSIONS.has(extension)) return "unsupported_type";
  if (file.size > MAX_UPLOAD_BYTES) return "file_too_large";
  return null;
}

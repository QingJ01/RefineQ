export function clearSelectedFiles(input: { value: string } | null): void {
  if (input) input.value = "";
}

export function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

export async function runSerially<T>(
  items: readonly T[],
  run: (item: T) => void | Promise<void>,
): Promise<void> {
  for (const item of items) await run(item);
}

export interface SerialTaskQueue<T> {
  enqueue: (items: readonly T[]) => void;
  remove: (predicate: (item: T) => boolean) => void;
  close: () => void;
  open: () => void;
  pendingCount: () => number;
}

export function createSerialTaskQueue<T>(
  run: (item: T) => void | Promise<void>,
): SerialTaskQueue<T> {
  let pending: T[] = [];
  let running = false;
  let closed = false;

  async function drain() {
    if (running || closed) return;
    running = true;
    try {
      while (!closed && pending.length > 0) {
        const item = pending.shift();
        if (item !== undefined) {
          try {
            await run(item);
          } catch {
            // Individual upload failures are reflected by the caller and must not stall later files.
          }
        }
      }
    } finally {
      running = false;
      if (!closed && pending.length > 0) void drain();
    }
  }

  return {
    enqueue(items) {
      if (closed || items.length === 0) return;
      pending.push(...items);
      void drain();
    },
    remove(predicate) {
      pending = pending.filter((item) => !predicate(item));
    },
    close() {
      closed = true;
      pending = [];
    },
    open() {
      closed = false;
      void drain();
    },
    pendingCount() {
      return pending.length;
    },
  };
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

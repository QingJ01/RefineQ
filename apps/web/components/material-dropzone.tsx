"use client";

import {
  Download,
  FileStack,
  RotateCcw,
  Search,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import { DragEvent, FormEvent, useRef, useState } from "react";

import type { Translator } from "@/lib/i18n";
import { ConfirmDialog } from "@/components/confirm-dialog";
import type { MaterialRecord, SearchSource } from "@/lib/types";
import {
  clearSelectedFiles,
  type UploadValidationError,
  validateUploadFile,
} from "@/lib/upload-flow";


type UploadState = "queued" | "uploading" | "uploaded" | "failed" | "cancelled";

interface UploadItem {
  id: string;
  file: File;
  status: UploadState;
  error?: UploadValidationError | "upload_failed";
  controller?: AbortController;
}

export function MaterialDropzone({
  t,
  onUpload,
  onSearch,
  onDownload,
  onDelete,
  materials,
}: {
  t: Translator;
  onUpload: (files: File[], signal?: AbortSignal) => Promise<MaterialRecord[]>;
  onSearch?: (query: string) => Promise<SearchSource[]>;
  onDownload?: (material: MaterialRecord) => void | Promise<void>;
  onDelete?: (material: MaterialRecord) => void | Promise<void>;
  materials: MaterialRecord[];
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [queue, setQueue] = useState<UploadItem[]>([]);
  const [dragging, setDragging] = useState(false);
  const [query, setQuery] = useState("");
  const [searching, setSearching] = useState(false);
  const [results, setResults] = useState<SearchSource[]>([]);
  const [deleteTarget, setDeleteTarget] = useState<MaterialRecord | null>(null);
  const [deleting, setDeleting] = useState(false);

  function patchQueue(id: string, patch: Partial<UploadItem>) {
    setQueue((current) => current.map((item) => item.id === id ? { ...item, ...patch } : item));
  }

  function queueLabel(item: UploadItem): string {
    if (item.error === "unsupported_type") return t("uploadUnsupported");
    if (item.error === "file_too_large") return t("uploadTooLarge");
    if (item.status === "queued") return t("uploadQueued");
    if (item.status === "uploading") return t("uploading");
    if (item.status === "uploaded") return t("uploaded");
    if (item.status === "cancelled") return t("uploadCancelled");
    return t("uploadFailed");
  }

  async function uploadFile(item: UploadItem) {
    const controller = new AbortController();
    patchQueue(item.id, { status: "uploading", error: undefined, controller });
    try {
      const uploaded = await onUpload([item.file], controller.signal);
      if (!controller.signal.aborted) {
        patchQueue(item.id, {
          status: uploaded.length > 0 ? "uploaded" : "failed",
          error: uploaded.length > 0 ? undefined : "upload_failed",
          controller: undefined,
        });
      }
    } catch {
      if (!controller.signal.aborted) {
        patchQueue(item.id, { status: "failed", error: "upload_failed", controller: undefined });
      }
    }
  }

  function selected(files: File[]) {
    if (files.length === 0) return;
    const items = files.map((file): UploadItem => {
      const error = validateUploadFile(file);
      return {
        id: crypto.randomUUID(),
        file,
        status: error ? "failed" : "queued",
        error: error ?? undefined,
      };
    });
    setQueue((current) => [...items, ...current]);
    items.filter((item) => !item.error).forEach((item) => void uploadFile(item));
    clearSelectedFiles(inputRef.current);
  }

  function retryUpload(item: UploadItem) {
    if (validateUploadFile(item.file)) return;
    void uploadFile(item);
  }

  function cancelUpload(item: UploadItem) {
    item.controller?.abort();
    patchQueue(item.id, { status: "cancelled", controller: undefined });
  }

  function onDrop(event: DragEvent<HTMLButtonElement>) {
    event.preventDefault();
    setDragging(false);
    selected(Array.from(event.dataTransfer.files));
  }

  async function searchMaterials(event: FormEvent) {
    event.preventDefault();
    if (!onSearch || !query.trim()) {
      setResults([]);
      return;
    }
    setSearching(true);
    try {
      setResults(await onSearch(query.trim()));
    } finally {
      setSearching(false);
    }
  }

  async function confirmDelete() {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await onDelete?.(deleteTarget);
      setDeleteTarget(null);
    } finally {
      setDeleting(false);
    }
  }

  return (
    <section className="content-card materials-card">
      <div className="section-heading"><div><span className="kicker">KNOWLEDGE / LOCAL</span><h2>{t("upload")}</h2></div><FileStack size={24} strokeWidth={1.4} /></div>
      <button
        type="button"
        className={dragging ? "upload-surface dragging" : "upload-surface"}
        onClick={() => inputRef.current?.click()}
        onDragEnter={() => setDragging(true)}
        onDragLeave={() => setDragging(false)}
        onDragOver={(event) => event.preventDefault()}
        onDrop={onDrop}
      >
        <Upload size={28} strokeWidth={1.3} /><strong>{t("chooseFiles")}</strong><span>{t("uploadHint")}</span>
      </button>
      <input ref={inputRef} hidden multiple type="file" accept=".pdf,.docx,.txt,.md,.markdown" onChange={(event) => selected(Array.from(event.target.files ?? []))} />

      {queue.length > 0 && (
        <ul className="upload-queue" aria-label={t("uploadQueue")}>
          {queue.map((item) => (
            <li key={item.id}>
              <div><strong>{item.file.name}</strong><span>{queueLabel(item)}</span></div>
              {item.status === "uploading" && <button type="button" aria-label={t("cancelUpload")} onClick={() => cancelUpload(item)}><X size={14} /></button>}
              {(item.status === "failed" || item.status === "cancelled") && !item.error?.startsWith("file_") && item.error !== "unsupported_type" && (
                <button type="button" aria-label={t("retry")} onClick={() => retryUpload(item)}><RotateCcw size={14} /></button>
              )}
            </li>
          ))}
        </ul>
      )}

      <form className="material-search" onSubmit={searchMaterials}>
        <Search size={16} />
        <input data-testid="material-search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder={t("searchMaterials")} />
        <button type="submit" disabled={searching || !query.trim()}>{searching ? t("loading") : t("search")}</button>
      </form>
      {results.length > 0 && (
        <ol className="material-search-results">
          {results.map((source) => (
            <li key={`${source.material_id}-${source.chunk_index}`}>
              <strong>{source.filename}</strong><span>{source.citation_id} · {Math.round(source.score * 100)}%</span>
              <p>{source.text}</p>
            </li>
          ))}
        </ol>
      )}

      {materials.length === 0 ? <div className="empty-note material-empty">{t("noMaterials")}</div> : (
        <ul className="material-list">
          {materials.map((material) => (
            <li key={material.id}>
              <div><span>{material.filename}</span><em>{material.chunk_count} chunks · {t("uploaded")}</em></div>
              <div className="material-actions">
                <button type="button" data-testid={`material-download-${material.id}`} aria-label={`${t("download")} ${material.filename}`} onClick={() => void onDownload?.(material)}><Download size={15} /></button>
                <button
                  type="button"
                  data-testid={`material-delete-${material.id}`}
                  aria-label={`${t("deleteMaterial")} ${material.filename}`}
                  disabled={deleting && deleteTarget?.id === material.id}
                  onClick={() => setDeleteTarget(material)}
                ><Trash2 size={15} /></button>
              </div>
            </li>
          ))}
        </ul>
      )}
      <ConfirmDialog
        open={deleteTarget !== null}
        title={deleteTarget ? `${t("deleteMaterial")} · ${deleteTarget.filename}` : t("deleteMaterial")}
        description={t("deleteMaterialConfirm")}
        confirmLabel={t("deleteMaterial")}
        cancelLabel={t("cancel")}
        tone="danger"
        busy={deleting}
        onConfirm={confirmDelete}
        onCancel={() => setDeleteTarget(null)}
      />
    </section>
  );
}

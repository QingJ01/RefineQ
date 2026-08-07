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

import { ConfirmDialog } from "@/components/confirm-dialog";
import { SourceDrawer } from "@/components/source-drawer";
import type { Translator } from "@/lib/i18n";
import type { Locale, MaterialRecord, SearchSource } from "@/lib/types";
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

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function MaterialDropzone({
  t,
  locale = "zh",
  onUpload,
  onSearch,
  onDownload,
  onDelete,
  materials,
}: {
  t: Translator;
  locale?: Locale;
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
  const [searchedQuery, setSearchedQuery] = useState("");
  const [selectedSources, setSelectedSources] = useState<SearchSource[]>([]);
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
      setSearchedQuery("");
      return;
    }
    setSearching(true);
    try {
      const normalized = query.trim();
      setResults(await onSearch(normalized));
      setSearchedQuery(normalized);
    } finally {
      setSearching(false);
    }
  }

  function clearSearch() {
    setQuery("");
    setResults([]);
    setSearchedQuery("");
  }

  function clearFinishedUploads() {
    setQueue((current) => current.filter((item) => (
      item.status === "queued" || item.status === "uploading"
    )));
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
        <div className="upload-queue-block">
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
          {queue.some((item) => item.status !== "queued" && item.status !== "uploading") && (
            <button type="button" className="clear-upload-queue" data-testid="clear-upload-queue" onClick={clearFinishedUploads}>
              {t("clearFinishedUploads")}
            </button>
          )}
        </div>
      )}

      <form className="material-search" onSubmit={searchMaterials}>
        <Search size={16} />
        <input data-testid="material-search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder={t("searchMaterials")} />
        <button type="submit" disabled={searching || !query.trim()}>{searching ? t("loading") : t("search")}</button>
      </form>
      {searchedQuery && (
        <div className="material-search-summary">
          <span>{results.length > 0 ? `${results.length} · ${searchedQuery}` : searchedQuery}</span>
          <button type="button" data-testid="clear-material-search" onClick={clearSearch}><X size={13} /> {t("clearSearch")}</button>
        </div>
      )}
      {searchedQuery && results.length === 0 && !searching && (
        <div className="empty-note material-search-empty" data-testid="material-search-empty">{t("searchNoResults")}</div>
      )}
      {results.length > 0 && (
        <ol className="material-search-results">
          {results.map((source) => (
            <li key={`${source.material_id}-${source.chunk_index}`}>
              <button type="button" onClick={() => setSelectedSources([source])}>
                <span><strong>{source.filename}</strong><em>{Math.round(source.score * 100)}%</em></span>
                <p>{source.text}</p>
              </button>
            </li>
          ))}
        </ol>
      )}

      {materials.length === 0 ? <div className="empty-note material-empty">{t("noMaterials")}</div> : (
        <ul className="material-list">
          {materials.map((material) => (
            <li key={material.id}>
              <div className="material-record-copy">
                <span>{material.filename}</span>
                <em>{material.chunk_count} {t("chunks")} · {t("uploaded")}</em>
                <details data-testid={`material-metadata-${material.id}`} className="material-metadata">
                  <summary>{t("materialDetails")}</summary>
                  <dl>
                    <div><dt>{t("fileSize")}</dt><dd>{formatBytes(material.size)}</dd></div>
                    <div><dt>{t("fileType")}</dt><dd>{material.content_type}</dd></div>
                    <div><dt>{t("indexedAt")}</dt><dd>{new Intl.DateTimeFormat(locale === "zh" ? "zh-CN" : "en-US", { dateStyle: "medium", timeStyle: "short" }).format(new Date(material.indexed_at))}</dd></div>
                  </dl>
                </details>
              </div>
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
      {selectedSources.length > 0 && (
        <SourceDrawer
          title={t("sources")}
          sources={selectedSources}
          t={t}
          onClose={() => setSelectedSources([])}
        />
      )}
    </section>
  );
}

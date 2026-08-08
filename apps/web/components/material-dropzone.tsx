"use client";

import {
  Check,
  Download,
  FileStack,
  ListPlus,
  Pencil,
  RotateCcw,
  Search,
  Tags,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import { DragEvent, FormEvent, useEffect, useMemo, useRef, useState } from "react";

import { ConfirmDialog } from "@/components/confirm-dialog";
import { SourceDrawer } from "@/components/source-drawer";
import type { Translator } from "@/lib/i18n";
import type {
  Locale,
  MaterialRecord,
  MaterialUpdateInput,
  SearchSource,
  TopicSuggestion,
} from "@/lib/types";
import {
  clearSelectedFiles,
  createSerialTaskQueue,
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

interface QueuedUpload {
  id: string;
  run: () => Promise<void>;
}

const organizationCopy = {
  zh: {
    library: "资料库",
    allStatuses: "全部状态",
    allTags: "全部标签",
    newest: "最近添加",
    oldest: "最早添加",
    title: "按标题",
    largest: "按大小",
    selectAll: "选择当前列表",
    selected: (count: number) => `已选择 ${count} 项`,
    edit: "编辑资料信息",
    editTitle: "资料标题",
    editTags: "标签（用逗号分隔）",
    save: "保存",
    cancel: "取消",
    bulkDelete: "批量删除",
    bulkTitle: (count: number) => `删除 ${count} 份资料？`,
    bulkDescription: "将同时删除原文件与检索索引；失败时会自动回滚。",
    noMatch: "当前筛选条件下没有资料。",
    originalFile: "原文件",
    status: "处理状态",
  },
  en: {
    library: "Material library",
    allStatuses: "All statuses",
    allTags: "All tags",
    newest: "Newest first",
    oldest: "Oldest first",
    title: "Title A–Z",
    largest: "Largest first",
    selectAll: "Select visible material",
    selected: (count: number) => `${count} selected`,
    edit: "Edit material details",
    editTitle: "Material title",
    editTags: "Tags (comma separated)",
    save: "Save",
    cancel: "Cancel",
    bulkDelete: "Delete selected",
    bulkTitle: (count: number) => `Delete ${count} materials?`,
    bulkDescription: "Original files and search indexes are removed together and restored if deletion fails.",
    noMatch: "No material matches these filters.",
    originalFile: "Original file",
    status: "Processing status",
  },
} as const;

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
  onUpdate,
  onBulkDelete,
  topicSuggestions = [],
  acceptingTopicSuggestionId = null,
  onAcceptTopicSuggestion,
  materials,
}: {
  t: Translator;
  locale?: Locale;
  onUpload: (files: File[], signal?: AbortSignal) => Promise<MaterialRecord[]>;
  onSearch?: (query: string) => Promise<SearchSource[]>;
  onDownload?: (material: MaterialRecord) => void | Promise<void>;
  onDelete?: (material: MaterialRecord) => void | Promise<void>;
  onUpdate?: (material: MaterialRecord, input: MaterialUpdateInput) => void | Promise<void>;
  onBulkDelete?: (materials: MaterialRecord[]) => void | Promise<void>;
  topicSuggestions?: TopicSuggestion[];
  acceptingTopicSuggestionId?: string | null;
  onAcceptTopicSuggestion?: (suggestion: TopicSuggestion) => void | Promise<void>;
  materials: MaterialRecord[];
}) {
  const copy = organizationCopy[locale];
  const inputRef = useRef<HTMLInputElement>(null);
  const activeControllersRef = useRef(new Set<AbortController>());
  const [uploadQueue] = useState(() => createSerialTaskQueue<QueuedUpload>((item) => item.run()));
  const [queue, setQueue] = useState<UploadItem[]>([]);
  const [dragging, setDragging] = useState(false);
  const [query, setQuery] = useState("");
  const [searching, setSearching] = useState(false);
  const [results, setResults] = useState<SearchSource[]>([]);
  const [searchedQuery, setSearchedQuery] = useState("");
  const [selectedSources, setSelectedSources] = useState<SearchSource[]>([]);
  const [deleteTarget, setDeleteTarget] = useState<MaterialRecord | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [statusFilter, setStatusFilter] = useState("all");
  const [tagFilter, setTagFilter] = useState("all");
  const [sortOrder, setSortOrder] = useState("newest");
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [editTarget, setEditTarget] = useState<MaterialRecord | null>(null);
  const [editTitle, setEditTitle] = useState("");
  const [editTags, setEditTags] = useState("");
  const [savingMetadata, setSavingMetadata] = useState(false);
  const [bulkDeleteOpen, setBulkDeleteOpen] = useState(false);
  const tags = useMemo(
    () => Array.from(new Set(materials.flatMap((material) => material.tags ?? [])))
      .sort((left, right) => left.localeCompare(right)),
    [materials],
  );
  const statuses = useMemo(
    () => Array.from(new Set(materials.map((material) => material.status))).sort(),
    [materials],
  );
  const visibleMaterials = useMemo(() => {
    const filtered = materials.filter((material) => (
      (statusFilter === "all" || material.status === statusFilter)
      && (tagFilter === "all" || (material.tags ?? []).includes(tagFilter))
    ));
    return filtered.toSorted((left, right) => {
      if (sortOrder === "oldest") {
        return new Date(left.indexed_at).getTime() - new Date(right.indexed_at).getTime();
      }
      if (sortOrder === "title") {
        return (left.title ?? left.filename).localeCompare(right.title ?? right.filename);
      }
      if (sortOrder === "size_desc") return right.size - left.size;
      return new Date(right.indexed_at).getTime() - new Date(left.indexed_at).getTime();
    });
  }, [materials, sortOrder, statusFilter, tagFilter]);
  const selectedMaterials = materials.filter((material) => selectedIds.has(material.id));
  const allVisibleSelected = visibleMaterials.length > 0
    && visibleMaterials.every((material) => selectedIds.has(material.id));

  useEffect(() => {
    uploadQueue.open();
    const beforeUnload = (event: BeforeUnloadEvent) => {
      if (activeControllersRef.current.size === 0 && uploadQueue.pendingCount() === 0) return;
      event.preventDefault();
    };
    window.addEventListener("beforeunload", beforeUnload);
    const controllers = activeControllersRef.current;
    return () => {
      window.removeEventListener("beforeunload", beforeUnload);
      uploadQueue.close();
      controllers.forEach((controller) => controller.abort());
      controllers.clear();
    };
  }, [uploadQueue]);

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
    activeControllersRef.current.add(controller);
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
    } finally {
      activeControllersRef.current.delete(controller);
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
    uploadQueue.enqueue(items
      .filter((item) => !item.error)
      .map((item) => ({ id: item.id, run: () => uploadFile(item) })));
    clearSelectedFiles(inputRef.current);
  }

  function retryUpload(item: UploadItem) {
    if (validateUploadFile(item.file)) return;
    uploadQueue.enqueue([{ id: item.id, run: () => uploadFile(item) }]);
  }

  function cancelUpload(item: UploadItem) {
    uploadQueue.remove((queued) => queued.id === item.id);
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
      setSelectedIds((current) => {
        const next = new Set(current);
        next.delete(deleteTarget.id);
        return next;
      });
      setDeleteTarget(null);
    } finally {
      setDeleting(false);
    }
  }

  function toggleSelection(materialId: string) {
    setSelectedIds((current) => {
      const next = new Set(current);
      if (next.has(materialId)) next.delete(materialId);
      else next.add(materialId);
      return next;
    });
  }

  function toggleVisibleSelection() {
    setSelectedIds((current) => {
      const next = new Set(current);
      if (allVisibleSelected) visibleMaterials.forEach((material) => next.delete(material.id));
      else visibleMaterials.forEach((material) => next.add(material.id));
      return next;
    });
  }

  function beginEdit(material: MaterialRecord) {
    setEditTarget(material);
    setEditTitle(material.title ?? material.filename);
    setEditTags((material.tags ?? []).join(", "));
  }

  async function saveMetadata(event: FormEvent) {
    event.preventDefault();
    if (!editTarget || !editTitle.trim()) return;
    const normalizedTags = Array.from(new Set(
      editTags.split(",").map((tag) => tag.trim()).filter(Boolean),
    ));
    setSavingMetadata(true);
    try {
      await onUpdate?.(editTarget, { title: editTitle.trim(), tags: normalizedTags });
      setEditTarget(null);
    } finally {
      setSavingMetadata(false);
    }
  }

  async function confirmBulkDelete() {
    if (selectedMaterials.length === 0) return;
    setDeleting(true);
    try {
      await onBulkDelete?.(selectedMaterials);
      setSelectedIds(new Set());
      setBulkDeleteOpen(false);
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
      <input ref={inputRef} hidden multiple type="file" accept=".pdf,.docx,.txt,.md" onChange={(event) => selected(Array.from(event.target.files ?? []))} />

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

      {topicSuggestions.length > 0 && (
        <aside className="material-topic-suggestions" data-testid="material-topic-suggestions">
          <div>
            <span><ListPlus size={17} /></span>
            <div>
              <strong>{locale === "zh" ? "从资料信息发现的主题" : "Topics found in material details"}</strong>
              <p>{locale === "zh"
                ? "这些候选只来自标题和标签。确认后才会加入学习路径。"
                : "These candidates use titles and tags only. Nothing changes until you confirm."}</p>
            </div>
          </div>
          <ul>
            {topicSuggestions.map((suggestion) => (
              <li key={suggestion.id}>
                <span>{suggestion.name}</span>
                <button
                  type="button"
                  data-testid={`accept-topic-${suggestion.id}`}
                  disabled={acceptingTopicSuggestionId !== null}
                  onClick={() => void onAcceptTopicSuggestion?.(suggestion)}
                >
                  {acceptingTopicSuggestionId === suggestion.id
                    ? (locale === "zh" ? "正在添加…" : "Adding…")
                    : (locale === "zh" ? "添加主题" : "Add topic")}
                </button>
              </li>
            ))}
          </ul>
        </aside>
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

      {materials.length > 0 && (
        <div className="material-organizer" aria-label={copy.library}>
          <div className="material-organizer-title">
            <span><Tags size={16} /></span>
            <strong>{copy.library}</strong>
            <small>{materials.length}</small>
          </div>
          <div className="material-filter-grid">
            <select
              data-testid="material-filter-status"
              aria-label={copy.status}
              value={statusFilter}
              onChange={(event) => setStatusFilter(event.target.value)}
            >
              <option value="all">{copy.allStatuses}</option>
              {statuses.map((item) => <option value={item} key={item}>{item}</option>)}
            </select>
            <select
              data-testid="material-filter-tag"
              aria-label={copy.allTags}
              value={tagFilter}
              onChange={(event) => setTagFilter(event.target.value)}
            >
              <option value="all">{copy.allTags}</option>
              {tags.map((tag) => <option value={tag} key={tag}>{tag}</option>)}
            </select>
            <select
              data-testid="material-sort"
              aria-label={copy.newest}
              value={sortOrder}
              onChange={(event) => setSortOrder(event.target.value)}
            >
              <option value="newest">{copy.newest}</option>
              <option value="oldest">{copy.oldest}</option>
              <option value="title">{copy.title}</option>
              <option value="size_desc">{copy.largest}</option>
            </select>
          </div>
          <div className="material-selection-bar">
            <label>
              <input
                data-testid="material-select-all"
                type="checkbox"
                checked={allVisibleSelected}
                onChange={toggleVisibleSelection}
              />
              <span>{copy.selectAll}</span>
            </label>
            <span>{copy.selected(selectedMaterials.length)}</span>
            <button
              type="button"
              data-testid="material-bulk-delete"
              disabled={selectedMaterials.length === 0 || deleting}
              onClick={() => setBulkDeleteOpen(true)}
            ><Trash2 size={14} /> {copy.bulkDelete}</button>
          </div>
        </div>
      )}

      {materials.length === 0 ? <div className="empty-note material-empty">{t("noMaterials")}</div> : visibleMaterials.length === 0 ? (
        <div className="empty-note material-empty">{copy.noMatch}</div>
      ) : (
        <ul className="material-list material-library-list">
          {visibleMaterials.map((material) => (
            <li key={material.id} className={selectedIds.has(material.id) ? "selected" : undefined}>
              <label className="material-select-control">
                <input
                  type="checkbox"
                  data-testid={`material-select-${material.id}`}
                  aria-label={`${copy.selectAll}: ${material.title ?? material.filename}`}
                  checked={selectedIds.has(material.id)}
                  onChange={() => toggleSelection(material.id)}
                />
              </label>
              <div className="material-record-copy">
                <div className="material-title-row">
                  <span>{material.title ?? material.filename}</span>
                  <small data-state={material.status}><Check size={11} /> {material.status}</small>
                </div>
                {(material.tags ?? []).length > 0 && (
                  <div className="material-tags">
                    {(material.tags ?? []).map((tag) => <span key={tag}>{tag}</span>)}
                  </div>
                )}
                <em>{material.chunk_count} {t("chunks")} · {t("uploaded")}</em>
                {editTarget?.id === material.id && (
                  <form className="material-edit-form" onSubmit={saveMetadata}>
                    <label>
                      <span>{copy.editTitle}</span>
                      <input value={editTitle} maxLength={500} onChange={(event) => setEditTitle(event.target.value)} />
                    </label>
                    <label>
                      <span>{copy.editTags}</span>
                      <input value={editTags} onChange={(event) => setEditTags(event.target.value)} />
                    </label>
                    <div>
                      <button type="button" onClick={() => setEditTarget(null)}>{copy.cancel}</button>
                      <button type="submit" disabled={!editTitle.trim() || savingMetadata}>{copy.save}</button>
                    </div>
                  </form>
                )}
                <details data-testid={`material-metadata-${material.id}`} className="material-metadata">
                  <summary>{t("materialDetails")}</summary>
                  <dl>
                    <div><dt>{copy.originalFile}</dt><dd>{material.filename}</dd></div>
                    <div><dt>{t("fileSize")}</dt><dd>{formatBytes(material.size)}</dd></div>
                    <div><dt>{t("fileType")}</dt><dd>{material.content_type}</dd></div>
                    <div><dt>{t("indexedAt")}</dt><dd>{new Intl.DateTimeFormat(locale === "zh" ? "zh-CN" : "en-US", { dateStyle: "medium", timeStyle: "short" }).format(new Date(material.indexed_at))}</dd></div>
                  </dl>
                </details>
              </div>
              <div className="material-actions">
                <button type="button" data-testid={`material-edit-${material.id}`} aria-label={`${copy.edit} ${material.title ?? material.filename}`} onClick={() => beginEdit(material)}><Pencil size={15} /></button>
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
      <ConfirmDialog
        open={bulkDeleteOpen}
        title={copy.bulkTitle(selectedMaterials.length)}
        description={copy.bulkDescription}
        confirmLabel={copy.bulkDelete}
        cancelLabel={copy.cancel}
        tone="danger"
        busy={deleting}
        onConfirm={confirmBulkDelete}
        onCancel={() => setBulkDeleteOpen(false)}
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

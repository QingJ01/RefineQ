"use client";

import {
  Download,
  FileStack,
  RotateCcw,
  Search,
  Sparkles,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import { DragEvent, FormEvent, useRef, useState } from "react";

import { ConfirmDialog } from "@/components/confirm-dialog";
import { SourceDrawer } from "@/components/source-drawer";
import type { Translator } from "@/lib/i18n";
import type { Locale, MaterialAnalysis, MaterialRecord, SearchSource, StudyPlan, TargetedPlanInput } from "@/lib/types";
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
  onAnalyze,
  onGeneratePlan,
  onOpenCalendar,
  materials,
}: {
  t: Translator;
  locale?: Locale;
  onUpload: (files: File[], signal?: AbortSignal) => Promise<MaterialRecord[]>;
  onSearch?: (query: string) => Promise<SearchSource[]>;
  onDownload?: (material: MaterialRecord) => void | Promise<void>;
  onDelete?: (material: MaterialRecord) => void | Promise<void>;
  onAnalyze?: (material: MaterialRecord) => Promise<MaterialAnalysis>;
  onGeneratePlan?: (input: TargetedPlanInput) => Promise<StudyPlan>;
  onOpenCalendar?: () => void;
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
  const [analyses, setAnalyses] = useState<Record<string, MaterialAnalysis>>({});
  const [analyzingIds, setAnalyzingIds] = useState<string[]>([]);
  const [analysisErrors, setAnalysisErrors] = useState<string[]>([]);
  const [planningId, setPlanningId] = useState<string | null>(null);
  const [focusText, setFocusText] = useState("");
  const [examDate, setExamDate] = useState("");
  const [dailyMinutes, setDailyMinutes] = useState(45);
  const [preferredTime, setPreferredTime] = useState("19:00");
  const [studyWeekdays, setStudyWeekdays] = useState([0, 1, 2, 3, 4, 5, 6]);
  const [routineNotes, setRoutineNotes] = useState("");
  const [generatingPlan, setGeneratingPlan] = useState(false);
  const [planStatus, setPlanStatus] = useState<"idle" | "success" | "error">("idle");
  const [planError, setPlanError] = useState("");

  const analysisCopy = locale === "zh" ? {
    analyze: "分析资料",
    analyzing: "正在识别章节和知识点…",
    failed: "分析失败，请检查模型连接后重试。",
    ai: "AI 分析",
    fallback: "本地降级分析",
    confidence: "置信度",
    topics: "知识点",
    sections: "章节",
    citations: "资料片段",
    types: {
      textbook: "教材",
      lecture_notes: "讲义",
      exam: "试卷",
      problem_set: "习题集",
      mixed: "混合资料",
      unknown: "未识别",
    },
  } : {
    analyze: "Analyze material",
    analyzing: "Identifying sections and topics…",
    failed: "Analysis failed. Check the model connection and retry.",
    ai: "AI analysis",
    fallback: "Local fallback",
    confidence: "Confidence",
    topics: "Topics",
    sections: "Sections",
    citations: "Source chunks",
    types: {
      textbook: "Textbook",
      lecture_notes: "Lecture notes",
      exam: "Exam",
      problem_set: "Problem set",
      mixed: "Mixed material",
      unknown: "Unknown",
    },
  };

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

  async function analyzeMaterial(material: MaterialRecord) {
    if (!onAnalyze || analyzingIds.includes(material.id)) return;
    setAnalyzingIds((current) => [...current, material.id]);
    setAnalysisErrors((current) => current.filter((id) => id !== material.id));
    try {
      const analysis = await onAnalyze(material);
      setAnalyses((current) => ({ ...current, [material.id]: analysis }));
    } catch {
      setAnalysisErrors((current) => [...current, material.id]);
    } finally {
      setAnalyzingIds((current) => current.filter((id) => id !== material.id));
    }
  }

  function beginPlanning(analysis: MaterialAnalysis) {
    setPlanningId(analysis.material_id);
    setFocusText(analysis.topics.slice(0, 8).join("、"));
    setPlanStatus("idle");
    setPlanError("");
  }

  async function generatePlan(analysis: MaterialAnalysis) {
    if (!onGeneratePlan || !examDate) return;
    const topics = focusText.split(/[、,，\n]/).map((item) => item.trim()).filter(Boolean);
    if (topics.length === 0) return;
    setGeneratingPlan(true);
    setPlanStatus("idle");
    setPlanError("");
    try {
      await onGeneratePlan({
        material_id: analysis.material_id,
        focus_topics: topics,
        exam_at: new Date(`${examDate}T23:59:00`).toISOString(),
        daily_minutes: dailyMinutes,
        study_weekdays: studyWeekdays,
        preferred_hour: Number(preferredTime.split(":")[0]),
        timezone_offset_minutes: -new Date().getTimezoneOffset(),
        routine_notes: routineNotes,
      });
      setPlanStatus("success");
      await new Promise((resolve) => window.setTimeout(resolve, 900));
      onOpenCalendar?.();
    } catch (error) {
      setPlanStatus("error");
      setPlanError(error instanceof Error ? error.message : (locale === "zh" ? "计划生成失败，请重试。" : "Plan generation failed. Please retry."));
    } finally {
      setGeneratingPlan(false);
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
                {analyzingIds.includes(material.id) && (
                  <span className="material-analysis-status">{analysisCopy.analyzing}</span>
                )}
                {analysisErrors.includes(material.id) && (
                  <span className="material-analysis-error">{analysisCopy.failed}</span>
                )}
                {analyses[material.id] && (
                  <div className="material-analysis" data-testid={`material-analysis-${material.id}`}>
                    <div className="material-analysis-heading">
                      <strong>{analysisCopy.types[analyses[material.id].material_type]}</strong>
                      <span>{analyses[material.id].mode === "ai" ? analysisCopy.ai : analysisCopy.fallback}</span>
                      <span>{analysisCopy.confidence} {Math.round(analyses[material.id].confidence * 100)}%</span>
                    </div>
                    <p>{analyses[material.id].summary}</p>
                    {analyses[material.id].topics.length > 0 && (
                      <div className="material-analysis-group">
                        <b>{analysisCopy.topics}</b>
                        <div>{analyses[material.id].topics.map((topic) => <span key={topic}>{topic}</span>)}</div>
                      </div>
                    )}
                    {analyses[material.id].sections.length > 0 && (
                      <details className="material-analysis-sections">
                        <summary>{analysisCopy.sections} · {analyses[material.id].sections.length}</summary>
                        <ol>
                          {analyses[material.id].sections.map((section) => (
                            <li key={`${section.title}-${section.citation_ids.join("-")}`}>
                              <strong>{section.title}</strong>
                              {section.topics.length > 0 && <span>{section.topics.join(" · ")}</span>}
                              {section.citation_ids.length > 0 && <code>{analysisCopy.citations}: {section.citation_ids.join(", ")}</code>}
                            </li>
                          ))}
                        </ol>
                      </details>
                    )}
                    {planningId !== material.id ? (
                      <button type="button" className="targeted-plan-button" onClick={() => beginPlanning(analyses[material.id])}>
                        {locale === "zh" ? "生成针对性学习计划" : "Create targeted study plan"}
                      </button>
                    ) : (
                      <div className="targeted-plan-form">
                        <label>{locale === "zh" ? "学习重点" : "Priority topics"}<textarea value={focusText} onChange={(event) => setFocusText(event.target.value)} /></label>
                        <label>{locale === "zh" ? "考试日期" : "Exam date"}<input type="date" value={examDate} onChange={(event) => setExamDate(event.target.value)} /></label>
                        <label>{locale === "zh" ? "每日分钟" : "Daily minutes"}<input type="number" min={10} max={480} value={dailyMinutes} onChange={(event) => setDailyMinutes(Number(event.target.value))} /></label>
                        <label>{locale === "zh" ? "习惯学习时间" : "Preferred study time"}<input type="time" step={3600} value={preferredTime} onChange={(event) => setPreferredTime(event.target.value)} /></label>
                        <fieldset className="targeted-plan-weekdays">
                          <legend>{locale === "zh" ? "可学习日期" : "Available weekdays"}</legend>
                          {(locale === "zh" ? ["一", "二", "三", "四", "五", "六", "日"] : ["M", "T", "W", "T", "F", "S", "S"]).map((label, day) => (
                            <label key={day}><input type="checkbox" checked={studyWeekdays.includes(day)} onChange={() => setStudyWeekdays((current) => current.includes(day) ? current.filter((item) => item !== day) : [...current, day].sort())} />{label}</label>
                          ))}
                        </fieldset>
                        <label className="wide">{locale === "zh" ? "作息与不可用时间" : "Routine and unavailable time"}<textarea value={routineNotes} onChange={(event) => setRoutineNotes(event.target.value)} placeholder={locale === "zh" ? "例如：工作日晚上学习，周三不可安排" : "e.g. evenings; unavailable Wednesday"} /></label>
                        {planStatus === "error" && <p className="targeted-plan-error" role="alert">{locale === "zh" ? `生成失败：${planError}` : `Generation failed: ${planError}`}</p>}
                        <button type="button" className={planStatus === "success" ? "is-success" : undefined} disabled={generatingPlan || !examDate || !focusText.trim() || studyWeekdays.length === 0} onClick={() => void generatePlan(analyses[material.id])}>{generatingPlan ? (locale === "zh" ? "正在生成…" : "Generating…") : planStatus === "success" ? (locale === "zh" ? "✓ 生成成功，正在打开日历" : "✓ Generated — opening calendar") : (locale === "zh" ? "确认并打开日历" : "Confirm and open calendar")}</button>
                      </div>
                    )}
                  </div>
                )}
              </div>
              <div className="material-actions">
                <button
                  type="button"
                  className="material-analyze-button"
                  data-testid={`material-analyze-${material.id}`}
                  aria-label={`${analysisCopy.analyze} ${material.filename}`}
                  disabled={!onAnalyze || analyzingIds.includes(material.id)}
                  onClick={() => void analyzeMaterial(material)}
                >
                  <Sparkles size={15} />
                  <span>{analyzingIds.includes(material.id) ? analysisCopy.analyzing : analysisCopy.analyze}</span>
                </button>
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

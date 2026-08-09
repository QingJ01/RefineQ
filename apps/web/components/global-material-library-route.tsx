"use client";

import { BookOpen, FileText, LoaderCircle, Trash2, Upload } from "lucide-react";
import { useRouter } from "next/navigation";
import { ChangeEvent, useEffect, useState } from "react";

import { AppSidebar } from "@/components/app-sidebar";
import { BrandMark } from "@/components/brand";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { api, ApiError } from "@/lib/api";
import { clearUserScopedSessionState } from "@/lib/client-session-state";
import { localizeApiError } from "@/lib/error-messages";
import { learningPath } from "@/lib/learning-routes";
import { loadLearningSession, saveLearningSession } from "@/lib/session";
import type { LearningWorkspace, Locale, MaterialRecord } from "@/lib/types";

export function GlobalMaterialLibraryRoute() {
  const router = useRouter();
  const [token, setToken] = useState("");
  const [locale, setLocale] = useState<Locale>("zh");
  const [isAdmin, setIsAdmin] = useState(false);
  const [workspaces, setWorkspaces] = useState<LearningWorkspace[]>([]);
  const [materials, setMaterials] = useState<MaterialRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [attachingId, setAttachingId] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<MaterialRecord | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const session = loadLearningSession(window.sessionStorage);
    if (!session) { router.replace("/"); return; }
    const sessionLocale = session.locale ?? "zh";
    Promise.resolve().then(() => {
      setToken(session.token);
      setLocale(sessionLocale);
    });
    Promise.all([
      api.getProfile(session.token),
      api.listWorkspaces(session.token, false),
      api.listLibraryMaterials(session.token),
    ]).then(([profile, spaces, records]) => {
      setIsAdmin(profile.role === "admin");
      setWorkspaces(spaces);
      setMaterials(records);
    }).catch((caught: unknown) => {
      if (caught instanceof ApiError && (caught.status === 401 || caught.status === 403)) {
        clearUserScopedSessionState(window.sessionStorage);
        router.replace("/");
        return;
      }
      setError(localizeApiError(caught, session.locale ?? "zh"));
    }).finally(() => setLoading(false));
  }, [router]);

  async function upload(event: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.target.files ?? []);
    event.target.value = "";
    if (!token || files.length === 0) return;
    setUploading(true);
    setError("");
    try {
      const added = await api.uploadLibraryMaterials(token, files);
      setMaterials((current) => [...added, ...current]);
    } catch (caught) {
      setError(localizeApiError(caught, locale));
    } finally {
      setUploading(false);
    }
  }

  async function attach(material: MaterialRecord, workspaceId: string) {
    if (!workspaceId || !token || !material.project_id) return;
    setAttachingId(material.id);
    setError("");
    try {
      await api.attachLibraryMaterial(token, material.project_id, material.id, workspaceId);
      router.push(learningPath(workspaceId, "materials"));
    } catch (caught) {
      setError(localizeApiError(caught, locale));
      setAttachingId(null);
    }
  }

  async function deleteMaterial() {
    if (!deleteTarget || !token) return;
    setDeleting(true);
    setError("");
    try {
      await api.deleteLibraryMaterial(token, deleteTarget.id);
      setMaterials((current) => current.filter((item) => item.id !== deleteTarget.id));
      setDeleteTarget(null);
    } catch (caught) {
      setError(localizeApiError(caught, locale));
    } finally {
      setDeleting(false);
    }
  }

  function logout() {
    api.clearReadCache(token);
    clearUserScopedSessionState(window.sessionStorage);
    router.replace("/");
  }

  function toggleLocale() {
    const next = locale === "zh" ? "en" : "zh";
    const session = loadLearningSession(window.sessionStorage);
    if (session) saveLearningSession(window.sessionStorage, { ...session, locale: next });
    setLocale(next);
  }

  if (loading) return <main id="main-content" className="loading-stage"><BrandMark size={44} /><LoaderCircle className="spin" size={22} /></main>;
  if (!token) return <main id="main-content" className="loading-stage"><BrandMark size={44} /><p>{error || (locale === "zh" ? "正在返回登录页。" : "Returning to sign in.")}</p></main>;

  return (
    <main id="main-content" className="global-library-shell">
      <div className="global-library-sidebar"><AppSidebar locale={locale} active="library" workspaces={workspaces} isAdmin={isAdmin} onToggleLocale={toggleLocale} onLogout={logout} /></div>
      <section className="global-library-page">
        <header><span className="kicker">{locale === "zh" ? "所有学习空间" : "ALL LEARNING SPACES"}</span><h1>{locale === "zh" ? "总资料库" : "Material library"}</h1><p>{locale === "zh" ? "先保存资料，需要学习时再加入对应的学习空间。" : "Save materials now and add them to a learning space when you need them."}</p></header>
        {error && <div className="error-banner" role="alert"><strong>{locale === "zh" ? "操作没有完成" : "Action failed"}</strong><span>{error}</span></div>}
        <label className="global-library-upload"><Upload size={24} /><strong>{uploading ? (locale === "zh" ? "正在上传…" : "Uploading…") : (locale === "zh" ? "上传到总资料库" : "Upload to library")}</strong><span>PDF、DOCX、TXT、Markdown</span><input hidden multiple disabled={uploading} type="file" accept=".pdf,.docx,.txt,.md" onChange={(event) => void upload(event)} /></label>
        <div className="global-library-summary"><strong>{locale === "zh" ? `全部资料 ${materials.length}` : `${materials.length} materials`}</strong><span>{locale === "zh" ? `共 ${Math.round(materials.reduce((sum, item) => sum + item.size, 0) / 1024)} KB` : `${Math.round(materials.reduce((sum, item) => sum + item.size, 0) / 1024)} KB total`}</span></div>
        {materials.length === 0 ? <div className="empty-note">{locale === "zh" ? "还没有资料，可以先上传一份。" : "No materials yet. Upload one to get started."}</div> : <ul className="global-library-list">{materials.map((material) => {
          const linkedSpaces = workspaces.filter((space) => material.workspace_ids?.includes(space.id));
          return <li key={material.id}><FileText size={20} /><div><strong>{material.title ?? material.filename}</strong><span>{linkedSpaces.length > 0 ? (locale === "zh" ? `已加入：${linkedSpaces.map((space) => space.title).join("、")}` : `In: ${linkedSpaces.map((space) => space.title).join(", ")}`) : (locale === "zh" ? "尚未加入学习空间" : "Not added to a learning space")} · {Math.max(1, Math.round(material.size / 1024))} KB</span></div>{workspaces.length > 0 && <label><BookOpen size={15} /><select aria-label={locale === "zh" ? "加入学习空间" : "Add to learning space"} disabled={attachingId === material.id} defaultValue="" onChange={(event) => void attach(material, event.target.value)}><option value="" disabled>{attachingId === material.id ? (locale === "zh" ? "正在加入…" : "Adding…") : (locale === "zh" ? "加入学习空间" : "Add to space")}</option>{workspaces.map((space) => <option key={space.id} value={space.id} disabled={material.workspace_ids?.includes(space.id)}>{space.title}{material.workspace_ids?.includes(space.id) ? (locale === "zh" ? "（已加入）" : " (added)") : ""}</option>)}</select></label>}<button type="button" aria-label={locale === "zh" ? `彻底删除 ${material.filename}` : `Delete ${material.filename} everywhere`} onClick={() => setDeleteTarget(material)}><Trash2 size={16} /></button></li>;
        })}</ul>}
      </section>
      <ConfirmDialog
        open={deleteTarget !== null}
        title={locale === "zh" ? "从总资料库彻底删除？" : "Delete from the global library?"}
        description={locale === "zh" ? "原文件、检索索引以及所有学习空间中的关联都会被删除。" : "The file, search index, and links from every learning space will be removed."}
        confirmLabel={locale === "zh" ? "彻底删除" : "Delete everywhere"}
        cancelLabel={locale === "zh" ? "取消" : "Cancel"}
        tone="danger"
        busy={deleting}
        onConfirm={deleteMaterial}
        onCancel={() => setDeleteTarget(null)}
      />
    </main>
  );
}

"use client";

import { FileStack, Upload } from "lucide-react";
import { useRef, useState } from "react";

import type { Translator } from "@/lib/i18n";
import type { MaterialRecord } from "@/lib/types";
import { clearSelectedFiles } from "@/lib/upload-flow";


export function MaterialDropzone({
  t,
  onUpload,
  materials,
}: {
  t: Translator;
  onUpload: (files: File[]) => Promise<MaterialRecord[]>;
  materials: MaterialRecord[];
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);

  async function selected(files: FileList | null) {
    if (!files?.length) return;
    setBusy(true);
    try {
      await onUpload(Array.from(files));
    } finally {
      clearSelectedFiles(inputRef.current);
      setBusy(false);
    }
  }

  return (
    <section className="content-card materials-card">
      <div className="section-heading"><div><span className="kicker">KNOWLEDGE / LOCAL</span><h2>{t("upload")}</h2></div><FileStack size={24} strokeWidth={1.4} /></div>
      <button className="upload-surface" onClick={() => inputRef.current?.click()} disabled={busy}>
        <Upload size={28} strokeWidth={1.3} /><strong>{busy ? t("loading") : t("chooseFiles")}</strong><span>{t("uploadHint")}</span>
      </button>
      <input ref={inputRef} hidden multiple type="file" accept=".pdf,.docx,.txt,.md" onChange={(event) => void selected(event.target.files)} />
      <ul className="material-list">
        {materials.map((material) => <li key={material.id}><span>{material.filename}</span><em>{material.chunk_count} chunks · {t("uploaded")}</em></li>)}
      </ul>
    </section>
  );
}

"use client";

import { FileText, X } from "lucide-react";
import { useEffect, useRef } from "react";

import type { SearchSource } from "@/lib/types";


export function SourceDrawer({
  title,
  sources,
  onClose,
}: {
  title: string;
  sources: SearchSource[];
  onClose: () => void;
}) {
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    closeRef.current?.focus();
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", closeOnEscape);
    return () => document.removeEventListener("keydown", closeOnEscape);
  }, [onClose]);

  return (
    <div className="source-drawer-backdrop" onMouseDown={(event) => {
      if (event.currentTarget === event.target) onClose();
    }}>
      <aside className="source-drawer" role="dialog" aria-modal="true" aria-labelledby="source-drawer-title">
        <header>
          <div><span className="kicker">GROUNDED EVIDENCE</span><h2 id="source-drawer-title">{title}</h2></div>
          <button ref={closeRef} type="button" aria-label="Close" onClick={onClose}><X size={18} /></button>
        </header>
        <ol>
          {sources.map((source) => (
            <li key={`${source.material_id}-${source.chunk_index}`}>
              <div><FileText size={16} /><strong>{source.filename}</strong><span>{source.citation_id}</span></div>
              <p>{source.text}</p>
              <small>{Math.round(source.score * 100)}% match</small>
            </li>
          ))}
        </ol>
      </aside>
    </div>
  );
}

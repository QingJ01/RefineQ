"use client";

import { FileText, X } from "lucide-react";
import { useEffect, useRef } from "react";

import type { Translator } from "@/lib/i18n";
import type { SearchSource } from "@/lib/types";


export function SourceDrawer({
  title,
  sources,
  t,
  onClose,
}: {
  title: string;
  sources: SearchSource[];
  t: Translator;
  onClose: () => void;
}) {
  const drawerRef = useRef<HTMLElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const previousFocus = document.activeElement as HTMLElement | null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    closeRef.current?.focus();
    const closeOnKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
        return;
      }
      if (event.key !== "Tab") return;
      const focusable = Array.from(
        drawerRef.current?.querySelectorAll<HTMLElement>(
          'button:not(:disabled), [href], input:not(:disabled), select:not(:disabled), textarea:not(:disabled)',
        ) ?? [],
      );
      if (focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable.at(-1)!;
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", closeOnKey);
    return () => {
      document.body.style.overflow = previousOverflow;
      document.removeEventListener("keydown", closeOnKey);
      previousFocus?.focus();
    };
  }, [onClose]);

  return (
    <div className="source-drawer-backdrop" onMouseDown={(event) => {
      if (event.currentTarget === event.target) onClose();
    }}>
      <aside ref={drawerRef} className="source-drawer" role="dialog" aria-modal="true" aria-labelledby="source-drawer-title">
        <header>
          <div><span className="kicker">{t("groundedEvidence")}</span><h2 id="source-drawer-title">{title}</h2></div>
          <button ref={closeRef} type="button" aria-label={t("close")} onClick={onClose}><X size={18} /></button>
        </header>
        {sources.length === 0 ? (
          <div className="source-drawer-empty"><FileText size={26} /><p>{t("noSourceExcerpts")}</p></div>
        ) : (
          <ol>
            {sources.map((source) => (
              <li key={`${source.material_id}-${source.chunk_index}`}>
                <div><FileText size={16} /><strong>{source.filename}</strong></div>
                <p>{source.text}</p>
                <small>{Math.round(source.score * 100)}% {t("sourceMatch")}</small>
              </li>
            ))}
          </ol>
        )}
      </aside>
    </div>
  );
}

"use client";

import { X } from "lucide-react";
import { useEffect, useRef } from "react";


export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel,
  cancelLabel,
  tone = "default",
  busy = false,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  title: string;
  description: string;
  confirmLabel: string;
  cancelLabel: string;
  tone?: "default" | "danger";
  busy?: boolean;
  onConfirm: () => void | Promise<void>;
  onCancel: () => void;
}) {
  const panelRef = useRef<HTMLDivElement>(null);
  const cancelRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    const previousFocus = document.activeElement as HTMLElement | null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    cancelRef.current?.focus();
    return () => {
      document.body.style.overflow = previousOverflow;
      previousFocus?.focus();
    };
  }, [open]);

  if (!open) return null;

  function handleKeyDown(event: React.KeyboardEvent<HTMLDivElement>) {
    if (event.key === "Escape" && !busy) {
      event.preventDefault();
      onCancel();
      return;
    }
    if (event.key !== "Tab") return;
    const focusable = Array.from(
      panelRef.current?.querySelectorAll<HTMLElement>(
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
  }

  return (
    <div
      className="confirm-dialog-backdrop"
      data-testid="confirm-dialog"
      onMouseDown={(event) => {
        if (event.currentTarget === event.target && !busy) onCancel();
      }}
    >
      <div
        ref={panelRef}
        className={`confirm-dialog confirm-dialog-${tone}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirm-dialog-title"
        aria-describedby="confirm-dialog-description"
        aria-busy={busy}
        onKeyDown={handleKeyDown}
      >
        <button
          type="button"
          className="confirm-dialog-close"
          aria-label={cancelLabel}
          disabled={busy}
          onClick={onCancel}
        ><X size={17} /></button>
        <div className="confirm-dialog-mark" aria-hidden="true">?</div>
        <h2 id="confirm-dialog-title">{title}</h2>
        <p id="confirm-dialog-description">{description}</p>
        <div className="confirm-dialog-actions">
          <button
            ref={cancelRef}
            type="button"
            data-testid="confirm-dialog-cancel"
            className="secondary-action"
            disabled={busy}
            onClick={onCancel}
          >{cancelLabel}</button>
          <button
            type="button"
            data-testid="confirm-dialog-confirm"
            className={tone === "danger" ? "danger-action" : "primary-action"}
            disabled={busy}
            onClick={() => void onConfirm()}
          >{confirmLabel}</button>
        </div>
      </div>
    </div>
  );
}

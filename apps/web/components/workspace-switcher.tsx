"use client";

import { Check, ChevronsUpDown, House, Layers3 } from "lucide-react";
import { KeyboardEvent, useEffect, useMemo, useRef, useState } from "react";

import type { LearningWorkspace, Locale } from "@/lib/types";


const copy = {
  zh: {
    current: "当前空间",
    switchSpace: "切换学习空间",
    progress: "掌握度",
    allSpaces: "查看所有学习空间",
    menu: "学习空间列表",
  },
  en: {
    current: "Current space",
    switchSpace: "Switch learning space",
    progress: "Mastery",
    allSpaces: "View all learning spaces",
    menu: "Learning spaces",
  },
} as const;

export function WorkspaceSwitcher({
  locale,
  current,
  workspaces,
  currentProgress,
  onSelect,
  onAllSpaces,
}: {
  locale: Locale;
  current: LearningWorkspace;
  workspaces: LearningWorkspace[];
  currentProgress: number;
  onSelect: (workspace: LearningWorkspace) => void | Promise<void>;
  onAllSpaces: () => void;
}) {
  const text = copy[locale];
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const itemRefs = useRef<Array<HTMLButtonElement | null>>([]);
  const options = useMemo(() => {
    const available = workspaces.filter((workspace) => !workspace.archived);
    const others = available.filter((workspace) => workspace.id !== current.id);
    return [current, ...others];
  }, [current, workspaces]);

  useEffect(() => {
    if (!open) return;
    itemRefs.current[activeIndex]?.focus();
  }, [activeIndex, open]);

  useEffect(() => {
    if (!open) return;
    function closeOnOutsideClick(event: MouseEvent) {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", closeOnOutsideClick);
    return () => document.removeEventListener("mousedown", closeOnOutsideClick);
  }, [open]);

  function closeAndRestoreFocus() {
    setOpen(false);
    triggerRef.current?.focus();
  }

  function moveFocus(event: KeyboardEvent<HTMLDivElement>) {
    const items = itemRefs.current.filter((item): item is HTMLButtonElement => item !== null);
    if (event.key === "Escape") {
      event.preventDefault();
      closeAndRestoreFocus();
      return;
    }
    if (event.key === "Tab") {
      setOpen(false);
      return;
    }
    if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    let nextIndex: number;
    if (event.key === "Home") nextIndex = 0;
    else if (event.key === "End") nextIndex = items.length - 1;
    else {
      const direction = event.key === "ArrowDown" ? 1 : -1;
      nextIndex = (activeIndex + direction + items.length) % items.length;
    }
    setActiveIndex(nextIndex);
    items[nextIndex]?.focus();
  }

  function select(workspace: LearningWorkspace) {
    setOpen(false);
    void onSelect(workspace);
  }

  return (
    <div ref={rootRef} className="workspace-switcher-shell">
      <button
        ref={triggerRef}
        type="button"
        className="workspace-switcher"
        data-testid="workspace-switcher"
        aria-label={`${text.switchSpace}: ${current.title}`}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls="workspace-switcher-menu"
        onClick={() => {
          setActiveIndex(0);
          setOpen((value) => !value);
        }}
        onKeyDown={(event) => {
          if (event.key === "ArrowDown" || event.key === "ArrowUp") {
            event.preventDefault();
            setActiveIndex(event.key === "ArrowUp" ? options.length : 0);
            setOpen(true);
          }
        }}
      >
        <span className="workspace-switcher-heading">
          <span className="kicker">{text.current}</span>
          <ChevronsUpDown size={15} />
        </span>
        <strong>{current.title}</strong>
        <span className="workspace-switcher-topic">{current.topics[0] ?? current.goal}</span>
        <span className="workspace-switcher-progress">
          <span>{text.progress}</span>
          <strong>{currentProgress}%</strong>
        </span>
        <i aria-hidden="true"><b style={{ width: `${currentProgress}%` }} /></i>
      </button>
      {open && (
        <div
          id="workspace-switcher-menu"
          className="workspace-switcher-menu"
          data-testid="workspace-switcher-menu"
          role="menu"
          aria-label={text.menu}
          onKeyDown={moveFocus}
        >
          {options.map((workspace, index) => (
            <button
              key={workspace.id}
              ref={(node) => { itemRefs.current[index] = node; }}
              type="button"
              role="menuitem"
              tabIndex={activeIndex === index ? 0 : -1}
              data-testid={`workspace-switcher-option-${workspace.id}`}
              className={workspace.id === current.id ? "active" : ""}
              aria-current={workspace.id === current.id ? "true" : undefined}
              aria-label={`${workspace.title}: ${workspace.goal}`}
              onFocus={() => setActiveIndex(index)}
              onClick={() => select(workspace)}
            >
              <Layers3 size={16} />
              <span><strong>{workspace.title}</strong><small>{workspace.topics[0] ?? workspace.goal}</small></span>
              {workspace.id === current.id && <Check size={15} />}
            </button>
          ))}
          <button
            ref={(node) => { itemRefs.current[options.length] = node; }}
            type="button"
            role="menuitem"
            tabIndex={activeIndex === options.length ? 0 : -1}
            className="workspace-switcher-all"
            data-testid="workspace-switcher-all"
            onFocus={() => setActiveIndex(options.length)}
            onClick={() => {
              setOpen(false);
              onAllSpaces();
            }}
          >
            <House size={16} /> {text.allSpaces}
          </button>
        </div>
      )}
    </div>
  );
}

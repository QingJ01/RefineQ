"use client";

import { ArrowRight, BookOpenCheck, LockKeyhole, Sparkles } from "lucide-react";
import { FormEvent, useState } from "react";

import { api } from "@/lib/api";
import type { Translator } from "@/lib/i18n";
import type { AuthResponse } from "@/lib/types";


export function AuthPanel({
  t,
  onAuthenticated,
}: {
  t: Translator;
  onAuthenticated: (response: AuthResponse) => void;
}) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const response = mode === "register"
        ? await api.register(email, password, displayName)
        : await api.login(email, password);
      onAuthenticated(response);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : t("error"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="auth-stage">
      <section className="auth-welcome">
        <div className="auth-brand">
          <span className="brand-mark" aria-hidden="true">R</span>
          <strong>RefineQ</strong>
        </div>
        <div className="auth-copy">
          <span className="kicker">PERSONAL LEARNING AGENT</span>
          <h1>{t("authPrompt")}</h1>
          <p>{t("authSubline")}</p>
          <div className="auth-principles">
            <span><Sparkles size={16} /> 自动识别学习方向</span>
            <span><BookOpenCheck size={16} /> 用练习证据持续进步</span>
          </div>
        </div>
      </section>
      <section className="auth-form-card">
        <header className="auth-form-heading">
          <span className="mobile-brand-mark" aria-hidden="true">R</span>
          <div>
            <h2>{mode === "login" ? t("login") : t("register")}</h2>
            <p>{t("authSubline")}</p>
          </div>
        </header>
        <div className="auth-tabs">
          <button className={mode === "login" ? "active" : ""} onClick={() => setMode("login")}>
            {t("login")}
          </button>
          <button data-testid="register-tab" className={mode === "register" ? "active" : ""} onClick={() => setMode("register")}>
            {t("register")}
          </button>
        </div>
        <form onSubmit={submit}>
          {mode === "register" && (
            <label>{t("displayName")}<input data-testid="display-name" value={displayName} onChange={(e) => setDisplayName(e.target.value)} required /></label>
          )}
          <label>{t("email")}<input data-testid="email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required /></label>
          <label>{t("password")}<input data-testid="password" type="password" minLength={12} value={password} onChange={(e) => setPassword(e.target.value)} required /></label>
          {error && <p className="form-error">{error}</p>}
          <button data-testid="auth-submit" className="primary-action wide" disabled={busy}>
            <LockKeyhole size={17} /> {busy ? t("loading") : t(mode)} <ArrowRight size={18} />
          </button>
        </form>
      </section>
    </main>
  );
}

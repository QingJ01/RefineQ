"use client";

import { ArrowUpRight, LockKeyhole } from "lucide-react";
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
      <div className="auth-orbit" aria-hidden="true"><span>RQ</span></div>
      <section className="auth-copy">
        <span className="kicker">PERSONAL LEARNING AGENT / 01</span>
        <h1>{t("authPrompt")}</h1>
        <p>{t("authSubline")}</p>
        <div className="auth-principles">
          <span>01 / GOAL</span><span>02 / PRACTICE</span><span>03 / EVIDENCE</span>
        </div>
      </section>
      <section className="auth-form-card">
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
            <LockKeyhole size={17} /> {busy ? t("loading") : t(mode)} <ArrowUpRight size={18} />
          </button>
        </form>
      </section>
    </main>
  );
}

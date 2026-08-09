"use client";

import { ArrowLeft, ArrowRight, Eye, EyeOff, LockKeyhole } from "lucide-react";
import Image from "next/image";
import { FormEvent, useEffect, useState } from "react";

import { BrandMark, BrandName } from "@/components/brand";
import { api } from "@/lib/api";
import { localizeApiError } from "@/lib/error-messages";
import type { Translator } from "@/lib/i18n";
import type { AuthResponse, Locale } from "@/lib/types";


type AuthMode = "login" | "register" | "forgot" | "reset";

export function AuthPanel({
  t,
  locale = "zh",
  onAuthenticated,
}: {
  t: Translator;
  locale?: Locale;
  onAuthenticated: (response: AuthResponse) => void;
}) {
  const [mode, setMode] = useState<AuthMode>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [resetToken, setResetToken] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [passwordResetAvailable, setPasswordResetAvailable] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const passwordBytes = new TextEncoder().encode(password).length;
  const passwordRules = {
    minimum: passwordBytes >= 12,
    maximum: passwordBytes <= 72,
    matches: mode !== "reset" || (password.length > 0 && password === confirmPassword),
  };

  useEffect(() => {
    let active = true;
    void api.getAuthCapabilities()
      .then((capabilities) => {
        if (active) setPasswordResetAvailable(capabilities.password_reset_available);
      })
      .catch(() => {
        if (active) setPasswordResetAvailable(false);
      });

    function applyResetTokenFromHash() {
      if (!active || !window.location.hash.startsWith("#reset-token=")) return;
      const encodedToken = window.location.hash.slice("#reset-token=".length);
      try {
        const token = decodeURIComponent(encodedToken);
        if (token.length >= 20 && token.length <= 500) {
          setResetToken(token);
          setMode("reset");
        }
      } catch {
        // Ignore malformed external input and leave the login form usable.
      } finally {
        window.history.replaceState(
          window.history.state,
          "",
          `${window.location.pathname}${window.location.search}`,
        );
      }
    }
    const initialHashCheck = window.setTimeout(applyResetTokenFromHash, 0);
    window.addEventListener("hashchange", applyResetTokenFromHash);

    return () => {
      active = false;
      window.clearTimeout(initialHashCheck);
      window.removeEventListener("hashchange", applyResetTokenFromHash);
    };
  }, []);

  function changeMode(next: AuthMode) {
    setMode(next);
    setError("");
    setNotice("");
    setPassword("");
    setConfirmPassword("");
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setNotice("");
    try {
      if (mode === "forgot") {
        const accepted = await api.requestPasswordReset(email);
        if (accepted.reset_token) {
          setResetToken(accepted.reset_token);
          setMode("reset");
        }
        setNotice(t("resetRequested"));
        return;
      }
      if (mode === "reset") {
        if (!passwordRules.minimum || !passwordRules.maximum || !passwordRules.matches) {
          setError(t("passwordRulesError"));
          return;
        }
        await api.completePasswordReset(resetToken, password);
        changeMode("login");
        setNotice(t("passwordResetComplete"));
        return;
      }
      const response = mode === "register"
        ? await api.register(email, password, displayName)
        : await api.login(email, password);
      onAuthenticated(response);
    } catch (caught) {
      setError(localizeApiError(caught, locale));
    } finally {
      setBusy(false);
    }
  }

  const heading = mode === "login"
    ? t("login")
    : mode === "register"
      ? t("register")
      : mode === "forgot"
        ? t("forgotPassword")
        : t("resetPassword");
  const needsStrongPassword = mode === "register" || mode === "reset";

  return (
    <main id="main-content" className="auth-stage">
      <section className="auth-welcome">
        <div className="auth-brand"><BrandMark className="brand-mark" size={36} /><BrandName /></div>
        <div className="auth-copy"><span className="kicker">PERSONAL LEARNING AGENT</span><h1>{t("authPrompt")}</h1><p>{t("authSubline")}</p></div>
        <Image className="auth-illustration" src="/assets/refineq-learning-illustration.png" alt="" aria-hidden="true" width={1254} height={1254} priority />
      </section>
      <section className="auth-form-side">
        <div className="auth-form-card">
          <header className="auth-form-heading">
            <BrandMark className="mobile-brand-mark" size={36} />
            <div><h2>{heading}</h2><p>{mode === "forgot" || mode === "reset" ? t("resetPasswordHint") : (locale === "zh" ? "使用你的账号继续" : "Continue with your account")}</p></div>
          </header>
          {(mode === "login" || mode === "register") && (
            <div className="auth-tabs">
              <button type="button" className={mode === "login" ? "active" : ""} onClick={() => changeMode("login")}>{t("login")}</button>
              <button type="button" data-testid="register-tab" className={mode === "register" ? "active" : ""} onClick={() => changeMode("register")}>{t("register")}</button>
            </div>
          )}
          <form onSubmit={submit}>
            {mode === "register" && (
              <label>{t("displayName")}<input data-testid="display-name" autoComplete="name" value={displayName} onChange={(event) => setDisplayName(event.target.value)} required /></label>
            )}
            {mode !== "reset" && (
              <label>{t("email")}<input data-testid="email" type="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} required /></label>
            )}
            {mode === "reset" && (
              <label>{t("resetToken")}<input data-testid="reset-token" autoComplete="one-time-code" value={resetToken} onChange={(event) => setResetToken(event.target.value)} required /></label>
            )}
            {(mode === "login" || mode === "register" || mode === "reset") && (
              <label>
                {mode === "reset" ? t("newPassword") : t("password")}
                <span className="password-input">
                  <input
                    data-testid="password"
                    type={showPassword ? "text" : "password"}
                    autoComplete={mode === "login" ? "current-password" : "new-password"}
                    minLength={needsStrongPassword ? 12 : 1}
                    maxLength={72}
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                    required
                  />
                  <button type="button" data-testid="toggle-password" aria-label={t(showPassword ? "hidePassword" : "showPassword")} onClick={() => setShowPassword((current) => !current)}>
                    {showPassword ? <EyeOff size={17} /> : <Eye size={17} />}
                  </button>
                </span>
              </label>
            )}
            {mode === "reset" && (
              <label>{t("confirmPassword")}<input type={showPassword ? "text" : "password"} autoComplete="new-password" value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} required /></label>
            )}
            {needsStrongPassword && (
              <ul className="password-rules" aria-label={t("passwordRules")}>
                <li data-valid={passwordRules.minimum}>{t("passwordMinimum")}</li>
                <li data-valid={passwordRules.maximum}>{t("passwordMaximum")}</li>
                {mode === "reset" && <li data-valid={passwordRules.matches}>{t("passwordsMatch")}</li>}
              </ul>
            )}
            {error && <p className="form-error" role="alert">{error}</p>}
            {notice && <p className="form-notice" role="status">{notice}</p>}
            <button data-testid="auth-submit" className="primary-action wide" disabled={busy || (needsStrongPassword && (!passwordRules.minimum || !passwordRules.maximum || !passwordRules.matches))}>
              <LockKeyhole size={17} /> {busy ? t("loading") : heading} <ArrowRight size={18} />
            </button>
            {mode === "login" && passwordResetAvailable && <button type="button" data-testid="forgot-password" className="auth-text-button" onClick={() => changeMode("forgot")}>{t("forgotPassword")}</button>}
            {(mode === "forgot" || mode === "reset") && <button type="button" className="auth-text-button" onClick={() => changeMode("login")}><ArrowLeft size={14} /> {t("backToLogin")}</button>}
          </form>
        </div>
      </section>
    </main>
  );
}

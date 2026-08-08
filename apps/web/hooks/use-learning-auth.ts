"use client";

import { useCallback, useMemo, useState } from "react";

import { localizeApiError } from "@/lib/error-messages";
import { translator } from "@/lib/i18n";
import {
  clearLearningSession,
  saveLearningLocale,
} from "@/lib/session";
import type { AuthResponse, Locale } from "@/lib/types";


export function useLearningAuth() {
  const [locale, setLocale] = useState<Locale>("zh");
  const [restoring, setRestoring] = useState(true);
  const [auth, setAuth] = useState<AuthResponse | null>(null);
  const [modelConfigured, setModelConfigured] = useState<boolean | null>(null);
  const [error, setError] = useState("");
  const t = useMemo(() => translator(locale), [locale]);

  const reportError = useCallback((caught: unknown) => {
    setError(localizeApiError(caught, locale));
  }, [locale]);

  const resetAuthentication = useCallback(() => {
    clearLearningSession(window.sessionStorage);
    setAuth(null);
    setModelConfigured(null);
    setError("");
  }, []);

  const toggleLocale = useCallback((workspaceId?: string) => {
    const next: Locale = locale === "zh" ? "en" : "zh";
    setLocale(next);
    if (auth) {
      saveLearningLocale(window.sessionStorage, auth.access_token, next, workspaceId);
    }
    document.documentElement.lang = next === "zh" ? "zh-CN" : "en";
    return next;
  }, [auth, locale]);

  return {
    auth,
    error,
    locale,
    modelConfigured,
    reportError,
    resetAuthentication,
    restoring,
    setAuth,
    setError,
    setLocale,
    setModelConfigured,
    setRestoring,
    t,
    toggleLocale,
  };
}

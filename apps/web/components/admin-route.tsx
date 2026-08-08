"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { AdminConsole } from "@/components/admin-console";
import { BrandMark } from "@/components/brand";
import { api, ApiError } from "@/lib/api";
import { clearLearningSession, loadLearningSession, saveLearningSession } from "@/lib/session";
import type { IntegrationKind, Locale } from "@/lib/types";


export function AdminRoute({ activeKind }: { activeKind?: IntegrationKind }) {
  const router = useRouter();
  const [token, setToken] = useState<string | null>(null);
  const [locale, setLocale] = useState<Locale>("zh");
  const [verificationError, setVerificationError] = useState("");
  const [verificationNonce, setVerificationNonce] = useState(0);

  useEffect(() => {
    let active = true;
    const session = loadLearningSession(window.sessionStorage);
    if (!session) {
      router.replace("/");
      return () => { active = false; };
    }
    api.getProfile(session.token)
      .then((user) => {
        if (!active) return;
        if (user.role !== "admin") {
          router.replace("/");
          return;
        }
        if (session.locale) {
          setLocale(session.locale);
          document.documentElement.lang = session.locale === "zh" ? "zh-CN" : "en";
        }
        setVerificationError("");
        setToken(session.token);
      })
      .catch((caught: unknown) => {
        if (!active) return;
        if (caught instanceof ApiError && (caught.status === 401 || caught.status === 403)) {
          clearLearningSession(window.sessionStorage);
          router.replace("/");
        } else {
          setVerificationError(caught instanceof Error ? caught.message : "Verification failed");
        }
      });
    return () => { active = false; };
  }, [router, verificationNonce]);

  function logout() {
    clearLearningSession(window.sessionStorage);
    router.replace("/");
  }

  if (!token) {
    return (
      <main id="main-content" className="loading-stage">
        <BrandMark size={44} />
        <span>{verificationError || (locale === "zh" ? "正在验证管理员身份…" : "Verifying administrator…")}</span>
        {verificationError && (
          <button className="secondary-action" onClick={() => {
            setVerificationError("");
            setVerificationNonce((current) => current + 1);
          }}>{locale === "zh" ? "重试" : "Retry"}</button>
        )}
      </main>
    );
  }

  return (
    <AdminConsole
      token={token}
      locale={locale}
      activeKind={activeKind}
      onLogout={logout}
      onToggleLocale={() => setLocale((current) => {
        const next = current === "zh" ? "en" : "zh";
        const session = loadLearningSession(window.sessionStorage);
        if (session) saveLearningSession(window.sessionStorage, { ...session, locale: next });
        document.documentElement.lang = next === "zh" ? "zh-CN" : "en";
        return next;
      })}
    />
  );
}

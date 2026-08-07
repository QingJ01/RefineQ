"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { AdminConsole } from "@/components/admin-console";
import { BrandMark } from "@/components/brand";
import { api } from "@/lib/api";
import { clearLearningSession, loadLearningSession } from "@/lib/session";
import type { IntegrationKind, Locale } from "@/lib/types";


export function AdminRoute({ activeKind }: { activeKind?: IntegrationKind }) {
  const router = useRouter();
  const [token, setToken] = useState<string | null>(null);
  const [locale, setLocale] = useState<Locale>("zh");

  useEffect(() => {
    let active = true;
    const session = loadLearningSession(window.localStorage);
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
        setToken(session.token);
      })
      .catch(() => {
        clearLearningSession(window.localStorage);
        router.replace("/");
      });
    return () => { active = false; };
  }, [router]);

  function logout() {
    clearLearningSession(window.localStorage);
    router.replace("/");
  }

  if (!token) {
    return (
      <main className="loading-stage">
        <BrandMark size={44} />
        <span>{locale === "zh" ? "正在验证管理员身份…" : "Verifying administrator…"}</span>
      </main>
    );
  }

  return (
    <AdminConsole
      token={token}
      locale={locale}
      activeKind={activeKind}
      onLogout={logout}
      onToggleLocale={() => setLocale((current) => current === "zh" ? "en" : "zh")}
    />
  );
}

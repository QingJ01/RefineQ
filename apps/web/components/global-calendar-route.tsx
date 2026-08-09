"use client";

import { LoaderCircle } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { AppSidebar } from "@/components/app-sidebar";
import { BrandMark } from "@/components/brand";
import { GlobalCalendar } from "@/components/global-calendar";
import { api, ApiError } from "@/lib/api";
import { calendarDateKey, calendarGridRange } from "@/lib/global-calendar";
import { localizeApiError } from "@/lib/error-messages";
import { clearUserScopedSessionState } from "@/lib/client-session-state";
import { loadLearningSession, saveLearningSession } from "@/lib/session";
import type { CalendarTask, LearningWorkspace, Locale } from "@/lib/types";


export function GlobalCalendarRoute() {
  const router = useRouter();
  const now = new Date();
  const [token, setToken] = useState("");
  const [locale, setLocale] = useState<Locale>("zh");
  const [isAdmin, setIsAdmin] = useState(false);
  const [workspaces, setWorkspaces] = useState<LearningWorkspace[]>([]);
  const [tasks, setTasks] = useState<CalendarTask[]>([]);
  const [month, setMonth] = useState(new Date(now.getFullYear(), now.getMonth(), 1));
  const [selectedDate, setSelectedDate] = useState(calendarDateKey(now));
  const [includeArchived, setIncludeArchived] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [reload, setReload] = useState(0);

  useEffect(() => {
    let active = true;
    const session = loadLearningSession(window.sessionStorage);
    if (!session) {
      router.replace("/");
      return () => { active = false; };
    }
    const nextLocale = session.locale ?? "zh";
    document.documentElement.lang = nextLocale === "zh" ? "zh-CN" : "en";
    void Promise.resolve().then(() => {
      if (active) setLocale(nextLocale);
      return api.getProfile(session.token);
    }).then((profile) => {
      if (!active) return;
      setIsAdmin(profile.role === "admin");
      setToken(session.token);
    }).catch((caught: unknown) => {
      if (!active) return;
      if (caught instanceof ApiError && (caught.status === 401 || caught.status === 403)) {
        api.clearReadCache(session.token);
        clearUserScopedSessionState(window.sessionStorage);
        router.replace("/");
      } else {
        setLoading(false);
        setError(localizeApiError(caught, nextLocale));
      }
    });
    return () => { active = false; };
  }, [router]);

  useEffect(() => {
    if (!token) return;
    let active = true;
    const range = calendarGridRange(month);
    Promise.all([
      api.getCalendar(token, range.startsAt.toISOString(), range.endsAt.toISOString(), includeArchived),
      api.listWorkspaces(token, includeArchived),
    ]).then(([calendar, nextWorkspaces]) => {
      if (!active) return;
      setTasks(calendar.tasks);
      setWorkspaces(nextWorkspaces);
      setLoading(false);
    }).catch((caught: unknown) => {
      if (!active) return;
      if (caught instanceof ApiError && (caught.status === 401 || caught.status === 403)) {
        api.clearReadCache(token);
        clearUserScopedSessionState(window.sessionStorage);
        router.replace("/");
        return;
      }
      setLoading(false);
      const savedLocale = loadLearningSession(window.sessionStorage)?.locale ?? "zh";
      setError(localizeApiError(caught, savedLocale));
    });
    return () => { active = false; };
  }, [includeArchived, month, reload, router, token]);

  function logout() {
    api.clearReadCache(token);
    clearUserScopedSessionState(window.sessionStorage);
    router.replace("/");
  }

  function toggleLocale() {
    const next = locale === "zh" ? "en" : "zh";
    const session = loadLearningSession(window.sessionStorage);
    if (session) saveLearningSession(window.sessionStorage, { ...session, locale: next });
    document.documentElement.lang = next === "zh" ? "zh-CN" : "en";
    setLocale(next);
  }

  function changeMonth(next: Date) {
    setLoading(true);
    setError("");
    setMonth(next);
  }

  function changeArchived(next: boolean) {
    setLoading(true);
    setError("");
    setIncludeArchived(next);
  }

  function retry() {
    setLoading(true);
    setError("");
    setReload((current) => current + 1);
  }

  if (!token) {
    return (
      <main id="main-content" className="loading-stage">
        <BrandMark size={44} />
        {error ? (
          <div role="alert"><p>{error}</p><button type="button" onClick={() => window.location.reload()}>{locale === "zh" ? "重试" : "Retry"}</button></div>
        ) : <LoaderCircle className="spin" size={22} />}
      </main>
    );
  }

  return (
    <main id="main-content" className="global-calendar-shell">
      <div className="global-calendar-sidebar">
        <AppSidebar
          locale={locale}
          active="calendar"
          workspaces={workspaces}
          isAdmin={isAdmin}
          onToggleLocale={toggleLocale}
          onLogout={logout}
        />
      </div>
      <GlobalCalendar
        locale={locale}
        month={month}
        selectedDate={selectedDate}
        tasks={tasks}
        workspaces={workspaces}
        includeArchived={includeArchived}
        loading={loading}
        error={error}
        onMonthChange={changeMonth}
        onSelectedDateChange={setSelectedDate}
        onIncludeArchivedChange={changeArchived}
        onRetry={retry}
      />
    </main>
  );
}

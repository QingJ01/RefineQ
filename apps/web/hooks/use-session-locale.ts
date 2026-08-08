"use client";

import { useEffect, useState } from "react";

import { loadLearningSession } from "@/lib/session";
import type { Locale } from "@/lib/types";


export function useSessionLocale(): Locale {
  const [locale, setLocale] = useState<Locale>("zh");

  useEffect(() => {
    let active = true;
    void Promise.resolve().then(() => {
      const saved = loadLearningSession(window.sessionStorage);
      if (active && saved?.locale) setLocale(saved.locale);
    });
    return () => { active = false; };
  }, []);

  return locale;
}

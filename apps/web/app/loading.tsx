"use client";

import { BrandMark, BrandName } from "../components/brand";
import { useSessionLocale } from "../hooks/use-session-locale";
import { routeLoadingText } from "../lib/route-loading";
import { usePathname } from "next/navigation";


export default function Loading() {
  const locale = useSessionLocale();
  const pathname = usePathname();
  const text = routeLoadingText(pathname, locale);
  return (
    <main
      id="main-content"
      className="route-state-stage"
      data-testid="route-loading"
      aria-busy="true"
      aria-live="polite"
    >
      <section className="route-state-card route-state-loading" aria-label={text.aria}>
        <div className="route-state-brand">
          <BrandMark size={42} />
          <BrandName />
        </div>
        <span className="kicker">{text.kicker}</span>
        <h1>{text.title}</h1>
        <p>{text.body}</p>
        <div className="route-state-skeleton" aria-hidden="true">
          <i />
          <i />
          <i />
        </div>
      </section>
    </main>
  );
}

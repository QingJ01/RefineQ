"use client";

import { useSessionLocale } from "../hooks/use-session-locale";


export default function GlobalError({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  const locale = useSessionLocale();
  return (
    <html lang={locale === "zh" ? "zh-CN" : "en"}>
      <body>
        <main id="main-content" className="route-state-stage">
          <section className="route-state-card" role="alert">
            <span className="kicker">REFINEQ</span>
            <h1>{locale === "zh" ? "应用暂时无法继续" : "RefineQ cannot continue right now"}</h1>
            <p>{locale === "zh" ? "你的学习数据不会因此被删除，请重新加载。" : "Your learning data has not been deleted. Reload the application."}</p>
            <button type="button" className="primary-action" onClick={() => reset()}>{locale === "zh" ? "重新加载" : "Reload"}</button>
          </section>
        </main>
      </body>
    </html>
  );
}

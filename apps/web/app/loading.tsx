"use client";

import { BrandMark, BrandName } from "../components/brand";
import { useSessionLocale } from "../hooks/use-session-locale";


export default function Loading() {
  const locale = useSessionLocale();
  const text = locale === "zh"
    ? { aria: "正在准备页面", kicker: "正在准备", title: "正在加载 RefineQ", body: "正在读取当前页面需要的信息。" }
    : { aria: "Preparing page", kicker: "Preparing", title: "Loading RefineQ", body: "Loading the information needed for this page." };
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

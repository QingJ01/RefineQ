"use client";

import Link from "next/link";

import { BrandMark, BrandName } from "../components/brand";
import { useSessionLocale } from "../hooks/use-session-locale";


export default function Error({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  const locale = useSessionLocale();
  const text = locale === "zh"
    ? { kicker: "暂时走神了", title: "这一页没有顺利加载", body: "你的学习记录不会受影响。可以重新加载当前页面，或先返回学习首页。", retry: "重新加载", back: "返回首页" }
    : { kicker: "A brief interruption", title: "This page did not load", body: "Your learning records are safe. Reload this page or return to the learning home.", retry: "Reload", back: "Back home" };
  return (
    <main id="main-content" className="route-state-stage">
      <section className="route-state-card" role="alert">
        <div className="route-state-brand">
          <BrandMark size={42} />
          <BrandName />
        </div>
        <span className="kicker">{text.kicker}</span>
        <h1>{text.title}</h1>
        <p>{text.body}</p>
        <div className="route-state-actions">
          <button className="primary-action" type="button" onClick={() => reset()}>
            {text.retry}
          </button>
          <Link className="secondary-action" href="/">
            {text.back}
          </Link>
        </div>
      </section>
    </main>
  );
}

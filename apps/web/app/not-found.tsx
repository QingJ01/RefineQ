"use client";

import Link from "next/link";

import { BrandMark, BrandName } from "../components/brand";
import { useSessionLocale } from "../hooks/use-session-locale";


export default function NotFound() {
  const locale = useSessionLocale();
  const text = locale === "zh"
    ? { kicker: "404 · 页面未找到", title: "这条学习路径还不存在", body: "链接可能已更新，也可能只是输入错了。回到首页继续今天的学习吧。", back: "返回学习首页" }
    : { kicker: "404 · Page not found", title: "This learning path does not exist", body: "The link may have changed or been entered incorrectly. Return home to continue learning.", back: "Back to learning" };
  return (
    <main id="main-content" className="route-state-stage">
      <section className="route-state-card">
        <div className="route-state-brand">
          <BrandMark size={42} />
          <BrandName />
        </div>
        <span className="kicker">{text.kicker}</span>
        <h1>{text.title}</h1>
        <p>{text.body}</p>
        <div className="route-state-actions">
          <Link className="primary-action" href="/">
            {text.back}
          </Link>
        </div>
      </section>
    </main>
  );
}

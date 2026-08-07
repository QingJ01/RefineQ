"use client";

import Link from "next/link";

import { BrandMark, BrandName } from "../components/brand";


export default function Error({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <main id="main-content" className="route-state-stage">
      <section className="route-state-card" role="alert">
        <div className="route-state-brand">
          <BrandMark size={42} />
          <BrandName />
        </div>
        <span className="kicker">暂时走神了</span>
        <h1>这一页没有顺利加载</h1>
        <p>你的学习记录不会受影响。可以重新加载当前页面，或先返回学习首页。</p>
        <div className="route-state-actions">
          <button className="primary-action" type="button" onClick={() => reset()}>
            重新加载
          </button>
          <Link className="secondary-action" href="/">
            返回首页
          </Link>
        </div>
      </section>
    </main>
  );
}

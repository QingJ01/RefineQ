import Link from "next/link";

import { BrandMark, BrandName } from "../components/brand";


export default function NotFound() {
  return (
    <main id="main-content" className="route-state-stage">
      <section className="route-state-card">
        <div className="route-state-brand">
          <BrandMark size={42} />
          <BrandName />
        </div>
        <span className="kicker">404 · 页面未找到</span>
        <h1>这条学习路径还不存在</h1>
        <p>链接可能已更新，也可能只是输入错了。回到首页继续今天的学习吧。</p>
        <div className="route-state-actions">
          <Link className="primary-action" href="/">
            返回学习首页
          </Link>
        </div>
      </section>
    </main>
  );
}

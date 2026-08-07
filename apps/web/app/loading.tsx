import { BrandMark, BrandName } from "../components/brand";


export default function Loading() {
  return (
    <main
      id="main-content"
      className="route-state-stage"
      data-testid="route-loading"
      aria-busy="true"
      aria-live="polite"
    >
      <section className="route-state-card route-state-loading" aria-label="正在准备学习空间">
        <div className="route-state-brand">
          <BrandMark size={42} />
          <BrandName />
        </div>
        <span className="kicker">正在准备</span>
        <h1>把你的学习进度接回来</h1>
        <p>正在整理目标、资料和最近一次练习。</p>
        <div className="route-state-skeleton" aria-hidden="true">
          <i />
          <i />
          <i />
        </div>
      </section>
    </main>
  );
}

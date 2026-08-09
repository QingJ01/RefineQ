import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { LearningHome } from "../components/learning-home";
import { translator } from "../lib/i18n";

describe("dialog-first learning home", () => {
  it("keeps the Agent conversation ahead of workspace management", () => {
    const html = renderToStaticMarkup(
      <LearningHome
        t={translator("zh")}
        busy={false}
        workspaces={[]}
        onResolve={() => undefined}
        onOpen={() => undefined}
        onLogout={() => undefined}
        onToggleLocale={() => undefined}
      />,
    );

    expect(html).toContain('class="learning-home-hero"');
    expect(html.indexOf('id="learning-composer"')).toBeLessThan(html.indexOf('id="recent-learning"'));
    expect(html).not.toContain('data-testid="home-command-header"');
    expect(html).not.toContain('data-testid="current-learning-space"');
    expect(html).not.toContain('class="current-space-shortcuts"');
    expect(html).not.toContain('href="#learning-composer"');
    expect(html).not.toContain('href="#recent-learning"');
  });

  it("caps the learning intent at the backend length limit", () => {
    const html = renderToStaticMarkup(
      <LearningHome
        t={translator("zh")}
        busy={false}
        workspaces={[]}
        onResolve={() => undefined}
        onOpen={() => undefined}
        onLogout={() => undefined}
        onToggleLocale={() => undefined}
      />,
    );

    expect(html).toMatch(/data-testid="learning-intent"[^>]*maxLength="2000"/);
  });

  it("anchors the submission-facing prompt in one dated exam story", () => {
    const html = renderToStaticMarkup(
      <LearningHome
        t={translator("zh")}
        busy={false}
        workspaces={[]}
        onResolve={() => undefined}
        onOpen={() => undefined}
        onLogout={() => undefined}
        onToggleLocale={() => undefined}
      />,
    );

    expect(html).toContain("10 月 25 日考计算机组成原理期中");
    expect(html).toContain("每天能学 90 分钟");
    expect(html).toContain("计划、练习和掌握证据");
    expect(html).not.toContain("访谈分析");
  });

  it("uses the same desktop sidebar width as the learning workspace", () => {
    const styles = readFileSync(
      fileURLToPath(new URL("../app/styles.css", import.meta.url)),
      "utf8",
    );

    expect(styles).toMatch(/\.home-shell\s*\{[^}]*grid-template-columns:\s*264px minmax\(0, 1fr\)/s);
  });

  it("keeps global home navigation separate from workspace-local navigation", () => {
    const html = renderToStaticMarkup(
      <LearningHome
        t={translator("zh")}
        busy={false}
        workspaces={[{
          id: "calculus",
          title: "Calculus Sprint",
          subject: "mathematics",
          goal: "Master calculus foundations",
          topics: ["Derivative"],
          keywords: ["calculus"],
          routing_summary: "Calculus learning",
          archived: false,
          created_at: "2026-08-07T00:00:00Z",
          last_active_at: "2026-08-08T00:00:00Z",
        }]}
        onResolve={() => undefined}
        onOpen={() => undefined}
        onLogout={() => undefined}
        onToggleLocale={() => undefined}
      />,
    );

    expect(html).toContain('class="app-sidebar-global"');
    expect(html).toContain('class="app-recent-spaces"');
    expect(html).toContain('href="/"');
    expect(html).toContain('href="/learn/calculus/today"');
    expect(html).toContain("Calculus Sprint");
    expect(html).not.toContain('href="/learn/calculus/path"');
    expect(html).not.toContain('href="/learn/calculus/materials"');
    expect(html).not.toContain('href="/learn/calculus/progress"');
    expect(html).not.toContain('href="#learning-composer"');
    expect(html).not.toContain('href="#recent-learning"');
  });
});

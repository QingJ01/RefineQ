import { execFileSync } from "node:child_process";
import path from "node:path";

import { expect, test } from "@playwright/test";


const webRoot = path.resolve(__dirname, "../..");
const repositoryRoot = path.resolve(webRoot, "../..");
const python = process.env.REFINEQ_PYTHON ?? (
  process.platform === "win32"
    ? path.join(repositoryRoot, ".venv", "Scripts", "python.exe")
    : "python"
);
const adminEmail = `admin-e2e-${Date.now()}@example.com`;
const adminPassword = "correct-horse-battery-staple";

test.beforeAll(() => {
  execFileSync(
    python,
    [
      path.join(repositoryRoot, "scripts", "create_admin.py"),
      "--email",
      adminEmail,
      "--display-name",
      "E2E Administrator",
      "--data-root",
      path.join(webRoot, ".playwright-data"),
    ],
    {
      cwd: repositoryRoot,
      env: {
        ...process.env,
        PYTHONPATH: path.join(repositoryRoot, "src"),
        REFINEQ_ADMIN_PASSWORD: adminPassword,
      },
      stdio: "pipe",
    },
  );
});


test("learner completes and restores a source-grounded exam journey", async ({ page }, testInfo) => {
  test.slow();
  const uniqueEmail = `exam-learner-${Date.now()}@example.com`;
  const browserErrors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") browserErrors.push(message.text());
  });
  page.on("pageerror", (error) => browserErrors.push(error.message));

  await page.setViewportSize({ width: 1440, height: 1024 });
  await page.goto("/");
  await page.getByTestId("register-tab").click();
  await page.getByTestId("display-name").fill("Exam learner");
  await page.getByTestId("email").fill(uniqueEmail);
  await page.getByTestId("password").fill("correct-horse-battery-staple");
  await page.getByTestId("auth-submit").click();
  await page
    .getByTestId("learning-intent")
    .fill("Computer Architecture midterm on October 25, 90 minutes a day, starting with pipelines and caches");
  await page.getByTestId("start-learning").click();

  await expect(page).toHaveURL(/\/learn\/[^/]+\/today$/);
  await expect(page.getByTestId("learning-session-canvas")).toBeVisible();
  await expect(page.getByTestId("workspace-route-notice")).toBeVisible();
  await page.getByTestId("workspace-route-notice").getByRole("button").last().click();
  await expect(page.locator(".session-steps li")).toHaveCount(4);
  const initialExamDays = Number.parseInt(
    await page.getByTestId("exam-countdown").innerText(),
    10,
  );
  expect(initialExamDays).toBeGreaterThan(30);
  const workspaceTitle = await page.locator(".workspace-switcher > strong").innerText();

  await test.step("switch directly between learning spaces with keyboard-safe focus", async () => {
    await page.getByTestId("app-nav-home").click();
    await page.getByTestId("learning-intent").fill(
      "I want to practice conversational Spanish for an upcoming trip",
    );
    await page.getByTestId("start-learning").click();
    await expect(page).toHaveURL(/\/learn\/[^/]+\/today$/);
    await expect(page.locator(".workspace-switcher > strong")).not.toHaveText(workspaceTitle);
    const secondWorkspaceUrl = page.url();
    const secondWorkspaceId = new URL(secondWorkspaceUrl).pathname.split("/")[2];

    const trigger = page.getByTestId("workspace-switcher");
    await trigger.click();
    await expect(page.getByTestId("workspace-switcher-menu")).toBeVisible();
    await expect(page.getByTestId("workspace-switcher-all")).toBeVisible();
    const menuItems = page.getByRole("menuitem");
    await expect(menuItems.first()).toBeFocused();
    await expect(menuItems.first()).toHaveAttribute("tabindex", "0");
    await expect(menuItems.nth(1)).toHaveAttribute("tabindex", "-1");
    await page.keyboard.press("ArrowDown");
    await expect(menuItems.nth(1)).toBeFocused();
    await expect(menuItems.first()).toHaveAttribute("tabindex", "-1");
    await expect(menuItems.nth(1)).toHaveAttribute("tabindex", "0");
    await page.keyboard.press("Escape");
    await expect(trigger).toBeFocused();

    await trigger.click();
    await page.getByRole("menuitem", { name: new RegExp(workspaceTitle) }).click();
    await expect(page.locator(".workspace-switcher > strong")).toHaveText(workspaceTitle);
    await expect(page).toHaveURL(/\/learn\/[^/]+\/today$/);

    await page.route(`**/api/workspaces/${secondWorkspaceId}/snapshot`, async (route) => {
      await route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({ error: { code: "service_unavailable", message: "temporary" } }),
      });
    });
    await page.goBack();
    await expect(page).toHaveURL(secondWorkspaceUrl);
    await expect(page.getByTestId("workspace-route-state")).toBeVisible();
    await expect(page.locator(".workspace-switcher")).toHaveCount(0);
    await page.unroute(`**/api/workspaces/${secondWorkspaceId}/snapshot`);
    await page.goForward();
    await expect(page.locator(".workspace-switcher > strong")).toHaveText(workspaceTitle);
  });

  await test.step("use a short, varied exam path", async () => {
    await page.getByTestId("nav-path").click();
    await expect(page).toHaveURL(/\/path$/);
    await expect(page.locator(".plan-session")).toHaveCount(7);
    await page.getByTestId("toggle-plan-sessions").click();
    await expect(page.getByTestId("toggle-plan-sessions")).toHaveAttribute(
      "aria-expanded",
      "true",
    );
    const planSessionCount = await page.locator(".plan-session").count();
    expect(planSessionCount).toBeGreaterThan(30);
    await expect(page.locator(".plan-activity")).toHaveCount(planSessionCount);
    const firstSession = page.locator(".plan-session").first();
    await expect(firstSession.locator(".plan-topic strong")).not.toContainText("topic_");
    await firstSession.locator('[data-testid^="complete-session-"]').click();
    await expect(firstSession).toHaveClass(/completed/);
    await firstSession.locator('[data-testid^="complete-session-"]').click();
    await expect(firstSession).not.toHaveClass(/completed/);

    await page.getByTestId("plan-settings-toggle").click();
    const goal = page.getByTestId("plan-goal");
    const originalGoal = await goal.inputValue();
    await goal.fill("");
    await page.getByTestId("plan-settings-save").click();
    await expect(goal).toHaveAttribute("aria-invalid", "true");
    await page.getByTestId("plan-settings-cancel").click();
    await expect(goal).toHaveValue(originalGoal);

    await goal.fill(`${originalGoal} with a timed mock exam`);
    await page.getByTestId("plan-daily-minutes").fill("35");
    const movableTopic = page.locator('[data-testid^="plan-topic-down-"]:not(:disabled)').first();
    if (await movableTopic.count()) await movableTopic.click();
    await page.getByTestId("plan-settings-save").click();
    await expect(page.getByTestId("plan-settings-notice")).toBeVisible();
    await expect(page.locator(".minute-badge")).toContainText("35");

    await page.getByTestId("plan-settings-regenerate").click();
    await expect(page.getByTestId("confirm-dialog")).toBeVisible();
    await page.getByTestId("confirm-dialog-cancel").click();
    await expect(page.getByTestId("confirm-dialog")).toBeHidden();
    await page.getByTestId("plan-settings-regenerate").click();
    await page.getByTestId("confirm-dialog-confirm").click();
    await expect(page.getByTestId("confirm-dialog")).toBeHidden();
    await expect(page.locator(".plan-session")).toHaveCount(planSessionCount);
  });

  await test.step("keep mobile navigation accessible", async () => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.reload();
    await expect(page.getByTestId("learning-path-view")).toBeVisible();
    await page.keyboard.press("Tab");
    await expect(page.locator(".skip-link")).toBeFocused();
    await page.keyboard.press("Tab");
    await expect(page.getByTestId("app-nav-home")).toBeFocused();
    await page.keyboard.press("Tab");
    await expect(page.getByTestId("app-nav-calendar")).toBeFocused();
    await page.keyboard.press("Tab");
    await expect(page.getByTestId("workspace-switcher")).toBeFocused();
    await expect(page.getByTestId("workspace-switcher")).toBeVisible();
    expect((await page.getByTestId("workspace-switcher").boundingBox())?.height).toBeGreaterThanOrEqual(44);
    expect(await page.getByTestId("workspace-switcher").locator(":scope > strong").evaluate(
      (element) => Number.parseFloat(getComputedStyle(element).fontSize),
    )).toBeGreaterThanOrEqual(12);
    await expect(page.getByTestId("workspace-switcher")).toHaveAccessibleName(
      new RegExp(workspaceTitle.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")),
    );
    for (const testId of ["nav-today", "nav-path", "nav-materials", "nav-progress"]) {
      await expect(page.getByTestId(testId)).toHaveAccessibleName(/.+/);
    }
    await expect(page.getByTestId("mobile-section-context")).toBeVisible();
    await expect(page.getByTestId("mobile-section-title")).toContainText(/Path|路径/);
    const materialsShortcut = page.getByTestId("mobile-shortcut-materials");
    expect((await materialsShortcut.boundingBox())?.height).toBeGreaterThanOrEqual(44);
    await materialsShortcut.click();
    await expect(page).toHaveURL(/\/materials$/);
    await expect(page.getByTestId("mobile-section-title")).toBeFocused();
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
    ).toBe(true);
    await page.getByTestId("mobile-shortcut-today").click();
    await expect(page.getByTestId("mobile-sticky-task-action")).toBeVisible();
    await expect(page.getByTestId("mobile-sticky-task-action")).toHaveCSS("position", "sticky");
    await page.getByTestId("mobile-shortcut-path").click();
    await page.waitForTimeout(450);
    await page.screenshot({ path: testInfo.outputPath("exam-learning-mobile.png") });
    await page.setViewportSize({ width: 1440, height: 1024 });
  });

  await test.step("return to personal home and recover the same workspace with browser history", async () => {
    const repeatedRestoreRequests: string[] = [];
    const recordRestoreRequest = (request: { url(): string }) => {
      const url = new URL(request.url());
      if (
        url.pathname.endsWith("/api/auth/me")
        || /\/api\/workspaces\/?$/.test(url.pathname)
        || url.pathname.endsWith("/snapshot")
      ) repeatedRestoreRequests.push(url.pathname);
    };
    page.on("request", recordRestoreRequest);
    await page.getByTestId("app-nav-home").click();
    await expect(page).toHaveURL(/\/$/);
    await expect(page.getByTestId("learning-intent")).toBeVisible();
    await page.goBack();
    await expect(page).toHaveURL(/\/learn\/[^/]+\/path$/);
    await expect(page.getByTestId("learning-path-view")).toBeVisible();
    page.off("request", recordRestoreRequest);
    expect(repeatedRestoreRequests).toEqual([]);
  });

  await test.step("upload computer architecture study sources", async () => {
    await page.getByTestId("nav-materials").click();
    await page.locator('input[type="file"]').setInputFiles({
      name: "computer-architecture-notes.txt",
      mimeType: "text/plain",
      buffer: Buffer.from(
        "Computer Architecture midterm review: pipelines overlap fetch, decode, execute, memory, and write-back to improve throughput; caches use temporal and spatial locality. 流水线的数据冒险可以通过转发或停顿处理，缓存利用局部性降低平均访存时间。",
      ),
    });
    await expect(
      page.locator(".material-list .material-title-row > span").getByText(
        "computer-architecture-notes.txt",
        { exact: true },
      ),
    ).toBeVisible();
    await page.locator('input[type="file"]').setInputFiles({
      name: "cache-review.md",
      mimeType: "text/markdown",
      buffer: Buffer.from(
        "# 缓存复习\n\n平均访存时间由命中时间、缺失率和缺失代价共同决定。直接映射缓存中，一个主存块只有一个候选位置。",
      ),
    });
    const notesMaterial = page.locator(".material-list li").filter({ hasText: "cache-review.md" });
    await expect(notesMaterial).toBeVisible();
    await notesMaterial.locator('[data-testid^="material-edit-"]').click();
    await notesMaterial.locator(".material-edit-form input").nth(0).fill("缓存复习笔记");
    await notesMaterial.locator(".material-edit-form input").nth(1).fill("exam, cache");
    await notesMaterial.locator('.material-edit-form button[type="submit"]').click();
    await expect(notesMaterial).toContainText("缓存复习笔记");
    await page.getByTestId("material-filter-tag").selectOption("exam");
    await expect(page.locator(".material-list li")).toHaveCount(1);
    await page.getByTestId("material-sort").selectOption("title");
    await page.getByTestId("material-filter-tag").selectOption("all");
    await expect(page.locator(".material-list li")).toHaveCount(2);
    await page.getByTestId("material-search").fill("流水线 数据冒险");
    await page.locator(".material-search button").click();
    await expect(page.locator(".material-search-results")).toContainText("computer-architecture-notes.txt");
    await page.getByTestId("nav-today").click();
    await expect(page.locator(".session-sources")).toContainText("computer-architecture-notes.txt");
  });

  await test.step("complete two exam-learning tasks", async () => {
    await page.getByTestId("learning-mode-exam").click();
    await expect(page.getByTestId("learning-mode-exam")).toHaveAttribute("aria-pressed", "true");
    await page.getByTestId("session-start-task").click();
    await expect(page.getByTestId("session-practice-stage")).toBeVisible();
    await page.screenshot({ path: testInfo.outputPath("exam-learning-practice.png") });
    const firstQuestionId = await page.getByTestId("session-practice-stage").getAttribute("data-question-id");
    expect(firstQuestionId).toBeTruthy();

    await page.getByTestId("practice-sources").click();
    await expect(page.getByRole("dialog")).toContainText("computer-architecture-notes.txt");
    await page.keyboard.press("Escape");
    const savedPrompt = await page.getByTestId("session-practice-stage").locator("h2").innerText();
    await page.getByTestId("save-question").click();
    await expect(page.getByTestId("save-question")).toHaveAttribute("aria-pressed", "true");
    await page.setViewportSize({ width: 390, height: 844 });
    await page.getByTestId("practice-answer").fill("unfinished mobile draft");
    await page.getByTestId("skip-question").click();
    await expect(page.getByRole("dialog")).toContainText(/unsaved|未提交/i);
    await page.getByTestId("confirm-dialog-cancel").click();
    await expect(page.getByTestId("practice-answer")).toHaveValue("unfinished mobile draft");
    await expect(page.getByTestId("session-practice-stage")).toHaveAttribute(
      "data-question-id",
      firstQuestionId!,
    );
    await page.getByTestId("skip-question").click();
    await page.getByTestId("confirm-dialog-confirm").click();
    await page.setViewportSize({ width: 1440, height: 1024 });
    await expect(page.getByTestId("session-practice-stage")).not.toHaveAttribute(
      "data-question-id",
      firstQuestionId!,
    );
    await expect(page.getByTestId("saved-question-list")).toContainText(savedPrompt);
    await page.getByTestId("practice-saved-question").first().click();
    await expect(page.getByTestId("session-practice-stage")).toHaveAttribute(
      "data-question-id",
      firstQuestionId!,
    );
    await expect(page.getByTestId("session-practice-stage").locator("h2")).toHaveText(savedPrompt);
    await page.getByTestId("skip-question").click();
    await expect(page.getByTestId("session-practice-stage")).not.toHaveAttribute(
      "data-question-id",
      firstQuestionId!,
    );

    await page.getByTestId("practice-answer").fill(
      "流水线通过让多条指令的取指、译码、执行、访存和写回阶段重叠来提高吞吐量。遇到 RAW 数据冒险时可用转发把结果送到后续指令，无法转发时插入停顿；分支预测错误则清空错误路径。易错点是吞吐量提高不等于单条指令延迟一定下降。",
    );
    await page.getByTestId("submit-answer").click();
    await expect(page.getByTestId("session-reflect-stage")).toBeVisible();
    await expect(page.locator(".feedback-score")).toContainText("/100");

    await page.getByTestId("next-question").click();
    await page.getByTestId("practice-answer").fill(
      "缓存依靠时间局部性和空间局部性减少访问主存的次数。平均访存时间等于命中时间加缺失率乘缺失代价；计算时必须把百分比换成小数，并区分直接映射中的冲突缺失与容量缺失。",
    );
    await page.getByTestId("submit-answer").click();
    await expect(page.getByTestId("session-reflect-stage")).toBeVisible();

    await page.getByTestId("nav-progress").click();
    await expect(page).toHaveURL(/\/progress$/);
    await expect(page.locator('[data-testid^="attempt-rubric-"]').first()).toBeVisible();
    await expect(page.locator(".evidence-timeline > li")).toHaveCount(2);
    await expect(page.locator(".evidence-timeline")).not.toContainText("topic_");
    await expect(page.getByTestId("review-queue-empty")).toBeVisible();

    await page.locator('[data-testid^="progress-topic-"]').first().click();
    await expect(page.getByTestId("progress-topic-detail")).toBeVisible();
    const rubric = page.locator('[data-testid^="attempt-rubric-"]').first();
    await rubric.locator("summary").click();
    await expect(rubric).toContainText("computer-architecture-notes.txt");
    const note = rubric.locator('[data-testid^="attempt-note-"]');
    await note.fill("Please review how the source-grounded reasoning was weighed.");
    await rubric.locator('[data-testid^="save-attempt-note-"]').click();
    const appeal = rubric.locator('[data-testid^="appeal-attempt-"]');
    await appeal.click();
    await expect(appeal).toHaveAttribute("aria-pressed", "true");
    const retryPrompt = await rubric.locator('[data-testid^="attempt-question-"]').innerText();
    await rubric.locator('[data-testid^="retry-attempt-"]').click();
    await expect(page).toHaveURL(/\/today$/);
    await expect(page.getByTestId("session-practice-stage")).toContainText(retryPrompt);
  });

  await test.step("restore sources and keep the session usable when the coach is unavailable", async () => {
    await page.reload();
    await expect(page.locator(".workspace-switcher > strong")).toHaveText(workspaceTitle);
    await page.getByTestId("nav-materials").click();
    await expect(
      page.locator(".material-list .material-title-row > span").getByText(
        "computer-architecture-notes.txt",
        { exact: true },
      ),
    ).toBeVisible();
    await page.getByTestId("nav-today").click();
    await expect(page.locator(".coach-capability-notice")).toBeVisible();
    await expect(page.getByTestId("session-coach-input")).toBeDisabled();
    await expect(page.getByTestId("learning-session-canvas")).toBeVisible();
    await page.waitForTimeout(450);
    await page.screenshot({ path: testInfo.outputPath("exam-learning-desktop.png") });
  });

  await test.step("show a localized recovery error even before authentication is restored", async () => {
    await page.route("**/api/auth/me", async (route) => {
      await route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({ error: { code: "service_unavailable", message: "temporary" } }),
      });
    });
    await page.reload();
    await expect(page.getByTestId("auth-restore-error")).toBeVisible();
    await page.unroute("**/api/auth/me");
    await page.reload();
    await expect(page.locator(".workspace-switcher > strong")).toHaveText(workspaceTitle);
    for (let index = browserErrors.length - 1; index >= 0; index -= 1) {
      if (browserErrors[index].includes("status of 503")) browserErrors.splice(index, 1);
    }
  });

  await test.step("update and export the account without losing the active workspace", async () => {
    await page.getByTestId("app-nav-account").click();
    await expect(page).toHaveURL(/\/account$/);
    await expect(page.getByTestId("account-center")).toBeVisible();
    const profileForm = page.getByTestId("account-profile-form");
    await profileForm.locator("input").first().fill("Exam learner updated");
    await profileForm.locator("button").click();
    await expect(page.locator(".account-identity-stamp strong")).toHaveText(
      "Exam learner updated",
    );

    const downloadPromise = page.waitForEvent("download");
    await page.getByTestId("account-export").click();
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toMatch(/^refineq-account-\d{4}-\d{2}-\d{2}\.json$/);

    await page.locator(".account-header-actions a").click();
    await expect(page).toHaveURL(/\/learn\/[^/]+\/today$/);
    await expect(page.locator(".workspace-switcher > strong")).toHaveText(workspaceTitle);
  });

  await test.step("confirm before bulk deleting organized sources", async () => {
    await page.getByTestId("nav-materials").click();
    await expect(page.locator(".material-list li")).toHaveCount(2);
    await page.getByTestId("material-select-all").check();
    await expect(page.getByTestId("material-bulk-delete")).toBeEnabled();
    await page.getByTestId("material-bulk-delete").click();
    await page.getByTestId("confirm-dialog-cancel").click();
    await expect(page.locator(".material-list li")).toHaveCount(2);
    await page.getByTestId("material-bulk-delete").click();
    await page.getByTestId("confirm-dialog-confirm").click();
    await expect(page.locator(".material-list li")).toHaveCount(0);
  });

  const unexpectedBrowserErrors = browserErrors.filter(
    (message) => !message.includes("status of 409"),
  );
  expect(unexpectedBrowserErrors).toEqual([]);
});


test("mobile learner completes a source-grounded exam loop", async ({ page }, testInfo) => {
  test.slow();
  const uniqueEmail = `mobile-exam-${Date.now()}@example.com`;

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await page.getByTestId("register-tab").click();
  await page.getByTestId("display-name").fill("Mobile exam learner");
  await page.getByTestId("email").fill(uniqueEmail);
  await page.getByTestId("password").fill("correct-horse-battery-staple");
  await page.getByTestId("auth-submit").click();
  await page.getByTestId("learning-intent").fill(
    "10 月 25 日考计算机组成原理期中，每天能学 90 分钟，先补流水线和缓存",
  );
  await page.getByTestId("start-learning").click();

  await expect(page).toHaveURL(/\/learn\/[^/]+\/today$/);
  await expect(page.getByTestId("learning-session-canvas")).toBeVisible();
  const routeNotice = page.getByTestId("workspace-route-notice");
  if (await routeNotice.isVisible()) await routeNotice.getByRole("button").last().click();

  await page.getByTestId("mobile-shortcut-materials").click();
  await expect(page).toHaveURL(/\/materials$/);
  await page.locator('input[type="file"]').setInputFiles({
    name: "mobile-computer-architecture.txt",
    mimeType: "text/plain",
    buffer: Buffer.from(
      "流水线通过重叠取指、译码、执行、访存和写回提高吞吐量。RAW 数据冒险可用转发或停顿处理。缓存利用时间局部性和空间局部性降低平均访存时间。",
    ),
  });
  await expect(
    page.locator(".material-list .material-title-row > span").getByText(
      "mobile-computer-architecture.txt",
      { exact: true },
    ),
  ).toBeVisible();

  await page.getByTestId("mobile-shortcut-today").click();
  await expect(page).toHaveURL(/\/today$/);
  await expect(page.locator(".session-sources")).toContainText(
    "mobile-computer-architecture.txt",
  );
  await page.getByTestId("learning-mode-exam").click();
  await expect(page.getByTestId("learning-mode-exam")).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await page.getByTestId("session-start-task").click();
  await expect(page.getByTestId("session-practice-stage")).toBeVisible();
  await page.getByTestId("practice-sources").click();
  await expect(page.getByRole("dialog")).toContainText(
    "mobile-computer-architecture.txt",
  );
  await page.keyboard.press("Escape");
  await page.getByTestId("practice-answer").fill(
    "流水线让多条指令的不同阶段重叠执行，从而提高吞吐量。遇到 RAW 数据冒险时，优先通过转发把结果送到后续指令，无法转发时插入停顿；分支预测错误要清空错误路径。易错点是把吞吐量提升误认为单条指令延迟一定降低。",
  );
  await page.getByTestId("submit-answer").click();
  await expect(page.getByTestId("session-reflect-stage")).toBeVisible();
  await expect(page.locator(".feedback-score")).toContainText("/100");

  await page.getByTestId("mobile-shortcut-progress").click();
  await expect(page).toHaveURL(/\/progress$/);
  await expect(page.locator(".evidence-timeline > li")).toHaveCount(1);
  await expect(page.locator('[data-testid^="attempt-rubric-"]').first()).toContainText(
    "mobile-computer-architecture.txt",
  );
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
  ).toBe(true);
  await page.screenshot({ path: testInfo.outputPath("mobile-exam-loop.png") });
});


test("administrator routes and operations survive real navigation", async ({ page }, testInfo) => {
  await page.goto("/");
  await page.getByTestId("email").fill(adminEmail);
  await page.getByTestId("password").fill(adminPassword);
  await page.getByTestId("auth-submit").click();
  await expect(page.getByTestId("learning-intent")).toBeVisible();

  await page.getByTestId("app-nav-admin").click();
  await expect(page).toHaveURL(/\/admin$/);
  await expect(page.getByTestId("admin-overview")).toBeVisible();
  await expect(page.getByTestId("admin-system-status")).toBeVisible();
  await expect(page.getByTestId("admin-next-action")).toBeVisible();
  await expect(page.getByTestId("admin-principles")).toBeVisible();

  await page.locator('.admin-nav a[href="/admin/integrations/chat"]').click();
  await expect(page).toHaveURL(/\/admin\/integrations\/chat$/);
  await expect(page.getByTestId("integration-card-chat")).toBeVisible();
  await expect(page.getByTestId("admin-form-section-basic")).toBeVisible();
  await expect(page.getByTestId("admin-form-section-credentials")).toBeVisible();
  await expect(page.getByTestId("admin-form-section-network")).toBeVisible();
  await expect(page.locator('[data-testid^="integration-card-"]')).toHaveCount(1);

  const modelInput = page.locator('input[placeholder="gpt-4.1-mini"]');
  const savedModel = await modelInput.inputValue();
  await modelInput.fill(`${savedModel || "demo"}-dirty`);
  await expect(page.getByText(/Unsaved changes|未保存/)).toBeVisible();
  await page.locator('.admin-nav a[href="/admin"]').click();
  await expect(page.getByTestId("confirm-dialog")).toBeVisible();
  await page.getByTestId("confirm-dialog-cancel").click();
  await expect(page).toHaveURL(/\/admin\/integrations\/chat$/);

  await page.locator('.admin-nav a[href="/admin"]').click();
  await page.getByTestId("confirm-dialog-confirm").click();
  await expect(page).toHaveURL(/\/admin$/);

  await page.goBack();
  await expect(page).toHaveURL(/\/admin\/integrations\/chat$/);
  await expect(page.getByTestId("admin-integration-detail")).toBeVisible();
  await page.reload();
  await expect(page.getByTestId("admin-integration-detail")).toBeVisible();

  await page.locator('.admin-nav a[href="/admin/operations"]').click();
  await expect(page).toHaveURL(/\/admin\/operations$/);
  await expect(page.getByTestId("admin-users")).toContainText(adminEmail);
  await expect(page.getByTestId("admin-jobs")).toBeVisible();
  await expect(page.getByTestId("admin-activity")).toBeVisible();
  await expect(page.getByTestId("admin-backups")).toBeVisible();

  await page.getByTestId("admin-create-backup").click();
  await expect(page.locator(".admin-backup-list li").first()).toBeVisible();
  await page.locator(".admin-backup-list li").first().locator("button").click();
  await expect(page.getByTestId("confirm-dialog")).toContainText("RESTORE");
  await page.getByTestId("confirm-dialog-confirm").click();
  await expect(page.getByTestId("confirm-dialog")).toBeHidden();
  await page.waitForTimeout(250);
  await page.screenshot({ path: testInfo.outputPath("admin-operations-desktop.png") });

  await page.setViewportSize({ width: 390, height: 844 });
  await page.reload();
  const mobileOperations = page.getByTestId("admin-operations");
  await expect(mobileOperations).toBeVisible();
  await expect(mobileOperations).toHaveAttribute("aria-busy", "false");
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
  ).toBe(true);
  await page.screenshot({ path: testInfo.outputPath("admin-operations-mobile.png") });

  await page.route("**/api/admin/jobs", async (route) => {
    await route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({
        error: {
          code: "service_unavailable",
          message: "D:\\sensitive\\admin.sqlite3",
        },
      }),
    });
  });
  await page.reload();
  const localizedError = page.locator('.admin-operations-notice[role="alert"]');
  await expect(localizedError).toContainText("服务暂时不可用，请稍后重试。");
  await expect(localizedError).not.toContainText("admin.sqlite3");
});


test("learner can reset a forgotten password and sign in again", async ({ page }) => {
  const uniqueEmail = `reset-learner-${Date.now()}@example.com`;
  const originalPassword = "correct-horse-battery-staple";
  const replacementPassword = "replacement-horse-battery-staple";

  await page.goto("/");
  await page.getByTestId("register-tab").click();
  await page.getByTestId("display-name").fill("Reset learner");
  await page.getByTestId("email").fill(uniqueEmail);
  await page.getByTestId("password").fill(originalPassword);
  await page.getByTestId("auth-submit").click();
  await page.getByTestId("app-logout").click();

  await page.getByTestId("forgot-password").click();
  await page.getByTestId("email").fill(uniqueEmail);
  await page.getByTestId("auth-submit").click();
  await expect(page.getByTestId("reset-token")).toHaveValue(/.+/);
  await page.getByTestId("password").fill(replacementPassword);
  await page.locator('input[autocomplete="new-password"]').last().fill(replacementPassword);
  await page.getByTestId("auth-submit").click();

  await expect(page.getByTestId("forgot-password")).toBeVisible();
  await page.getByTestId("password").fill(replacementPassword);
  await page.getByTestId("auth-submit").click();
  await expect(page.getByTestId("learning-intent")).toBeVisible();
});


test("learner cannot stay on an administrator route", async ({ page }) => {
  const uniqueEmail = `route-learner-${Date.now()}@example.com`;
  await page.goto("/");
  await page.getByTestId("register-tab").click();
  await page.getByTestId("display-name").fill("Route learner");
  await page.getByTestId("email").fill(uniqueEmail);
  await page.getByTestId("password").fill(adminPassword);
  await page.getByTestId("auth-submit").click();
  await expect(page.getByTestId("learning-intent")).toBeVisible();

  await page.goto("/admin");
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByTestId("learning-intent")).toBeVisible();
});


test("unknown routes offer a direct way back to learning", async ({ page }) => {
  await page.goto("/this-learning-route-does-not-exist");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("学习路径");
  const homeLink = page.getByRole("link", { name: "返回学习首页" });
  await expect(homeLink).toHaveAttribute("href", "/");
  await homeLink.click();
  await expect(page).toHaveURL(/\/$/);
});

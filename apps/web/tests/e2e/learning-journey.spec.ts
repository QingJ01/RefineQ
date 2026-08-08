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


test("learner completes and restores a capability learning journey", async ({ page }, testInfo) => {
  const uniqueEmail = `capability-learner-${Date.now()}@example.com`;
  const browserErrors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") browserErrors.push(message.text());
  });
  page.on("pageerror", (error) => browserErrors.push(error.message));

  await page.setViewportSize({ width: 1440, height: 1024 });
  await page.goto("/");
  await page.getByTestId("register-tab").click();
  await page.getByTestId("display-name").fill("Capability learner");
  await page.getByTestId("email").fill(uniqueEmail);
  await page.getByTestId("password").fill("correct-horse-battery-staple");
  await page.getByTestId("auth-submit").click();
  await page
    .getByTestId("learning-intent")
    .fill("I want to learn product thinking, validate real user needs, and complete an interview analysis");
  await page.getByTestId("start-learning").click();

  await expect(page).toHaveURL(/\/learn\/[^/]+\/today$/);
  await expect(page.getByTestId("learning-session-canvas")).toBeVisible();
  await expect(page.getByTestId("workspace-route-notice")).toBeVisible();
  await page.getByTestId("workspace-route-notice").getByRole("button").last().click();
  await expect(page.locator(".session-steps li")).toHaveCount(4);
  const workspaceTitle = await page.locator(".workspace-switcher > strong").innerText();

  await test.step("switch directly between learning spaces with keyboard-safe focus", async () => {
    await page.getByTestId("workspace-home-link").click();
    await page.getByTestId("learning-intent").fill(
      "I want to practice conversational Spanish for an upcoming trip",
    );
    await page.getByTestId("start-learning").click();
    await expect(page).toHaveURL(/\/learn\/[^/]+\/today$/);
    await expect(page.locator(".workspace-switcher > strong")).not.toHaveText(workspaceTitle);

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
  });

  await test.step("use a short, varied capability path", async () => {
    await page.getByTestId("nav-path").click();
    await expect(page).toHaveURL(/\/path$/);
    await expect(page.locator(".plan-session")).toHaveCount(7);
    await expect(page.locator(".plan-activity")).toHaveCount(7);
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

    await goal.fill(`${originalGoal} with a reviewed case study`);
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
    await expect(page.locator(".plan-session")).toHaveCount(7);
  });

  await test.step("keep mobile navigation accessible", async () => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.reload();
    await expect(page.getByTestId("learning-path-view")).toBeVisible();
    await page.keyboard.press("Tab");
    await expect(page.locator(".skip-link")).toBeFocused();
    await page.keyboard.press("Tab");
    await expect(page.getByTestId("workspace-switcher")).toBeFocused();
    await expect(page.getByTestId("workspace-switcher")).toBeVisible();
    expect((await page.getByTestId("workspace-switcher").boundingBox())?.height).toBeGreaterThanOrEqual(44);
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
    await page.screenshot({ path: testInfo.outputPath("capability-learning-mobile.png") });
    await page.setViewportSize({ width: 1440, height: 1024 });
  });

  await test.step("return to personal home and recover the same workspace with browser history", async () => {
    await page.getByTestId("workspace-home-link").click();
    await expect(page).toHaveURL(/\/$/);
    await expect(page.getByTestId("learning-intent")).toBeVisible();
    await page.goBack();
    await expect(page).toHaveURL(/\/learn\/[^/]+\/path$/);
    await expect(page.getByTestId("learning-path-view")).toBeVisible();
  });

  await test.step("upload a real interview source", async () => {
    await page.getByTestId("nav-materials").click();
    await page.locator('input[type="file"]').setInputFiles({
      name: "user-interview.txt",
      mimeType: "text/plain",
      buffer: Buffer.from(
        "用户需求验证：A user asked for data export, but repeated interview evidence showed the underlying need was a trustworthy weekly reporting workflow. Validate the problem before choosing a feature solution.",
      ),
    });
    await expect(page.locator(".material-list").getByText("user-interview.txt")).toBeVisible();
    await page.getByTestId("material-search").fill("weekly reporting workflow");
    await page.locator(".material-search button").click();
    await expect(page.locator(".material-search-results")).toContainText("user-interview.txt");
    await page.getByTestId("nav-today").click();
    await expect(page.locator(".session-sources")).toContainText("user-interview.txt");
  });

  await test.step("complete two case-learning tasks", async () => {
    await page.getByTestId("learning-mode-case").click();
    await expect(page.getByTestId("learning-mode-case")).toHaveAttribute("aria-pressed", "true");
    await page.getByTestId("session-start-task").click();
    await expect(page.getByTestId("session-practice-stage")).toBeVisible();
    await page.screenshot({ path: testInfo.outputPath("capability-learning-practice.png") });
    const firstQuestionId = await page.getByTestId("session-practice-stage").getAttribute("data-question-id");
    expect(firstQuestionId).toBeTruthy();

    await page.getByTestId("practice-sources").click();
    await expect(page.getByRole("dialog")).toContainText("user-interview.txt");
    await page.keyboard.press("Escape");
    await page.getByTestId("save-question").click();
    await expect(page.getByTestId("save-question")).toHaveAttribute("aria-pressed", "true");
    await page.getByTestId("skip-question").click();
    await expect(page.getByTestId("session-practice-stage")).not.toHaveAttribute(
      "data-question-id",
      firstQuestionId!,
    );

    await page.getByTestId("practice-answer").fill(
      "The stated request is export, but the recurring job is reliable weekly reporting. I would interview five similar users, compare their current workaround, and test a lightweight report prototype before committing to an export feature.",
    );
    await page.getByTestId("submit-answer").click();
    await expect(page.getByTestId("session-reflect-stage")).toBeVisible();
    await expect(page.locator(".feedback-score")).toContainText("/100");

    await page.getByTestId("next-question").click();
    await page.getByTestId("practice-answer").fill(
      "I would separate the requested solution from the underlying outcome, gather behavioral evidence, define a falsifiable success signal, and compare the smallest alternatives before building.",
    );
    await page.getByTestId("submit-answer").click();
    await expect(page.getByTestId("session-reflect-stage")).toBeVisible();

    await page.getByTestId("nav-progress").click();
    await expect(page).toHaveURL(/\/progress$/);
    await expect(page.locator(".evidence-timeline li")).toHaveCount(2);
    await expect(page.locator(".evidence-timeline")).not.toContainText("topic_");
    await expect(page.getByTestId("review-queue-empty")).toBeVisible();

    await page.locator('[data-testid^="progress-topic-"]').first().click();
    await expect(page.getByTestId("progress-topic-detail")).toBeVisible();
    const rubric = page.locator('[data-testid^="attempt-rubric-"]').first();
    await rubric.locator("summary").click();
    await expect(rubric).toContainText("user-interview.txt");
    const note = rubric.locator('[data-testid^="attempt-note-"]');
    await note.fill("Please review how the evidence was weighed.");
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
    await expect(page.locator(".material-list").getByText("user-interview.txt")).toBeVisible();
    await page.getByTestId("nav-today").click();
    await expect(page.locator(".coach-capability-notice")).toBeVisible();
    await expect(page.getByTestId("session-coach-input")).toBeDisabled();
    await expect(page.getByTestId("learning-session-canvas")).toBeVisible();
    await page.screenshot({ path: testInfo.outputPath("capability-learning-desktop.png") });
  });

  await test.step("confirm before deleting a source", async () => {
    await page.getByTestId("nav-materials").click();
    const material = page.locator(".material-list").getByText("user-interview.txt");
    await page.getByTestId(/material-delete-/).click();
    await page.getByTestId("confirm-dialog-cancel").click();
    await expect(material).toBeVisible();
    await page.getByTestId(/material-delete-/).click();
    await page.getByTestId("confirm-dialog-confirm").click();
    await expect(material).toBeHidden();
  });

  const unexpectedBrowserErrors = browserErrors.filter(
    (message) => !message.includes("status of 409"),
  );
  expect(unexpectedBrowserErrors).toEqual([]);
});


test("administrator routes survive direct navigation, refresh, and browser history", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByTestId("email").fill(adminEmail);
  await page.getByTestId("password").fill(adminPassword);
  await page.getByTestId("auth-submit").click();
  await expect(page.getByTestId("learning-intent")).toBeVisible();

  await page.getByTestId("home-admin").click();
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
  await page.getByTestId("home-logout").click();

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

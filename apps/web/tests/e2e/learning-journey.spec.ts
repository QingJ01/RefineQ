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


test.skip("legacy projectless study journey", async ({ page }, testInfo) => {
  const uniqueEmail = `learner-${Date.now()}@example.com`;

  await test.step("register and let the Agent establish a learning space", async () => {
    await page.goto("/");
    await page.getByTestId("register-tab").click();
    await page.getByTestId("display-name").fill("End-to-end learner");
    await page.getByTestId("email").fill(uniqueEmail);
    await page.getByTestId("password").fill("correct-horse-battery-staple");
    await page.getByTestId("auth-submit").click();

    await expect(page.getByTestId("learning-intent")).toBeVisible();
    await page
      .getByTestId("learning-intent")
      .fill("I have a calculus exam in two weeks and want to review limits today");
    await page.getByTestId("start-learning").click();

    await expect(page).toHaveURL(/\/learn\/[^/]+\/today$/);
    await expect(page.locator(".workspace-header h1")).toBeVisible();
    await expect(page.getByTestId("workspace-route-notice")).toBeVisible();
    await expect(page.locator(".plan-card")).toBeVisible();
    await expect(page.locator(".plan-session")).toHaveCount(7);
    const planToggle = page.getByTestId("toggle-plan-sessions");
    const totalSessions = Number((await planToggle.innerText()).match(/\d+/)?.[0]);
    expect(totalSessions).toBeGreaterThan(7);
    await planToggle.click();
    await expect(page.locator(".plan-session")).toHaveCount(totalSessions);
    await planToggle.click();
    await expect(page.locator(".plan-session")).toHaveCount(7);

    const firstSession = page.locator(".plan-session").first();
    await expect(firstSession.locator(".plan-topic strong")).toContainText(/limits/i);
    await expect(firstSession.locator(".plan-topic strong")).not.toContainText("topic_");
    await firstSession.locator('[data-testid^="complete-session-"]').click();
    await expect(firstSession).toHaveClass(/completed/);
    await firstSession.locator('[data-testid^="complete-session-"]').click();
    await expect(firstSession).not.toHaveClass(/completed/);
  });

  const workspaceTitle = await page.locator(".workspace-header h1").innerText();

  await test.step("keep mobile navigation accessible when labels are visually hidden", async () => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.reload();
    await expect(page.locator(".workspace-header h1")).toBeVisible();
    await page.keyboard.press("Tab");
    await expect(page.locator(".skip-link")).toBeFocused();
    await expect(page.locator(".skip-link")).toBeVisible();
    await page.keyboard.press("Tab");
    await expect(page.locator(".workspace-sidebar .sidebar-brand")).toHaveAccessibleName("RefineQ");
    await expect(page.getByTestId("nav-today")).toHaveAccessibleName(/今日|Today/);
    await expect(page.getByTestId("nav-materials")).toHaveAccessibleName(/资料|Materials/);
    await expect(page.getByTestId("nav-evidence")).toHaveAccessibleName(/证据|Evidence/);
    await expect(page.getByTestId("nav-coach")).toHaveAccessibleName(/Agent/);
    await page.screenshot({ path: testInfo.outputPath("learning-mobile.png") });
    await page.setViewportSize({ width: 1280, height: 720 });
  });

  await test.step("upload personal study material", async () => {
    await page.getByTestId("nav-materials").click();
    await expect(page).toHaveURL(/\/materials$/);
    await page.locator('input[type="file"]').setInputFiles({
      name: "calculus-notes.txt",
      mimeType: "text/plain",
      buffer: Buffer.from(
        "Calculus limits describe the value approached by a function. For example, x squared approaches four as x approaches two.",
      ),
    });
    await expect(page.locator(".material-list").getByText("calculus-notes.txt")).toBeVisible();
    await page.getByTestId("material-search").fill("function approaches");
    await page.locator(".material-search button").click();
    await expect(page.locator(".material-search-results")).toContainText("calculus-notes.txt");
    const download = page.waitForEvent("download");
    await page.getByTestId(/material-download-/).click();
    expect((await download).suggestedFilename()).toBe("calculus-notes.txt");
    await page.getByTestId("nav-today").click();
    await expect(page).toHaveURL(/\/today$/);
    await page.getByTestId("nav-materials").click();
    await expect(page).toHaveURL(/\/materials$/);
    await expect(page.locator(".material-list").getByText("calculus-notes.txt")).toBeVisible();
    await page.goBack();
    await expect(page).toHaveURL(/\/today$/);
    await page.goForward();
    await expect(page).toHaveURL(/\/materials$/);
  });

  await test.step("answer a generated question and record grading evidence", async () => {
    await page.getByTestId("nav-today").click();
    await page.getByTestId("practice-difficulty").selectOption("4");
    await page.locator(".plan-session").first().locator('[data-testid^="start-session-"]').click();
    await expect(page.locator(".question-sheet h3")).toBeVisible();
    await expect(page.locator(".question-sheet .practice-meta")).toContainText("4");
    const firstQuestionId = await page.locator(".question-sheet").getAttribute("data-question-id");
    expect(firstQuestionId).toBeTruthy();

    await page.getByTestId("practice-sources").click();
    await expect(page.getByRole("dialog")).toContainText("calculus-notes.txt");
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog")).toBeHidden();

    await page.getByTestId("save-question").click();
    await expect(page.getByTestId("save-question")).toHaveAttribute("aria-pressed", "true");
    await expect(page.getByTestId("practice-saved-question")).toHaveCount(1);

    await page.getByTestId("skip-question").click();
    await expect(page.locator(".question-sheet")).not.toHaveAttribute(
      "data-question-id",
      firstQuestionId!,
    );
    await page
      .getByTestId("practice-answer")
      .fill(
        "A calculus limit is the value that a function approaches. For example, x squared approaches four when x approaches two.",
      );
    await page.getByTestId("submit-answer").click();
    await expect(page.locator(".practice-result")).toContainText(/评分|Score/);
    await expect(page.locator(".progress-stats")).toContainText("1");

    await page.getByTestId("retry-topic").click();
    await expect(page.getByTestId("practice-answer")).toBeVisible();
    await page
      .getByTestId("practice-answer")
      .fill(
        "A limit describes a function's approached value near a point. For example, x approaches two while x squared approaches four.",
      );
    await page.getByTestId("submit-answer").click();
    await expect(page.locator(".progress-stats")).toContainText("2");

    await page.getByTestId("nav-evidence").click();
    await expect(page).toHaveURL(/\/evidence$/);
    await expect(page.locator(".evidence-timeline li")).toHaveCount(2);
    await expect(page.locator(".progress-stats")).toContainText("2");
  });

  await test.step("restore the same space and material after refresh", async () => {
    await page.reload();
    await expect(page.locator(".workspace-header h1")).toHaveText(workspaceTitle);
    await page.getByTestId("nav-today").click();
    await expect(page.getByTestId("practice-saved-question")).toHaveCount(1);
    await page.getByTestId("nav-materials").click();
    await expect(page).toHaveURL(/\/materials$/);
    await expect(page.locator(".material-list").getByText("calculus-notes.txt")).toBeVisible();
  });

  await test.step("open the grounded learning Agent", async () => {
    await page.getByTestId("nav-coach").click();
    await expect(page).toHaveURL(/\/coach$/);
    await expect(page.getByTestId("model-status")).toBeVisible();
    await page.locator(".chat-composer textarea").fill("Explain my weakest point");
    await page.locator(".chat-composer button").click();
    await expect(page.locator(".agent-card .error-banner")).toContainText(
      /模型设置|Configure a model/,
    );
    await expect(page.getByTestId("agent-retry")).toBeVisible();
    await expect(page.getByTestId("agent-new-conversation")).toBeVisible();
    await expect(page.getByTestId("agent-history")).toBeVisible();
    await page.locator(".chat-composer textarea").focus();
    await page.screenshot({ path: testInfo.outputPath("learning-desktop.png"), fullPage: true });
  });

  await test.step("confirm before deleting a study material", async () => {
    await page.getByTestId("nav-materials").click();
    const material = page.locator(".material-list").getByText("calculus-notes.txt");
    await page.getByTestId(/material-delete-/).click();
    await expect(page.getByTestId("confirm-dialog")).toBeVisible();
    await page.getByTestId("confirm-dialog-cancel").click();
    await expect(material).toBeVisible();

    await page.getByTestId(/material-delete-/).click();
    await page.getByTestId("confirm-dialog-confirm").click();
    await expect(material).toBeHidden();
    await expect(page.getByTestId("confirm-dialog")).toBeHidden();
  });

  await test.step("archive and restore the learning space", async () => {
    await page.locator(".workspace-sidebar .sidebar-brand").click();
    await expect(page).toHaveURL(/\/$/);
    await page.getByTestId(/workspace-archive-/).click();
    await expect(page.locator(".recent-card")).toHaveCount(0);
    await page.getByTestId("archived-workspaces-toggle").click();
    await expect(page.locator(".recent-card.archived")).toContainText(workspaceTitle);
    await page.getByTestId(/workspace-archive-/).click();
    await expect(page.locator(".recent-card:not(.archived)")).toContainText(workspaceTitle);
  });
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
  const workspaceTitle = await page.locator(".sidebar-learning > strong").innerText();

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
  });

  await test.step("keep mobile navigation accessible", async () => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.reload();
    await expect(page.getByTestId("learning-path-view")).toBeVisible();
    await page.keyboard.press("Tab");
    await expect(page.locator(".skip-link")).toBeFocused();
    await page.keyboard.press("Tab");
    await expect(page.locator(".workspace-sidebar .sidebar-brand")).toHaveAccessibleName("RefineQ");
    for (const testId of ["nav-today", "nav-path", "nav-materials", "nav-progress"]) {
      await expect(page.getByTestId(testId)).toHaveAccessibleName(/.+/);
    }
    await page.screenshot({ path: testInfo.outputPath("capability-learning-mobile.png") });
    await page.setViewportSize({ width: 1440, height: 1024 });
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
  });

  await test.step("restore sources and use the contextual coach", async () => {
    await page.reload();
    await expect(page.locator(".workspace-header h1")).toHaveText(workspaceTitle);
    await page.getByTestId("nav-materials").click();
    await expect(page.locator(".material-list").getByText("user-interview.txt")).toBeVisible();
    await page.getByTestId("nav-today").click();
    await page.getByTestId("session-coach-input").fill("Help me strengthen the evidence in my analysis");
    await page.locator(".session-coach-form button").click();
    await expect(page.getByTestId("session-coach-input")).toBeEnabled();
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

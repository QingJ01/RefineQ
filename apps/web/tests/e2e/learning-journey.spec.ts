import { expect, test } from "@playwright/test";


test("learner completes and restores a projectless study journey", async ({ page }) => {
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

    await expect(page.locator(".workspace-header h1")).toBeVisible();
    await expect(page.locator(".plan-card")).toBeVisible();
  });

  const workspaceTitle = await page.locator(".workspace-header h1").innerText();

  await test.step("keep mobile navigation accessible when labels are visually hidden", async () => {
    await page.setViewportSize({ width: 390, height: 844 });
    await expect(page.locator(".workspace-sidebar .sidebar-brand")).toHaveAccessibleName("RefineQ");
    await expect(page.getByTestId("nav-today")).toHaveAccessibleName(/今日|Today/);
    await expect(page.getByTestId("nav-materials")).toHaveAccessibleName(/资料|Materials/);
    await expect(page.getByTestId("nav-evidence")).toHaveAccessibleName(/证据|Evidence/);
    await expect(page.getByTestId("nav-coach")).toHaveAccessibleName(/Agent/);
    await page.setViewportSize({ width: 1280, height: 720 });
  });

  await test.step("upload personal study material", async () => {
    await page.getByTestId("nav-materials").click();
    await page.locator('input[type="file"]').setInputFiles({
      name: "calculus-notes.txt",
      mimeType: "text/plain",
      buffer: Buffer.from(
        "Calculus limits describe the value approached by a function. For example, x squared approaches four as x approaches two.",
      ),
    });
    await expect(page.getByText("calculus-notes.txt")).toBeVisible();
    await page.getByTestId("nav-today").click();
    await page.getByTestId("nav-materials").click();
    await expect(page.getByText("calculus-notes.txt")).toBeVisible();
  });

  await test.step("answer a generated question and record grading evidence", async () => {
    await page.getByTestId("nav-today").click();
    await page.getByTestId("get-question").click();
    await expect(page.locator(".question-sheet h3")).toBeVisible();
    await page
      .getByTestId("practice-answer")
      .fill(
        "A calculus limit is the value that a function approaches. For example, x squared approaches four when x approaches two.",
      );
    await page.getByTestId("submit-answer").click();
    await expect(page.getByRole("status")).toContainText(/评分|Score/);
    await expect(page.locator(".progress-stats")).toContainText("1");

    await page.getByTestId("next-question").click();
    await expect(page.getByTestId("practice-answer")).toBeVisible();
    await page
      .getByTestId("practice-answer")
      .fill(
        "A limit describes a function's approached value near a point. For example, x approaches two while x squared approaches four.",
      );
    await page.getByTestId("submit-answer").click();
    await expect(page.locator(".progress-stats")).toContainText("2");

    await page.getByTestId("nav-evidence").click();
    await expect(page.locator(".evidence-timeline li")).toHaveCount(2);
  });

  await test.step("restore the same space and material after refresh", async () => {
    await page.reload();
    await expect(page.locator(".workspace-header h1")).toHaveText(workspaceTitle);
    await page.getByTestId("nav-materials").click();
    await expect(page.getByText("calculus-notes.txt")).toBeVisible();
  });

  await test.step("open the grounded learning Agent", async () => {
    await page.getByTestId("nav-coach").click();
    await expect(page.getByTestId("model-settings")).toBeVisible();
    await page.locator(".chat-composer textarea").fill("Explain my weakest point");
    await page.locator(".chat-composer button").click();
    await expect(page.locator(".agent-card .error-banner")).toContainText(
      /模型设置|Configure a model/,
    );
    await expect(page.getByTestId("agent-retry")).toBeVisible();
  });
});

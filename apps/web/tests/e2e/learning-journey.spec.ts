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

    await expect(page.locator(".rail-learning h1")).toBeVisible();
    await expect(page.locator(".plan-card")).toBeVisible();
  });

  const workspaceTitle = await page.locator(".rail-learning h1").innerText();

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
    await expect(page.locator(".rail-stats")).toContainText("01");

    await page.getByTestId("nav-evidence").click();
    await expect(page.locator(".ledger-list li")).toHaveCount(1);
  });

  await test.step("restore the same space and material after refresh", async () => {
    await page.reload();
    await expect(page.locator(".rail-learning h1")).toHaveText(workspaceTitle);
    await page.getByTestId("nav-materials").click();
    await expect(page.getByText("calculus-notes.txt")).toBeVisible();
  });

  await test.step("open the grounded learning Agent", async () => {
    await page.getByTestId("nav-coach").click();
    await expect(page.getByTestId("model-settings")).toBeVisible();
  });
});

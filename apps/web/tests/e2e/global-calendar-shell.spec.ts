import { expect, test } from "@playwright/test";


test("shared shell connects global calendar, workspace task, and account", async ({ page }, testInfo) => {
  test.slow();
  const uniqueEmail = `calendar-learner-${Date.now()}@example.com`;

  await page.setViewportSize({ width: 1440, height: 1024 });
  await page.goto("/");
  await page.getByTestId("register-tab").click();
  await page.getByTestId("display-name").fill("Calendar learner");
  await page.getByTestId("email").fill(uniqueEmail);
  await page.getByTestId("password").fill("correct-horse-battery-staple");
  await page.getByTestId("auth-submit").click();
  await page.getByTestId("learning-intent").fill(
    "Calculus final on October 25, 45 minutes a day, focusing on limits and derivatives",
  );
  await page.getByTestId("start-learning").click();

  await expect(page).toHaveURL(/\/learn\/[^/]+\/today$/);
  await expect(page.getByTestId("next-action-upload_material")).toBeVisible();
  await expect(page.getByTestId("app-sidebar")).toBeVisible();
  await page.getByTestId("app-nav-calendar").click();
  await expect(page).toHaveURL(/\/calendar$/);
  await expect(page.getByTestId("global-calendar")).toBeVisible();
  await expect.poll(async () => (
    Number.parseInt(await page.locator(".calendar-summary dd").first().innerText(), 10)
  )).toBeGreaterThan(0);

  const sidebarBox = await page.getByTestId("app-sidebar").boundingBox();
  const calendarBox = await page.getByTestId("global-calendar").boundingBox();
  expect(sidebarBox).not.toBeNull();
  expect(calendarBox).not.toBeNull();
  expect(sidebarBox!.x + sidebarBox!.width).toBeLessThanOrEqual(calendarBox!.x + 1);

  await page.screenshot({
    path: testInfo.outputPath("global-calendar-desktop.png"),
    fullPage: true,
  });

  const eventDay = page.locator(".global-calendar-day:not([data-empty])").first();
  await expect(eventDay).toBeVisible();
  await eventDay.click();
  const taskLink = page.locator(".global-day-agenda a").first();
  await expect(taskLink).toBeVisible();
  await taskLink.click();
  await expect(page).toHaveURL(/\/learn\/[^/]+\/today\?session=.+/);
  await expect(page.getByTestId("next-action-upload_material")).toBeVisible();

  await page.getByTestId("app-nav-account").click();
  await expect(page).toHaveURL(/\/account$/);
  await expect(page.getByTestId("account-center")).toBeVisible();
  await expect(page.getByTestId("app-sidebar")).toBeVisible();
  await page.screenshot({
    path: testInfo.outputPath("account-shared-shell.png"),
    fullPage: true,
  });

  await page.getByTestId("app-nav-calendar").click();
  await expect(page).toHaveURL(/\/calendar$/);
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByTestId("app-sidebar")).toBeVisible();
  await expect(page.getByTestId("global-calendar")).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1)).toBe(true);

  await page.screenshot({
    path: testInfo.outputPath("global-calendar-mobile.png"),
    fullPage: true,
  });
});

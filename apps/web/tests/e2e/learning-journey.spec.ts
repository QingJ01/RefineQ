import { expect, test } from "@playwright/test";


test("learner completes the evidence-driven study journey", async ({ page }) => {
  const uniqueEmail = `learner-${Date.now()}@example.com`;
  const examDate = new Date(Date.now() + 14 * 24 * 60 * 60 * 1000)
    .toISOString()
    .slice(0, 10);

  await test.step("register and define an exam goal", async () => {
    await page.goto("/");
    await page.locator(".auth-tabs").getByRole("button", { name: "注册" }).click();
    await page.getByLabel("怎么称呼你").fill("端到端学习者");
    await page.getByLabel("邮箱").fill(uniqueEmail);
    await page.getByLabel("密码").fill("correct-horse-battery-staple");
    await page.locator("form").getByRole("button", { name: /注册/ }).click();

    await expect(page.getByRole("heading", { name: "建立备考项目" })).toBeVisible();
    await page.getByLabel("项目名称").fill("微积分冲刺");
    await page.getByLabel("考试目标").fill("掌握极限与导数基础");
    await page.getByLabel("考试日期").fill(examDate);
    await page.getByLabel("每日分钟").fill("45");
    await page.getByLabel("知识点（逗号分隔）").fill("Limits, Derivatives");
    await page.getByRole("button", { name: /生成学习路径/ }).click();

    await expect(page.getByRole("heading", { name: "微积分冲刺" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "学习路径" })).toBeVisible();
  });

  await test.step("upload personal study material", async () => {
    await page.getByRole("button", { name: /资料/ }).click();
    await page.locator('input[type="file"]').setInputFiles({
      name: "calculus-notes.txt",
      mimeType: "text/plain",
      buffer: Buffer.from("A limit describes the value approached by a function."),
    });
    await expect(page.getByText("calculus-notes.txt")).toBeVisible();
    await expect(page.getByText(/资料已建立索引/)).toBeVisible();
  });

  await test.step("answer a retrieval question and see progress evidence", async () => {
    await page.getByRole("button", { name: /今日/ }).click();
    await page.getByRole("button", { name: "抽一道题" }).click();
    await expect(page.getByRole("heading", { name: "Define or explain: Limits" })).toBeVisible();
    await page.getByPlaceholder("用自己的话写下答案……").fill("Limits");
    await page.getByRole("button", { name: /提交作答/ }).click();
    await expect(page.getByRole("status")).toContainText("已掌握");
    await expect(page.locator(".rail-stats")).toContainText("01");

    await page.getByRole("button", { name: /证据/ }).click();
    await expect(page.getByRole("heading", { name: "学习证据账本" })).toBeVisible();
    await expect(page.getByText(/Practice response for topic-1 was correct/)).toBeVisible();
  });

  await test.step("open the project-grounded learning agent", async () => {
    await page.getByRole("button", { name: /学习 Agent/ }).click();
    await expect(page.getByRole("heading", { name: "向 Agent 提问" })).toBeVisible();
    await expect(page.getByRole("button", { name: "模型设置" })).toBeVisible();
  });
});


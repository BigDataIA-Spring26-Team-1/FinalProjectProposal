import { expect, test } from "@playwright/test";

test.describe.configure({ mode: "serial" });

test("backend health and dashboard endpoints respond", async ({ request }) => {
  const health = await request.get("http://127.0.0.1:8000/api/health");
  expect(health.ok()).toBeTruthy();

  const dashboard = await request.get("http://127.0.0.1:8000/api/dashboard");
  expect(dashboard.ok()).toBeTruthy();
  const payload = await dashboard.json();
  expect(Array.isArray(payload.liveFeed)).toBeTruthy();
});

test("chat endpoint returns an advisor response", async ({ request }) => {
  const response = await request.post("http://127.0.0.1:8000/api/chat", {
    data: {
      question: "Explain what this digital twin does for a manufacturing company.",
      history: [],
      active_view: "advisor",
      selected_line: {
        id: 1,
        name: "Line A - Chassis",
      },
    },
  });

  expect(response.ok()).toBeTruthy();
  const payload = await response.json();
  expect(typeof payload.answer).toBe("string");
  expect(payload.answer.length).toBeGreaterThan(20);
});

test("factory floor, simulation, advisor, and pipeline flows render", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByText("DIGITAL TWIN")).toBeVisible();
  await expect(page.getByRole("button", { name: "Factory Floor" })).toBeVisible();
  await expect(page.getByText("Factory Floor Layout")).toBeVisible();

  await page.getByRole("button", { name: "Add Line" }).click();
  await expect(page.getByText("Line D")).toBeVisible();

  const shiftInput = page.locator('input[type="number"]').first();
  await shiftInput.fill("10");
  await expect(shiftInput).toHaveValue("10");

  await page.getByRole("button", { name: "Simulate" }).click();
  await expect(page.getByText("Run Simulation")).toBeVisible();
  await page.getByRole("button", { name: "Run" }).click();
  await expect(page.getByText("WEEKLY PROFIT")).toBeVisible({ timeout: 30000 });
  await expect(page.getByText("Production Over Time - Line A - Chassis")).toBeVisible();
  await expect(page.getByText("Cost Breakdown - Line A - Chassis")).toBeVisible();

  await page.locator("select").first().selectOption("1");
  await expect(page.getByText("Production Over Time - Line B - Electronics")).toBeVisible();
  await expect(page.getByText("Cost Breakdown - Line B - Electronics")).toBeVisible();

  await page.getByRole("button", { name: "AI Advisor" }).click();
  await expect(page.getByText("AI Manufacturing Advisor")).toBeVisible();
  const advisorInput = page.getByPlaceholder(
    "Ask about bottlenecks, architecture, data sources, companies, or optimization...",
  );
  await advisorInput.fill("Explain what this digital twin does for a manufacturing company.");
  await advisorInput.press("Enter");
  await expect(advisorInput).toHaveValue("");

  await page.getByRole("button", { name: "Data Pipeline" }).click();
  await expect(page.getByText("Data Pipeline Status")).toBeVisible();
  await expect(page.getByText("Pipeline Jobs")).toBeVisible();
  await expect(page.getByText("Data Sources")).toBeVisible();
});

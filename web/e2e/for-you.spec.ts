import { test, expect } from '@playwright/test';

test('for-you redirects unauthenticated users to login', async ({ page }) => {
  await page.goto('/for-you');
  await expect(page).toHaveURL(/\/auth\/login\?redirect=%2Ffor-you/);
});

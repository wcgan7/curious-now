import { test, expect } from '@playwright/test';

async function apiAvailable(request: typeof test.request) {
  try {
    const res = await request.get('http://localhost:8000/v1/feed?tab=latest&page=1&page_size=1');
    return res.ok();
  } catch {
    return false;
  }
}

test('home renders feed', async ({ page, request }) => {
  test.skip(!(await apiAvailable(request)), 'API server not available at http://localhost:8000');

  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Latest' })).toBeVisible();

  const storyLink = page.locator('a[href^="/story/"]').first();
  await expect(storyLink).toBeVisible();
});


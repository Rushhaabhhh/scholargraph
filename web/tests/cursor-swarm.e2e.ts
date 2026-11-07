import { expect, test } from '@playwright/test';

test('the intro reveals the final results area and leaves it usable', async ({
  page,
}) => {
  test.setTimeout(45000);
  await page.emulateMedia({ reducedMotion: 'no-preference' });
  await page.goto('/');
  const swarm = page.locator('.swarm-layer');
  const heading = page.locator('.results-heading');
  const placeholder = page.locator('.results-placeholder');
  await expect(swarm).toHaveClass(/is-running/);
  await expect(heading).toHaveAttribute('style', /clip-path/);
  await expect(placeholder).toHaveAttribute('style', /clip-path/);
  await expect(swarm).not.toHaveClass(/is-running/, { timeout: 30000 });
  await expect(heading).toBeVisible();
  await expect(placeholder).toBeVisible();
  await expect(
    page.getByRole('button', { name: 'Ask graph assistant' }),
  ).toHaveCount(0);
  expect(await heading.evaluate((element) => element.style.clipPath)).toBe('');
  expect(await placeholder.evaluate((element) => element.style.clipPath)).toBe(
    '',
  );
  await expect(heading).toBeInViewport();
});

test('skipping the intro restores the final results area', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'no-preference' });
  await page.goto('/');
  await page.getByRole('button', { name: /Skip intro/ }).click();
  const placeholder = page.locator('.results-placeholder');
  await expect(placeholder).toBeVisible();
  expect(await placeholder.evaluate((element) => element.style.clipPath)).toBe(
    '',
  );
});

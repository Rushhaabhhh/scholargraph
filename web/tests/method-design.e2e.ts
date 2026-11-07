import { expect, test } from '@playwright/test';

test('method stages respond to hover and keyboard and results expose clear evidence controls', async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto('/#how-it-works');
  const connect = page.getByRole('tab', { name: /connect/i });
  await connect.hover();
  await expect(connect).toHaveAttribute('aria-selected', 'true');
  await expect(
    page.getByRole('heading', { name: 'See the connections.' }),
  ).toBeVisible();
  await expect(page.getByLabel('connect process diagram')).toBeVisible();
  await expect(connect.locator('.method-plus')).toHaveCSS(
    'transform',
    'matrix(0, -1, 1, 0, 0, 0)',
  );
  await connect.focus();
  await page.keyboard.press('ArrowDown');
  await expect(page.getByRole('tab', { name: /retrieve/i })).toHaveAttribute(
    'aria-selected',
    'true',
  );
  await expect(
    page.getByRole('heading', { name: 'Find the signal.' }),
  ).toBeVisible();

  await page.getByLabel('RESEARCH QUESTION OR TOPIC').fill('graph retrieval');
  await page.getByRole('button', { name: /Find researchers/ }).click();
  const card = page.locator('article.expert-card').first();
  await expect(card).toBeVisible({ timeout: 60000 });
  await expect(card.getByText('Not a probability')).toHaveCount(0);
  const summary = card.locator('.expert-evidence > summary');
  await expect(summary).toContainText('View evidence');
  await expect(summary.locator('svg')).toHaveCount(0);
  const before = await summary.evaluate(
    (node) => getComputedStyle(node).backgroundColor,
  );
  await summary.hover();
  await expect
    .poll(() =>
      summary.evaluate((node) => getComputedStyle(node).backgroundColor),
    )
    .not.toBe(before);
  await summary.click();
  await expect(card.locator('.evidence-list')).toBeVisible();
  await expect(
    card.getByRole('link', { name: 'Open evidence profile' }).locator('svg'),
  ).toHaveCount(0);
  await expect(page.getByText('REFINE YOUR SEARCH')).toHaveCount(0);
});

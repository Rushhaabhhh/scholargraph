import { test, expect } from '@playwright/test';
test('search, refine with graph tools, and keep shortlist memory in one session', async ({
  page,
}) => {
  test.setTimeout(120000);
  await page.goto('/');
  await page.getByLabel('RESEARCH QUESTION OR TOPIC').fill('graph retrieval');
  await page.getByRole('button', { name: /Find researchers/ }).click();
  await expect(page.locator('article').nth(1)).toBeVisible({ timeout: 60000 });
  await page
    .locator('article')
    .first()
    .getByRole('button', { name: 'Ask assistant' })
    .click();
  const assistant = page.getByRole('dialog', { name: 'Research assistant' });
  const message = assistant.getByLabel('Message research assistant');
  const send = async (text: string) => {
    await message.fill(text);
    await assistant.getByRole('button', { name: 'Send message' }).click();
  };
  await send('Show profile #1');
  await expect(
    assistant.getByText('Retrieve researcher profile · success'),
  ).toBeVisible();
  await send('Find collaboration path between #1 and #2');
  await expect(
    assistant.getByText('Trace collaboration path · success'),
  ).toBeVisible();
  await send('Shortlist #1');
  await expect(assistant.getByText(/Decision saved: shortlist/)).toBeVisible();
  await send('search again');
  await expect(
    assistant.getByText('Search researchers · success'),
  ).toBeVisible({ timeout: 30000 });
  await expect(
    assistant.getByText(/1 shortlisted · 0 dismissed · Search context:/),
  ).toBeVisible();
  await assistant
    .getByRole('button', { name: 'Close research assistant' })
    .click();
  await expect(
    page
      .locator('article')
      .first()
      .getByRole('button', { name: /Shortlisted/ }),
  ).toBeVisible();
  await page
    .locator('article')
    .first()
    .getByRole('button', { name: 'Ask assistant' })
    .click();
  page.once('dialog', (dialog) => dialog.accept());
  await assistant.getByRole('button', { name: 'Clear', exact: true }).click();
  await expect(assistant.locator('.session-memory')).toContainText(
    '0 shortlisted · 0 dismissed',
  );
});
test('reconnects automatically after a temporary session startup failure', async ({
  page,
}) => {
  let attempts = 0;
  await page.route('**/api/sessions', (route) => {
    if (route.request().method() === 'POST' && ++attempts === 1)
      return route.fulfill({
        status: 503,
        contentType: 'application/json',
        body: JSON.stringify({
          code: 'backend_unavailable',
          message: 'Backend temporarily unavailable',
        }),
      });
    return route.continue();
  });
  await page.goto('/');
  await expect(page.locator('.error-banner[role="alert"]')).toContainText(
    'Backend temporarily unavailable',
  );
  await expect.poll(() => attempts, { timeout: 15000 }).toBeGreaterThan(1);
  await page.getByLabel('RESEARCH QUESTION OR TOPIC').fill('graph retrieval');
  const submit = page.getByRole('button', { name: /Find researchers/ });
  await expect(submit).toBeEnabled();
  await submit.click();
  await expect(page.locator('article').first()).toBeVisible({ timeout: 60000 });
});
test('search results show an interactive evidence graph', async ({ page }) => {
  await page.goto('/');
  await page.getByLabel('RESEARCH QUESTION OR TOPIC').fill('graph retrieval');
  await page.getByRole('button', { name: /Find researchers/ }).click();
  await expect(page.locator('article').first()).toBeVisible({ timeout: 60000 });
  const graph = page.getByRole('region', {
    name: 'Interactive publication and researcher network',
  });
  await expect(graph).toBeVisible();
  await graph
    .getByRole('button', { name: /^Publication:/ })
    .first()
    .focus();
  await expect(page.getByText(/^THE PUBLICATION ·/)).toBeVisible();
});
test('search, inspect evidence and save a decision', async ({ page }) => {
  await page.goto('/');
  await page.getByLabel('RESEARCH QUESTION OR TOPIC').fill('graph retrieval');
  await page.getByRole('button', { name: /Find researchers/ }).click();
  const card = page.locator('article').first();
  await expect(card).toBeVisible({ timeout: 60000 });
  await card.getByText(/View evidence/).click();
  await expect(card.getByText(/DBLP ·/).first()).toBeVisible();
  await card.getByRole('button', { name: '+ Shortlist' }).click();
  await expect(card.getByRole('button', { name: /Shortlisted/ })).toBeVisible();
  await card.locator('a').first().click();
  await expect(
    page.getByRole('heading', { name: 'Publication timeline' }),
  ).toBeVisible();
});
test('failed shortlist is not shown as saved', async ({ page }) => {
  await page.goto('/');
  await page.getByLabel('RESEARCH QUESTION OR TOPIC').fill('graph retrieval');
  await page.getByRole('button', { name: /Find researchers/ }).click();
  const card = page.locator('article').first();
  await expect(card).toBeVisible({ timeout: 60000 });
  await page.route('**/api/sessions/*/decisions/*', (route) =>
    route.fulfill({
      status: 503,
      contentType: 'application/json',
      body: JSON.stringify({
        code: 'failure',
        message: 'Decision could not be saved',
      }),
    }),
  );
  await card.getByRole('button', { name: '+ Shortlist' }).click();
  await expect(page.getByText('Decision could not be saved')).toBeVisible();
  await expect(card.getByRole('button', { name: '+ Shortlist' })).toBeVisible();
});
test('a newer search wins when an earlier search is delayed', async ({
  page,
}) => {
  await page.goto('/');
  let searches = 0;
  await page.route('**/api/search', async (route) => {
    searches++;
    if (searches === 1)
      await new Promise((resolve) => setTimeout(resolve, 1400));
    try {
      await route.continue();
    } catch {}
  });
  await page.getByLabel('RESEARCH QUESTION OR TOPIC').fill('graph retrieval');
  await page.getByRole('button', { name: /Find researchers/ }).click();
  await expect.poll(() => searches).toBe(1);
  await page
    .getByLabel('RESEARCH QUESTION OR TOPIC')
    .fill('information retrieval');
  await page.getByRole('button', { name: /Searching/ }).click();
  await expect(page.locator('article').first()).toBeVisible({ timeout: 60000 });
  await page.waitForTimeout(1600);
  await expect(page.getByLabel('RESEARCH QUESTION OR TOPIC')).toHaveValue(
    'information retrieval',
  );
  await expect(
    page.getByRole('heading', { name: /Researchers for your question/ }),
  ).toBeVisible();
});
test('mobile search remains usable without navigation', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/');
  await expect(
    page.getByRole('navigation', { name: 'Main navigation' }),
  ).toHaveCount(0);
  await page.getByLabel('RESEARCH QUESTION OR TOPIC').fill('graph retrieval');
  await page.getByRole('button', { name: /Find researchers/ }).click();
  const card = page.locator('article').first();
  await expect(card).toBeVisible({ timeout: 60000 });
  await card.getByRole('button', { name: '+ Shortlist' }).click();
  await expect(card.getByRole('button', { name: /Shortlisted/ })).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});
test('rejected results keep their original rank', async ({ page }) => {
  await page.goto('/');
  await page.getByLabel('RESEARCH QUESTION OR TOPIC').fill('graph retrieval');
  await page.getByRole('button', { name: /Find researchers/ }).click();
  const cards = page.locator('article');
  await expect(cards.nth(1)).toBeVisible({ timeout: 60000 });
  const second = await cards.nth(1).locator('a').first().textContent();
  await cards
    .first()
    .getByRole('button', { name: /Reject/ })
    .click();
  await expect(cards.first().locator('.expert-rank')).toHaveText('02');
  await expect(cards.first().locator('a').first()).toHaveText(second!);
});
test('supported recency and year filters are sent to search', async ({
  page,
}) => {
  await page.goto('/');
  await page.getByLabel('Since year').fill('2018');
  await page.getByLabel('RESEARCH QUESTION OR TOPIC').fill('graph retrieval');
  let sent: Record<string, unknown> | undefined;
  page.on('request', (request) => {
    if (request.url().endsWith('/api/search')) sent = request.postDataJSON();
  });
  await page.getByRole('button', { name: /Find researchers/ }).click();
  await expect(page.locator('article').first()).toBeVisible({ timeout: 60000 });
  expect(sent?.since_year).toBe(2018);
  expect(sent?.recency_preference).toBeNull();
  await expect(page.getByText('Since 2018')).toBeVisible();
});
test('query dates, explicit overrides and abstention', async ({ page }) => {
  await page.goto('/');
  const query = page.getByLabel('RESEARCH QUESTION OR TOPIC');
  await query.fill('graph retrieval since 2018');
  await page.getByRole('button', { name: /Find researchers/ }).click();
  await expect(page.locator('article').first()).toBeVisible({ timeout: 60000 });
  await expect(page.getByText('Since 2018', { exact: true })).toBeVisible();
  await page.getByLabel('Publication activity').selectOption('any');
  await page.getByRole('button', { name: /Find researchers/ }).click();
  await expect(page.getByText('Since 2018', { exact: true })).toHaveCount(0);
  await query.fill('zxqvplm wkrjty nonsensephrase');
  await page.getByRole('button', { name: /Find researchers/ }).click();
  await expect(
    page.getByText('No researchers found for this view.'),
  ).toBeVisible();
});
test('shortlist route compares and changes server-backed decisions', async ({
  page,
}) => {
  await page.goto('/');
  await page.getByLabel('RESEARCH QUESTION OR TOPIC').fill('graph retrieval');
  await page.getByRole('button', { name: /Find researchers/ }).click();
  const cards = page.locator('article');
  await expect(cards.nth(1)).toBeVisible({ timeout: 60000 });
  await cards.nth(0).getByRole('button', { name: '+ Shortlist' }).click();
  await expect(
    cards.nth(0).getByRole('button', { name: /Shortlisted/ }),
  ).toBeVisible();
  await cards.nth(1).getByRole('button', { name: '+ Shortlist' }).click();
  await expect(
    cards.nth(1).getByRole('button', { name: /Shortlisted/ }),
  ).toBeVisible();
  await page.getByRole('link', { name: 'Open saved workspace' }).click();
  await expect(
    page.getByRole('heading', { name: 'Saved & session.' }),
  ).toBeVisible();
  await expect(
    page.getByText('Shortlisted', { exact: false }).first(),
  ).toBeVisible();
  const checks = page.getByRole('checkbox');
  await checks.nth(0).check();
  await checks.nth(1).check();
  await page.getByRole('button', { name: 'Compare selected experts' }).click();
  await expect(
    page.getByRole('heading', { name: 'Compare experts' }),
  ).toBeVisible();
  await page.getByRole('button', { name: 'Close' }).click();
  await page
    .locator('.saved-card')
    .first()
    .getByRole('button', { name: 'Reject' })
    .click();
  await page.getByRole('tab', { name: /Rejected/ }).click();
  await expect(page.locator('.saved-card')).toHaveCount(1);
  await page
    .locator('.saved-card')
    .getByRole('button', { name: 'Restore' })
    .click();
  await expect(page.getByRole('tab', { name: /Rejected/ })).toContainText('0');
});
test('settings require confirmation and report server-confirmed session deletion', async ({
  page,
}) => {
  await page.goto('/');
  await page.getByRole('link', { name: 'Open saved workspace' }).click();
  await expect(
    page.getByRole('heading', { name: 'Your session memory' }),
  ).toBeVisible();
  page.once('dialog', (dialog) => dialog.dismiss());
  await page.getByRole('button', { name: 'Delete session' }).click();
  await expect(
    page.getByRole('heading', { name: 'Your session memory' }),
  ).toBeVisible();
  page.once('dialog', (dialog) => dialog.accept());
  await page.getByRole('button', { name: 'Delete session' }).click();
  await expect(page.getByRole('status')).toContainText(
    'Session memory deleted',
  );
});
test('profile actions use the same server session and return to search', async ({
  page,
}) => {
  await page.goto('/');
  await page.getByLabel('RESEARCH QUESTION OR TOPIC').fill('graph retrieval');
  await page.getByRole('button', { name: /Find researchers/ }).click();
  const first = page.locator('article').first();
  await expect(first).toBeVisible({ timeout: 60000 });
  const name = await first.locator('.expert-identity a').textContent();
  await first.locator('.expert-identity a').click();
  await expect(
    page.getByRole('heading', { name: 'Publication timeline' }),
  ).toBeVisible();
  await expect(page.getByText(/Name source records/)).toBeVisible();
  await page.getByRole('button', { name: '+ Shortlist' }).click();
  await expect(page.getByRole('button', { name: /Shortlisted/ })).toBeVisible();
  await page
    .getByRole('link', { name: 'Ask assistant about this expert' })
    .click();
  await expect(page).toHaveURL(/\/chat/);
  await expect(page.getByLabel('Message', { exact: true })).toHaveValue(
    `What can you tell me about ${name}'s research?`,
  );
});

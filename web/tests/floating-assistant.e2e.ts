import { expect, test } from '@playwright/test';

test('resizes from the top left and keeps saved chat usable', async ({
  page,
}) => {
  const messages: { id: number; role: string; content: string }[] = [];
  const conversations: {
    id: string;
    title: string;
    created_at: string;
    updated_at: string;
    preview?: string;
  }[] = [];
  await page.route('**/api/**', async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname.replace(/^\/api/, '');
    const method = request.method();
    const json = (body: unknown) => route.fulfill({ json: body });
    if (path === '/sessions' && method === 'POST')
      return json({
        session_id: 'a'.repeat(32),
        memory: {
          version: 0,
          shortlisted_person_ids: [],
          rejected_person_ids: [],
          last_query: null,
          last_intent: null,
          last_result_ids: [],
        },
      });
    if (path.endsWith('/memory'))
      return json({
        version: 0,
        shortlisted_person_ids: [],
        rejected_person_ids: [],
        last_query: null,
        last_intent: null,
        last_result_ids: [],
      });
    if (path === '/health')
      return json({
        status: 'ok',
        papers: 200,
        authors: 100,
        model_version: 'test',
        query_provider: 'fallback',
      });
    if (path === '/conversations/status')
      return json({
        provider: 'test',
        model: 'test',
        available: true,
        message: 'Ready',
      });
    if (path === '/conversations' && method === 'GET')
      return json(conversations);
    if (path === '/conversations' && method === 'POST') {
      const item = {
        id: `chat-${conversations.length + 1}`,
        title: `Conversation ${conversations.length + 1}`,
        created_at: '2026-11-07 00:00:00',
        updated_at: '2026-11-07 00:00:00',
      };
      conversations.unshift(item);
      return json(item);
    }
    if (path === '/conversations/chat-1/messages' && method === 'POST') {
      const body = request.postDataJSON();
      messages.push(
        { id: 1, role: 'user', content: body.text },
        { id: 2, role: 'assistant', content: 'A saved answer.' },
      );
      conversations[0].preview = body.text;
      return route.fulfill({
        status: 200,
        contentType: 'application/x-ndjson',
        body: '{"type":"delta","text":"A saved answer."}\n',
      });
    }
    if (/^\/conversations\/chat-\d+$/.test(path) && method === 'GET') {
      const item = conversations.find((conversation) =>
        path.endsWith(conversation.id),
      );
      return json({
        ...item,
        messages: item?.id === 'chat-1' ? messages : [],
        documents: [],
      });
    }
    return route.fulfill({ status: 404, json: { message: 'Not found' } });
  });
  await page.setViewportSize({ width: 1280, height: 1100 });
  await page.goto('/');
  await page.getByRole('button', { name: 'Open AI assistant' }).click();
  const dialog = page.getByRole('dialog', { name: 'AI Assistant' });
  await expect(
    dialog.getByRole('heading', { name: 'Scholar AI assistant' }),
  ).toBeVisible();
  await expect(
    dialog.getByText('Scholar AI assistant', { exact: true }),
  ).toHaveCount(1);
  const handle = dialog.getByRole('button', { name: 'Resize assistant panel' });
  await expect(handle).toBeVisible();
  await page.waitForTimeout(400);
  const before = await dialog.boundingBox();
  const corner = await handle.boundingBox();
  if (!before || !corner) throw new Error('Assistant panel is not visible');
  await page.mouse.move(corner.x + 12, corner.y + 12);
  await page.mouse.down();
  await page.mouse.move(corner.x - 88, corner.y - 48, { steps: 6 });
  await page.mouse.up();
  const after = await dialog.boundingBox();
  if (!after) throw new Error('Assistant panel disappeared');
  expect(after.width).toBeGreaterThan(before.width + 90);
  expect(after.height).toBeGreaterThan(before.height + 50);
  expect(
    Math.abs(after.x + after.width - before.x - before.width),
  ).toBeLessThan(2);
  expect(
    Math.abs(after.y + after.height - before.y - before.height),
  ).toBeLessThan(2);
  await handle.focus();
  await page.keyboard.press('ArrowRight');
  await expect
    .poll(async () => (await dialog.boundingBox())?.width)
    .toBeLessThan(after.width);

  await dialog
    .getByLabel('Message', { exact: true })
    .fill('A research question');
  await dialog.getByRole('button', { name: /^Send/ }).click();
  await expect(dialog.locator('.conversation-message.assistant')).toContainText(
    'A saved answer.',
  );
  await expect(
    dialog.getByRole('button', {
      name: /^(Copy|Regenerate|Helpful|Not helpful)$/,
    }),
  ).toHaveCount(0);
  await expect(
    dialog.getByText('Chats save automatically', { exact: false }),
  ).toBeVisible();
  await dialog.getByRole('button', { name: 'New conversation' }).click();
  await expect(dialog.locator('.conversation-message')).toHaveCount(0);
  await dialog.getByRole('button', { name: 'Saved conversations' }).click();
  await dialog
    .getByRole('button', { name: /Conversation 1/ })
    .first()
    .click();
  await expect(dialog.locator('.conversation-message.assistant')).toContainText(
    'A saved answer.',
  );
  await page.setViewportSize({ width: 390, height: 844 });
  const mobile = await dialog.boundingBox();
  if (!mobile) throw new Error('Assistant panel is not visible on mobile');
  expect(mobile.x).toBeGreaterThanOrEqual(0);
  expect(mobile.x + mobile.width).toBeLessThanOrEqual(390);
  expect(mobile.y).toBeGreaterThanOrEqual(0);
  await expect(
    dialog.getByRole('heading', { name: 'Scholar AI assistant' }),
  ).toBeVisible();
  await expect(
    dialog.getByRole('button', { name: 'Saved conversations' }),
  ).toBeVisible();
});

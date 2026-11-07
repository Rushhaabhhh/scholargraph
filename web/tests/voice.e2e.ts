import { test, expect } from '@playwright/test';

const fixture = process.env.VOICE_TEST_AUDIO;
test.skip(
  !fixture,
  'Set VOICE_TEST_AUDIO to a WAV containing a spoken search command.',
);
test.use({
  launchOptions: {
    executablePath: process.env.CHROMIUM_PATH || undefined,
    args: [
      '--use-fake-device-for-media-stream',
      '--use-fake-ui-for-media-stream',
      `--use-file-for-fake-audio-capture=${fixture}`,
    ],
  },
});

test('continuous conversation can be stopped after a spoken turn', async ({
  page,
}) => {
  test.setTimeout(180000);
  await page.goto('/chat');
  const dialog = page.getByRole('region', { name: 'Conversation' });
  await dialog.getByRole('button', { name: 'Voice', exact: true }).click();
  await expect(dialog.getByLabel('Speech recognition provider')).toContainText(
    'Server · vosk',
  );
  await expect(dialog.getByLabel('Speech recognition provider')).toHaveValue(
    'server',
  );
  let transcriptions = 0;
  page.on('response', (response) => {
    if (response.url().endsWith('/api/voice/transcribe') && response.ok())
      transcriptions++;
  });
  await dialog.getByRole('button', { name: 'Continuous' }).click();
  await expect(
    dialog.locator('.conversation-message.assistant').last(),
  ).toBeVisible({ timeout: 60000 });
  await expect
    .poll(() => transcriptions, { timeout: 120000 })
    .toBeGreaterThanOrEqual(2);
  await dialog.getByRole('button', { name: 'Stop voice conversation' }).click();
  await expect(
    dialog.getByRole('status').filter({ hasText: 'Conversation paused' }),
  ).toBeVisible();
  await expect(
    dialog.getByRole('button', { name: 'Continuous' }),
  ).toHaveAttribute('aria-pressed', 'false');
  await expect(page.getByLabel('Message', { exact: true })).toBeEnabled({
    timeout: 60000,
  });
  await page.getByRole('button', { name: '+ New' }).click();
  await page.getByLabel('Message', { exact: true }).fill('Say hello briefly.');
  await page.getByRole('button', { name: /^Send/ }).click();
  await expect(page.getByRole('button', { name: /^Send/ })).toBeVisible({
    timeout: 60000,
  });
  await expect(
    page.locator('.conversation-message.assistant').last(),
  ).not.toContainText('No response generated.');
});

import { test, expect } from '@playwright/test';
const fixture = process.env.VOICE_TEST_AUDIO;
test.skip(!fixture, 'Set VOICE_TEST_AUDIO to a WAV fixture.');
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
test('voice and text share the independent conversation', async ({ page }) => {
  test.setTimeout(120000);
  await page.goto('/chat');
  await page.getByRole('button', { name: 'Voice', exact: true }).click();
  await expect(page.getByLabel('Speech recognition provider')).toHaveValue(
    'server',
  );
  const spoken = page.waitForResponse(
    (response) => response.url().endsWith('/api/voice/speak') && response.ok(),
  );
  await page.getByRole('button', { name: 'Push to talk' }).click();
  await spoken;
  await expect(page.locator('.conversation-message.user').last()).toContainText(
    /graph neural networks/i,
  );
  await page.getByRole('button', { name: 'Stop voice conversation' }).click();
  await page.getByRole('button', { name: 'Text', exact: true }).click();
  await expect(
    page.locator('.conversation-message.assistant').last(),
  ).toBeVisible();
  const input = page.getByLabel('Message', { exact: true });
  await input.fill('Say hello briefly.');
  await page.getByRole('button', { name: /^Send/ }).click();
  await expect(page.getByRole('button', { name: /^Send/ })).toBeVisible({
    timeout: 90000,
  });
  await expect(page.locator('.conversation-message.user').last()).toContainText(
    'Say hello briefly.',
  );
  await expect(
    page.locator('.conversation-message.assistant').last(),
  ).not.toContainText('No response generated.');
});

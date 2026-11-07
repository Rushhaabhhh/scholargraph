import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import { VoiceConsole } from '../components/VoiceConsole';

const mocks = vi.hoisted(() => ({
  record: vi.fn(),
  recognition: vi.fn(),
  api: vi.fn(),
}));
vi.mock('../lib/api', () => ({ api: mocks.api }));
vi.mock('../lib/voice', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../lib/voice')>()),
  recordAudio: mocks.record,
  recognitionConstructor: mocks.recognition,
}));
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});
beforeEach(() => {
  mocks.api.mockReset().mockResolvedValue({
    stt: { provider: 'vosk', available: true, local: true },
    tts: { provider: 'piper', available: true, local: true },
  });
  mocks.record.mockReset().mockResolvedValue({
    stop: async () => new Blob(['audio'], { type: 'audio/wav' }),
    cancel: vi.fn(),
  });
  mocks.recognition.mockReset().mockReturnValue(class {});
});

it('keeps server recognition selected after an empty recording and gives microphone guidance', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({
      ok: false,
      json: async () => ({ code: 'no_speech', message: 'No speech' }),
    }),
  );
  render(<VoiceConsole session="session" busy={false} onSend={vi.fn()} />);
  await waitFor(() => expect(mocks.api).toHaveBeenCalled());
  fireEvent.click(screen.getByRole('button', { name: 'Push to talk' }));
  fireEvent.click(
    await screen.findByRole('button', { name: 'Finish recording' }),
  );
  expect((await screen.findByRole('alert')).textContent).toContain(
    'microphone',
  );
  expect(screen.getByLabelText('Speech recognition provider')).toHaveProperty(
    'value',
    'server',
  );
});

it('provides an audible voice test and can play the latest answer', async () => {
  const fetcher = vi.fn().mockResolvedValue({
    ok: true,
    blob: async () => new Blob(['audio'], { type: 'audio/wav' }),
  });
  vi.stubGlobal('fetch', fetcher);
  vi.stubGlobal(
    'Audio',
    class {
      onended: (() => void) | null = null;
      onerror: (() => void) | null = null;
      play() {
        queueMicrotask(() => this.onended?.());
        return Promise.resolve();
      }
      pause() {}
    },
  );
  vi.stubGlobal('URL', {
    createObjectURL: vi.fn(() => 'blob:voice'),
    revokeObjectURL: vi.fn(),
  });
  render(
    <VoiceConsole
      session="session"
      busy={false}
      onSend={vi.fn()}
      latestReply="The answer is here."
    />,
  );
  await waitFor(() => expect(mocks.api).toHaveBeenCalled());
  fireEvent.click(screen.getByRole('button', { name: 'Test voice' }));
  await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(1));
  await waitFor(() =>
    expect(
      screen.getByRole('button', { name: 'Play last answer' }),
    ).not.toHaveProperty('disabled', true),
  );
  fireEvent.click(screen.getByRole('button', { name: 'Play last answer' }));
  await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(2));
  expect(JSON.parse(fetcher.mock.calls[1][1].body).text).toBe(
    'The answer is here.',
  );
});

it('sends recognized speech to the assistant and speaks its answer', async () => {
  const fetcher = vi.fn(async (path: string) =>
    path.endsWith('/transcribe')
      ? { ok: true, json: async () => ({ text: 'Explain graph learning' }) }
      : {
          ok: true,
          blob: async () => new Blob(['audio'], { type: 'audio/wav' }),
        },
  );
  vi.stubGlobal('fetch', fetcher);
  vi.stubGlobal(
    'Audio',
    class {
      onended: (() => void) | null = null;
      play() {
        queueMicrotask(() => this.onended?.());
        return Promise.resolve();
      }
      pause() {}
    },
  );
  vi.stubGlobal('URL', {
    createObjectURL: vi.fn(() => 'blob:voice'),
    revokeObjectURL: vi.fn(),
  });
  const send = vi.fn().mockResolvedValue('A spoken answer.');
  render(<VoiceConsole session="session" busy={false} onSend={send} />);
  await waitFor(() => expect(mocks.api).toHaveBeenCalled());
  fireEvent.click(screen.getByRole('button', { name: 'Push to talk' }));
  fireEvent.click(
    await screen.findByRole('button', { name: 'Finish recording' }),
  );
  await waitFor(() =>
    expect(send).toHaveBeenCalledWith(
      'Explain graph learning',
      expect.any(AbortSignal),
    ),
  );
  await waitFor(() =>
    expect(fetcher.mock.calls.some(([url]) => url.endsWith('/speak'))).toBe(
      true,
    ),
  );
  expect(screen.getByText('Explain graph learning')).toBeTruthy();
});

it('speaks each successive voice answer once', async () => {
  let turn = 0;
  const fetcher = vi.fn(async (path: string) =>
    path.endsWith('/transcribe')
      ? { ok: true, json: async () => ({ text: `Question ${++turn}` }) }
      : { ok: true, blob: async () => new Blob(['audio'], { type: 'audio/wav' }) },
  );
  vi.stubGlobal('fetch', fetcher);
  vi.stubGlobal('Audio', class {
    onended: (() => void) | null = null;
    play() { queueMicrotask(() => this.onended?.()); return Promise.resolve(); }
    pause() {}
  });
  vi.stubGlobal('URL', { createObjectURL: vi.fn(() => 'blob:voice'), revokeObjectURL: vi.fn() });
  const send = vi.fn(async (text: string) => `Answer to ${text}`);
  render(<VoiceConsole session="session" busy={false} onSend={send} />);
  await waitFor(() => expect(mocks.api).toHaveBeenCalled());
  for (let n = 1; n <= 2; n++) {
    fireEvent.click(screen.getByRole('button', { name: 'Push to talk' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Finish recording' }));
    await waitFor(() => expect(screen.getByRole('status').textContent).toBe('Response complete'));
  }
  expect(send).toHaveBeenCalledTimes(2);
  const requests = fetcher.mock.calls.filter(([path]) => path.endsWith('/speak'));
  expect(requests).toHaveLength(2);
});

it('does not send or speak a browser recognition result twice', async () => {
  let instance: { onresult: ((event: any) => void) | null; onend: (() => void) | null } | undefined;
  mocks.api.mockResolvedValue({ stt: { provider: 'vosk', available: false, local: true }, tts: { provider: 'piper', available: true, local: true } });
  mocks.recognition.mockReturnValue(class {
    onresult = null; onend = null; onerror = null;
    constructor() { instance = this; }
    start() {} stop() {} abort() {}
  });
  const fetcher = vi.fn().mockResolvedValue({ ok: true, blob: async () => new Blob(['audio']) });
  vi.stubGlobal('fetch', fetcher);
  vi.stubGlobal('Audio', class {
    onended: (() => void) | null = null;
    play() { setTimeout(() => this.onended?.(), 30); return Promise.resolve(); }
    pause() {}
  });
  vi.stubGlobal('URL', { createObjectURL: vi.fn(() => 'blob:voice'), revokeObjectURL: vi.fn() });
  const send = vi.fn().mockResolvedValue('One answer');
  render(<VoiceConsole session="session" busy={false} onSend={send} />);
  await waitFor(() => expect(screen.getByLabelText('Speech recognition provider')).toHaveProperty('value', 'browser'));
  fireEvent.click(screen.getByRole('button', { name: 'Push to talk' }));
  await waitFor(() => expect(instance).toBeDefined());
  instance!.onresult?.({ results: { length: 1, 0: { 0: { transcript: 'Question' }, isFinal: true } } });
  instance!.onend?.();
  await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(1));
  instance!.onend?.();
  await waitFor(() => expect(screen.getByRole('status').textContent).toBe('Response complete'));
  expect(send).toHaveBeenCalledTimes(1);
  expect(fetcher).toHaveBeenCalledTimes(1);
});

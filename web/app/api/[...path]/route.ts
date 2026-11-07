import { NextRequest, NextResponse } from 'next/server';

// The browser talks only to this same-origin boundary. The backend address is
// read at runtime so the same image works locally and inside Compose.
async function forward(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
) {
  const { path } = await context.params;
  const base = process.env.HIRESENSE_API_URL ||
    (process.env.NODE_ENV === 'production' ? '' : 'http://127.0.0.1:8000');
  let backend: URL;
  try {
    backend = new URL(base);
    if (!['http:', 'https:'].includes(backend.protocol) ||
        !['', '/'].includes(backend.pathname) || backend.search || backend.hash ||
        backend.username || backend.password) throw new Error('Invalid backend origin');
  } catch {
    return NextResponse.json(
      { code: 'backend_misconfigured', message: 'Set HIRESENSE_API_URL to the backend origin, without /api or /health.' },
      { status: 503 },
    );
  }
  const upstream = new URL(
    path.map(encodeURIComponent).join('/'),
    backend.origin + '/',
  );
  upstream.search = request.nextUrl.search;
  const quickRequest =
    path[0] === 'health' ||
    (path[0] === 'sessions' &&
      (request.method === 'GET' ||
        (request.method === 'POST' && path.length === 1)));
  const audioUpload = path[0] === 'voice' && path[1] === 'transcribe';
  const documentUpload =
    path[0] === 'conversations' &&
    path[2] === 'documents' &&
    request.method === 'POST';
  if (
    audioUpload &&
    Number(request.headers.get('Content-Length') || 0) > 1_000_000
  )
    return NextResponse.json(
      { code: 'audio_too_large', message: 'Keep recordings under 30 seconds.' },
      { status: 413 },
    );
  if (
    documentUpload &&
    Number(request.headers.get('Content-Length') || 0) > 1_000_000
  )
    return NextResponse.json(
      { code: 'document_too_large', message: 'Documents must be under 1 MB.' },
      { status: 413 },
    );
  try {
    const body =
      request.method === 'GET' || request.method === 'HEAD'
        ? undefined
        : await request.arrayBuffer();
    if (documentUpload && body && body.byteLength > 1_000_000)
      return NextResponse.json(
        {
          code: 'document_too_large',
          message: 'Documents must be under 1 MB.',
        },
        { status: 413 },
      );
    const response = await fetch(upstream, {
      method: request.method,
      headers: {
        'Content-Type':
          request.headers.get('Content-Type') || 'application/json',
        ...(request.headers.get('X-Session-ID')
          ? { 'X-Session-ID': request.headers.get('X-Session-ID')! }
          : {}),
        ...(request.headers.get('X-Document-Name')
          ? { 'X-Document-Name': request.headers.get('X-Document-Name')! }
          : {}),
      },
      body,
      cache: 'no-store',
      // A listening but unresponsive backend must not leave the UI loading forever.
      signal: AbortSignal.any([
        request.signal,
        AbortSignal.timeout(
          quickRequest ? 5000 : path[0] === 'conversations' ? 300000 : 60000,
        ),
      ]),
    });
    if (response.status === 204) return new NextResponse(null, { status: 204 });
    return new NextResponse(response.body, {
      status: response.status,
      headers: {
        'Content-Type':
          response.headers.get('Content-Type') || 'application/json',
        'Cache-Control': 'no-store',
      },
    });
  } catch {
    return NextResponse.json(
      {
        code: 'backend_unavailable',
        message: 'Could not reach the API. Check that the backend is running.',
      },
      { status: 503 },
    );
  }
}
export const GET = forward;
export const POST = forward;
export const PUT = forward;
export const PATCH = forward;
export const DELETE = forward;

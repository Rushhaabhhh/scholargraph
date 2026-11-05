import { NextRequest, NextResponse } from 'next/server';

// The browser talks only to this same-origin boundary. The backend address is
// read at runtime so the same image works locally and inside Compose.
async function forward(request:NextRequest, context:{params:Promise<{path:string[]}>}) {
  const {path} = await context.params;
  const upstream = new URL(path.map(encodeURIComponent).join('/'), `${process.env.HIRESENSE_API_URL || 'http://127.0.0.1:8000'}/`);
  upstream.search = request.nextUrl.search;
  try {
    const response = await fetch(upstream, {
      method:request.method,
      headers:{'Content-Type':'application/json'},
      body:request.method === 'GET' || request.method === 'HEAD' ? undefined : await request.text(),
      cache:'no-store',
      signal:request.signal,
    });
    if (response.status === 204) return new NextResponse(null,{status:204});
    return new NextResponse(await response.text(),{status:response.status,headers:{'Content-Type':response.headers.get('Content-Type') || 'application/json','Cache-Control':'no-store'}});
  } catch {
    return NextResponse.json({code:'backend_unavailable',message:'Could not reach the API. Check that the backend is running.'},{status:503});
  }
}
export const GET=forward;
export const POST=forward;
export const PUT=forward;
export const DELETE=forward;

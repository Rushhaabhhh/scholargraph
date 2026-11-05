export class ApiError extends Error { constructor(message:string, public status:number, public code?:string) { super(message); } }
export async function api<T>(path:string, init:RequestInit = {}):Promise<T> {
  let response:Response;
  try { response = await fetch(`/api${path}`, {...init, headers:{'Content-Type':'application/json', ...init.headers}, cache:'no-store'}); }
  catch (error) { if (error instanceof DOMException && error.name === 'AbortError') throw error; throw new ApiError('Could not reach the API. Check that the backend is running.', 0); }
  if (response.status === 204) return undefined as T;
  if (!response.ok) { const body = await response.json().catch(() => ({})); throw new ApiError(body.message || `Request failed (${response.status}).`, response.status, body.code); }
  return response.json() as Promise<T>;
}
export const requestId = () => globalThis.crypto.randomUUID().replaceAll('-', '');
export const json = (method:string, data:unknown, signal?:AbortSignal):RequestInit => ({method, body:JSON.stringify(data), signal});

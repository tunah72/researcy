const RESPONSE_HEADERS = ['content-type', 'retry-after', 'x-request-id'] as const;
const MAX_REQUEST_BYTES = 16 * 1024;

function errorResponse(status: number, code: string, message: string) {
  return Response.json(
    { code, message, details: null, request_id: crypto.randomUUID() },
    { status },
  );
}

async function readBoundedBody(request: Request): Promise<ArrayBuffer | Response> {
  const declaredLength = request.headers.get('content-length');
  if (declaredLength && Number(declaredLength) > MAX_REQUEST_BYTES) {
    return errorResponse(
      413,
      'REQUEST_TOO_LARGE',
      'The arXiv import request is too large.',
    );
  }

  if (!request.body) return new ArrayBuffer(0);
  const reader = request.body.getReader();
  const chunks: Uint8Array[] = [];
  let received = 0;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    received += value.byteLength;
    if (received > MAX_REQUEST_BYTES) {
      await reader.cancel();
      return errorResponse(
        413,
        'REQUEST_TOO_LARGE',
        'The arXiv import request is too large.',
      );
    }
    chunks.push(value);
  }

  const buffer = new ArrayBuffer(received);
  const body = new Uint8Array(buffer);
  let offset = 0;
  for (const chunk of chunks) {
    body.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return buffer;
}

export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';

export async function POST(request: Request) {
  const apiBase = process.env.API_INTERNAL_URL || 'http://127.0.0.1:8000';
  const body = await readBoundedBody(request);
  if (body instanceof Response) return body;

  const headers = new Headers();
  for (const name of [
    'content-type',
    'cookie',
    'origin',
    'x-csrf-token',
    'idempotency-key',
  ]) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }

  let upstream: Response;
  try {
    upstream = await fetch(`${apiBase}/api/papers/arxiv`, {
      method: 'POST',
      headers,
      body,
      cache: 'no-store',
    });
  } catch {
    return Response.json(
      {
        code: 'UPSTREAM_UNAVAILABLE',
        message: 'The import service is temporarily unavailable.',
        request_id: crypto.randomUUID(),
      },
      { status: 502 }
    );
  }

  const responseHeaders = new Headers();
  for (const name of RESPONSE_HEADERS) {
    const value = upstream.headers.get(name);
    if (value) responseHeaders.set(name, value);
  }
  return new Response(upstream.body, {
    status: upstream.status,
    headers: responseHeaders,
  });
}

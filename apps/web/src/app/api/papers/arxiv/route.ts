const RESPONSE_HEADERS = ['content-type', 'retry-after', 'x-request-id'] as const;

export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';

export async function POST(request: Request) {
  const apiBase = process.env.API_INTERNAL_URL || 'http://127.0.0.1:8000';
  const headers = new Headers(request.headers);
  headers.delete('connection');
  headers.delete('content-length');
  headers.delete('host');

  let upstream: Response;
  try {
    upstream = await fetch(`${apiBase}/api/papers/arxiv`, {
      method: 'POST',
      headers,
      body: await request.arrayBuffer(),
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

// @vitest-environment node

import { afterEach, describe, expect, it, vi } from 'vitest';
import { POST } from './route';

describe('arXiv import proxy', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('rejects an oversized JSON body before contacting the API', async () => {
    const upstream = vi.fn();
    vi.stubGlobal('fetch', upstream);
    const request = new Request('http://localhost:3000/api/papers/arxiv', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ arxiv_id_or_url: 'x'.repeat(20_000) }),
    });

    const response = await POST(request);

    expect(response.status).toBe(413);
    await expect(response.json()).resolves.toMatchObject({
      code: 'REQUEST_TOO_LARGE',
    });
    expect(upstream).not.toHaveBeenCalled();
  });

  it('adds retry-after on network failure to upstream API', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('Connection refused')));
    const request = new Request('http://localhost:3000/api/papers/arxiv', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ arxiv_id_or_url: '1706.03762' }),
    });

    const response = await POST(request);
    expect(response.status).toBe(502);
    expect(response.headers.get('Retry-After')).toBe('60');
    const json = await response.json();
    expect(json.code).toBe('UPSTREAM_UNAVAILABLE');
  });
});

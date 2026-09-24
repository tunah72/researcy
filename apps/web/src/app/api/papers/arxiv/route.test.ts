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
});

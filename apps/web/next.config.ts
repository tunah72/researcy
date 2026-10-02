import type { NextConfig } from 'next';

const nextConfig: NextConfig = {
  reactStrictMode: true,
  experimental: {
    // Preserve the API's 25 MiB PDF limit plus multipart overhead through rewrites.
    proxyClientMaxBodySize: 26 * 1024 * 1024,
    // The finite Reader run lasts 150s; the proxy must not interrupt it at Next's 30s default.
    proxyTimeout: 165_000,
  },
  async rewrites() {
    const apiBase = process.env.API_INTERNAL_URL || 'http://127.0.0.1:8000';
    return [
      {
        source: '/api/:path*',
        destination: `${apiBase}/api/:path*`,
      },
      {
        source: '/auth/:path*',
        destination: `${apiBase}/auth/:path*`,
      },
    ];
  },
};

export default nextConfig;

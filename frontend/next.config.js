/** @type {import('next').NextConfig} */
const nextConfig = {
  // output: 'standalone' is only for Docker — Vercel handles its own build output
  ...(process.env.DOCKER_BUILD === '1' ? { output: 'standalone' } : {}),
  async rewrites() {
    // Proxy /api/* requests to the FastAPI backend.
    // In Docker: INTERNAL_API_URL=http://api:8000
    // In local dev: defaults to http://localhost:8000
    const backendUrl = process.env.INTERNAL_API_URL || process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
    return [
      {
        source: '/api/:path*',
        destination: `${backendUrl}/api/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;

import type { NextConfig } from 'next';

const isProdBuild = process.env.NODE_ENV === 'production';

const nextConfig: NextConfig = {
  // Khi build (npm run build), xuất ra thư mục tĩnh poc/frontend/out/
  ...(isProdBuild ? { output: 'export' } : {}),
  images: {
    unoptimized: true,
  },
  // Khi chạy dev (npm run dev ở localhost:3000), tự proxy /api/v1/* về FastAPI :28080
  ...(!isProdBuild
    ? {
        async rewrites() {
          const backendUrl = process.env.BACKEND_INTERNAL_URL || 'http://127.0.0.1:28080';
          return [
            {
              source: '/api/v1/:path*',
              destination: `${backendUrl}/api/v1/:path*`,
            },
          ];
        },
      }
    : {}),
};

export default nextConfig;

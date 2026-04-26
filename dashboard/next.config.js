/** @type {import('next').NextConfig} */
const nextConfig = {
  // API routes need server, not static export
  // output: 'export' was removed because it disables API routes
  
  images: {
    unoptimized: true
  },
  
  // Allow external hosts in dev mode (for cloudflare tunnel)
  experimental: {
    serverActions: {
      allowedOrigins: ['*']
    }
  },
  
  // Disable strict checks for hostname
  async headers() {
    return [
      {
        source: '/:path*',
        headers: [
          { key: 'Access-Control-Allow-Origin', value: '*' },
          { key: 'Access-Control-Allow-Methods', value: 'GET,POST,OPTIONS' },
          { key: 'Access-Control-Allow-Headers', value: '*' },
        ],
      },
    ];
  },
}

module.exports = nextConfig

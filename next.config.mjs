/** In development the FastAPI backend runs on :8000 (npm run dev starts both).
 *  On Vercel, /api/* is served by the Python function in api/index.py. */
const nextConfig = {
  async rewrites() {
    return process.env.NODE_ENV === "development"
      ? [{ source: "/api/:path*", destination: "http://127.0.0.1:8000/api/:path*" }]
      : [];
  },
};
export default nextConfig;

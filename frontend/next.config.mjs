/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // slice 6: self-contained server.js for the Docker image (compose/k8s)
  output: "standalone",
};

export default nextConfig;

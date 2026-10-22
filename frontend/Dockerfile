# frontend image — multi-stage → next standalone server.js (DESIGN §3, §9)
FROM node:20-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:20-alpine AS build
WORKDIR /app
# Inlined into the client bundle at build time (same-origin deployments pass the
# public origin, e.g. k8s ingress; the default keeps the compose/dev fallback.)
ARG NEXT_PUBLIC_API_URL="http://localhost:8000"
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:20-alpine AS run
WORKDIR /app
ENV NODE_ENV=production \
    PORT=3000 \
    HOSTNAME=0.0.0.0
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static
EXPOSE 3000
CMD ["node", "server.js"]

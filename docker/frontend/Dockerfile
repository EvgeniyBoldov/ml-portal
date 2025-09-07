# --- Build stage ---
FROM node:20-alpine AS build
WORKDIR /app

# Install deps
COPY frontend/package*.json ./
RUN if [ -f package-lock.json ]; then npm ci --no-audit --no-fund; else npm install --no-audit --no-fund; fi

# Copy sources
COPY frontend/ /app/

# Inject Vite env at build-time
ARG VITE_API_URL=http://api:8000
ENV VITE_API_URL=${VITE_API_URL}

# Build production assets
RUN npm run build

# --- Run stage (no reverse proxy) ---
FROM node:20-alpine AS run
WORKDIR /srv

# tiny static server with SPA fallback
RUN npm i -g serve

COPY --from=build /app/dist/ /srv/dist/

EXPOSE 8080
CMD ["serve", "-s", "dist", "-l", "8080"]

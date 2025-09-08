# --- Build stage ---
FROM node:20-alpine AS build
WORKDIR /app

COPY frontend/package*.json ./
RUN if [ -f package-lock.json ]; then npm ci --no-audit --no-fund; else npm install --no-audit --no-fund; fi

COPY frontend/ /app/

# Build-time configuration (no .env usage)
ARG VITE_API_BASE=http://api:8000
ARG VITE_USE_MOCKS=false
ENV VITE_API_BASE=${VITE_API_BASE}
ENV VITE_USE_MOCKS=${VITE_USE_MOCKS}

RUN npm run build

# --- Run stage ---
FROM node:20-alpine AS run
WORKDIR /srv
RUN npm i -g serve
COPY --from=build /app/dist/ /srv/dist/
EXPOSE 8080
CMD ["serve", "-s", "dist", "-l", "8080"]

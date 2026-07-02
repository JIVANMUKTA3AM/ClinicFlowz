# ── Stage 1: build ────────────────────────────────────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .

# As vars VITE_* são substituídas em tempo de build; passadas como ARG pelo docker-compose
ARG VITE_SUPABASE_URL
ARG VITE_SUPABASE_ANON_KEY
ARG VITE_API_URL=""

ENV VITE_SUPABASE_URL=$VITE_SUPABASE_URL \
    VITE_SUPABASE_ANON_KEY=$VITE_SUPABASE_ANON_KEY \
    VITE_API_URL=$VITE_API_URL

RUN npm run build

# ── Stage 2: serve ────────────────────────────────────────────────────────────
FROM nginx:1.27-alpine

ARG BUILD_DATE=unknown
RUN echo "Build: $BUILD_DATE"

COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx-spa.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]

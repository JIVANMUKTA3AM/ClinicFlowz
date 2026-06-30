content = """version: "3.9"

services:

  redis:
    image: redis:7-alpine
    container_name: crm_redis_dev
    restart: unless-stopped
    expose:
      - "6379"
    networks:
      - crm_dev

  api:
    build: .
    container_name: crm_api_dev
    restart: unless-stopped
    env_file: .env
    environment:
      WAHA_URL: http://waha:3000
      WAHA_API_KEY: dev-local-key
      REDIS_URL: redis://redis:6379
      DEBUG: "true"
    volumes:
      - ./app:/app/app
    ports:
      - "8000:8000"
    depends_on:
      redis:
        condition: service_started
    networks:
      - crm_dev

  waha:
    image: devlikeapro/waha:latest
    container_name: crm_waha_dev
    restart: unless-stopped
    environment:
      WAHA_API_KEY: dev-local-key
      WHATSAPP_DEFAULT_ENGINE: NOWEB
      WHATSAPP_HOOK_URL: http://api:8000/api/v1/whatsapp/webhook
      WHATSAPP_HOOK_EVENTS: message,session.status
      WAHA_LOG_LEVEL: debug
      WAHA_LOG_FORMAT: pretty
    volumes:
      - waha_sessions:/app/.sessions
    ports:
      - "3000:3000"
    networks:
      - crm_dev

networks:
  crm_dev:
    driver: bridge

volumes:
  waha_sessions:
"""
open("docker-compose.dev.yml", "w", encoding="utf-8", newline="\n").write(content)
print("OK")

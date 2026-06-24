from pydantic_settings import BaseSettings
from typing import List

class Settings(BaseSettings):
    # App
    APP_NAME: str = "ClinicFlowz"
    DEBUG: bool = False

    # Supabase
    SUPABASE_URL: str
    SUPABASE_SERVICE_KEY: str

    # Anthropic
    ANTHROPIC_API_KEY: str

    # Waha (WhatsApp HTTP API) — opcionais; WhatsApp fica inactivo se não configurados
    WAHA_URL: str = ""       # ex: http://localhost:3000 ou http://IP_VPS:3000
    WAHA_API_KEY: str = ""   # definido em Settings → API de Waha

    # Cifragem de credenciais sensíveis (tokens de integrações)
    # Gerar: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    ENCRYPTION_KEY: str = ""

    # URL pública do backend para o WAHA enviar webhooks.
    # Em produção (VPS):  https://api.suaclínica.pt  ou  https://app.suaclínica.pt/api
    # Em teste local:     http://host.docker.internal:8000  (WAHA em Docker → uvicorn no host)
    # Em dev all-Docker:  http://api:8000  (WAHA e backend na mesma rede Docker)
    BACKEND_WEBHOOK_URL: str = "http://host.docker.internal:8000"

    # CORS
    ALLOWED_ORIGINS: List[str] = ["http://localhost:5173", "https://app.suaagencia.pt"]

    class Config:
        env_file = ".env"

settings = Settings()

from __future__ import annotations

from supabase import create_client, Client
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.core.config import settings

security = HTTPBearer()

_client: Client | None = None


def get_supabase() -> Client:
    """
    Lazy singleton — client is created on first request, not at import time.
    Tests override via dependency_overrides[get_supabase]; the real client
    is never instantiated during test collection.
    """
    global _client
    if _client is None:
        _client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_KEY)
    return _client


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> dict:
    """
    Valida o JWT via Supabase Auth API — compatível com ECC P-256 e HS256.
    Retorna o user object com user_metadata.
    """
    try:
        response = get_supabase().auth.get_user(credentials.credentials)
        if not response or not response.user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido")
        user = response.user
        return {
            "sub": user.id,
            "email": user.email,
            "user_metadata": user.user_metadata or {},
        }
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido ou expirado")


def get_clinica_id(user: dict = Depends(get_current_user)) -> str:
    """Extrai o clinica_id do token — garante isolamento multi-tenant."""
    clinica_id = user.get("user_metadata", {}).get("clinica_id")
    if not clinica_id:
        raise HTTPException(status_code=403, detail="Clínica não associada ao utilizador")
    return clinica_id

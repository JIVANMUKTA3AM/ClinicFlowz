from __future__ import annotations

from supabase import create_client, Client
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.core.config import settings

security = HTTPBearer(auto_error=False)

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
    credentials: HTTPAuthorizationCredentials | None = Depends(security)
) -> dict:
    """
    Valida o JWT via Supabase Auth API — compatível com ECC P-256 e HS256.
    Retorna o user object com user_metadata e app_metadata.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de autenticação em falta",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        response = get_supabase().auth.get_user(credentials.credentials)
        if not response or not response.user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token inválido",
                headers={"WWW-Authenticate": "Bearer"},
            )
        user = response.user
        return {
            "sub": user.id,
            "email": user.email,
            "user_metadata": user.user_metadata or {},
            "app_metadata": user.app_metadata or {},
        }
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido ou expirado",
            headers={"WWW-Authenticate": "Bearer"},
        )


def get_clinica_id(user: dict = Depends(get_current_user)) -> str:
    """Extrai o clinica_id do token — garante isolamento multi-tenant.
    Verifica user_metadata primeiro (onboarding normal), depois app_metadata
    (caso o clinica_id tenha sido definido via admin API noutro campo).
    """
    clinica_id = (
        user.get("user_metadata", {}).get("clinica_id")
        or user.get("app_metadata", {}).get("clinica_id")
    )
    if not clinica_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Clínica não associada ao utilizador. Complete o onboarding.",
        )
    return clinica_id

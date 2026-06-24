"""
app/core/encryption.py — Fernet symmetric encryption for sensitive credentials.

Usage:
    from app.core.encryption import cifrar, decifrar

    ciphertext = cifrar("token_secreto")   # → base64 ciphertext
    plaintext  = decifrar(ciphertext)      # → "token_secreto"

Key management:
    Set ENCRYPTION_KEY in .env (base64 Fernet key, 32 bytes).
    Generate: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

    If the key is absent or malformed the first call to cifrar/decifrar raises
    RuntimeError at boot — never fails silently.

Key rotation:
    Use MultiFernet([new, old]) during a rotation window so existing ciphertexts
    remain decryptable while new ones use the new key.
"""

from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings

# Singleton — created once on first use, never recreated.
_fernet: Fernet | None = None


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is not None:
        return _fernet

    key = settings.ENCRYPTION_KEY
    if not key:
        raise RuntimeError(
            "ENCRYPTION_KEY não está configurada. "
            "Adicione ao .env antes de iniciar o servidor.\n"
            "Gerar: python -c \"from cryptography.fernet import Fernet; "
            "print(Fernet.generate_key().decode())\""
        )
    try:
        _fernet = Fernet(key.encode() if isinstance(key, str) else key)
    except Exception as exc:
        raise RuntimeError(
            f"ENCRYPTION_KEY inválida — verifique o formato (base64 Fernet de 32 bytes): {exc}"
        ) from exc

    return _fernet


def _reset() -> None:
    """Reset singleton — só para testes."""
    global _fernet
    _fernet = None


def cifrar(texto: str) -> str:
    """Cifra texto puro → ciphertext base64 (Fernet AES-128-CBC + HMAC-SHA256)."""
    return _get_fernet().encrypt(texto.encode()).decode()


def decifrar(ciphertext: str) -> str:
    """
    Decifra ciphertext → texto puro.

    Raises ValueError se o token estiver corrompido ou a chave for diferente.
    """
    try:
        return _get_fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:
        raise ValueError(
            "Credencial corrompida ou ENCRYPTION_KEY incorrecta. "
            "Verifique se a chave no .env corresponde à usada quando o valor foi cifrado."
        ) from exc

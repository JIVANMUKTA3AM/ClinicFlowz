from supabase import Client
from datetime import datetime, timezone

def registrar_interacao(db: Client, data: dict) -> dict:
    """
    Serviço central para registrar qualquer interação na timeline do paciente.
    Chamado por: endpoint WhatsApp, endpoint consultas, agente IA, manualmente.
    """
    payload = {
        **data,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    res = db.table("interacoes").insert(payload).execute()
    return res.data[0] if res.data else {}

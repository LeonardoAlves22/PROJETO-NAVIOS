import os
import pytz

try:
    import streamlit as st
    _secrets = st.secrets
except:
    _secrets = {}

def _get(key, default=None):
    try:
        return _secrets[key]
    except:
        return os.environ.get(key, default)

# --- EMAIL ---
EMAIL_USER = "leonardo.alves@wilsonsons.com.br"
EMAIL_PASS = "nlvr vmyv cbcq oexe"
DESTINATARIO = "leonardo.alves@wilsonsons.com.br,operation.sluis@wilsonsons.com.br,operation.belem@wilsonsons.com.br"

# --- FILTROS ---
REMETENTES_VALIDOS = ["operation.sluis", "operation.belem", "agencybrazil"]
TERMOS_PROSPECT = ["PROSPECT", "ARRIVAL", "NOR TENDERED", "BERTHING", "BERTH", "DAILY"]
FILTRO_ASSINATURA = ["BEST REGARDS", "LEONARDO ALVES", "SHIPPING AGENCY", "MOB.:", "WWW.", "HTTP", "WHATSAPP", "WILSON SONS"]

# --- TIMEZONE ---
BR_TZ = pytz.timezone('America/Sao_Paulo')

# --- OPENROUTER (IA) ---
OPENROUTER_API_KEY = _get("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = _get("OPENROUTER_MODEL", "google/gemini-2.5-flash")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

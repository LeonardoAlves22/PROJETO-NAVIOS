import streamlit as st
import imaplib, email, re, smtplib, sqlite3
from email.header import decode_header
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta, timezone

from config import (
    EMAIL_USER, EMAIL_PASS, DESTINATARIO, REMETENTES_VALIDOS,
    TERMOS_PROSPECT, FILTRO_ASSINATURA, BR_TZ,
    OPENROUTER_API_KEY, OPENROUTER_MODEL
)
from ai_analyzer import analyze_prospect_email, detect_appointment, detect_clp

# ============================================================
# 1. PAGE CONFIG & CUSTOM THEME
# ============================================================
st.set_page_config(
    page_title="Monitor WS - Operacional",
    page_icon="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><rect fill='%230a1628' width='100' height='100' rx='12'/><path d='M20 65 L50 30 L80 65 Z' fill='%2300d4aa'/></svg>",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- INJECT CUSTOM CSS ---
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,300;0,9..40,400;0,9..40,500;0,9..40,600;0,9..40,700&family=IBM+Plex+Mono:wght@400;500;600&display=swap');

    /* ---- ROOT VARIABLES ---- */
    :root {
        --navy-900: #060d1a;
        --navy-800: #0a1628;
        --navy-700: #0f2035;
        --navy-600: #152a42;
        --navy-500: #1a3a5c;
        --steel-400: #2a5078;
        --steel-300: #3a6a98;
        --teal-accent: #00d4aa;
        --teal-glow: #00d4aa33;
        --teal-muted: #00a88a;
        --amber-accent: #f0a030;
        --amber-glow: #f0a03033;
        --red-accent: #ff4d6a;
        --red-glow: #ff4d6a22;
        --green-accent: #00e676;
        --green-muted: #00c853;
        --text-primary: #e8edf5;
        --text-secondary: #8a9bbd;
        --text-muted: #5a6a8a;
        --surface-card: #0d1b30;
        --surface-elevated: #101f38;
        --border-subtle: #1a2d4a;
        --font-body: 'DM Sans', sans-serif;
        --font-mono: 'IBM Plex Mono', monospace;
    }

    /* ---- GLOBAL ---- */
    .stApp, [data-testid="stAppViewContainer"] {
        background: linear-gradient(180deg, var(--navy-900) 0%, var(--navy-800) 40%, var(--navy-700) 100%) !important;
        color: var(--text-primary) !important;
        font-family: var(--font-body) !important;
    }

    html, body, [class*="css"] {
        font-family: var(--font-body) !important;
    }

    /* ---- HEADER AREA ---- */
    header[data-testid="stHeader"] {
        background: rgba(6, 13, 26, 0.85) !important;
        backdrop-filter: blur(12px) !important;
        border-bottom: 1px solid var(--border-subtle) !important;
    }

    /* ---- SIDEBAR ---- */
    [data-testid="stSidebar"] {
        background: linear-gradient(195deg, var(--navy-800) 0%, var(--navy-900) 100%) !important;
        border-right: 1px solid var(--border-subtle) !important;
    }

    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p,
    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] span {
        color: var(--text-secondary) !important;
    }

    /* ---- TYPOGRAPHY ---- */
    h1, h2, h3, h4 {
        font-family: var(--font-body) !important;
        color: var(--text-primary) !important;
        font-weight: 600 !important;
        letter-spacing: -0.02em !important;
    }

    p, span, label, div {
        color: var(--text-primary) !important;
    }

    /* ---- BUTTONS ---- */
    .stButton > button {
        font-family: var(--font-body) !important;
        font-weight: 600 !important;
        letter-spacing: 0.04em !important;
        text-transform: uppercase !important;
        font-size: 0.8rem !important;
        border-radius: 6px !important;
        transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1) !important;
        border: 1px solid var(--border-subtle) !important;
    }

    .stButton > button[kind="primary"],
    .stButton > button[data-testid="stBaseButton-primary"] {
        background: linear-gradient(135deg, var(--teal-accent) 0%, var(--teal-muted) 100%) !important;
        color: var(--navy-900) !important;
        border: none !important;
        box-shadow: 0 0 20px var(--teal-glow), 0 4px 12px rgba(0,0,0,0.3) !important;
    }

    .stButton > button[kind="primary"]:hover,
    .stButton > button[data-testid="stBaseButton-primary"]:hover {
        box-shadow: 0 0 30px var(--teal-glow), 0 6px 20px rgba(0,0,0,0.4) !important;
        transform: translateY(-1px) !important;
    }

    .stButton > button[kind="secondary"],
    .stButton > button[data-testid="stBaseButton-secondary"] {
        background: var(--navy-600) !important;
        color: var(--text-primary) !important;
        border: 1px solid var(--steel-400) !important;
    }

    .stButton > button[kind="secondary"]:hover,
    .stButton > button[data-testid="stBaseButton-secondary"]:hover {
        background: var(--navy-500) !important;
        border-color: var(--teal-accent) !important;
    }

    /* ---- TABS ---- */
    .stTabs [data-baseweb="tab-list"] {
        gap: 0px !important;
        background: var(--navy-800) !important;
        border-radius: 8px !important;
        padding: 4px !important;
        border: 1px solid var(--border-subtle) !important;
    }

    .stTabs [data-baseweb="tab"] {
        font-family: var(--font-body) !important;
        font-weight: 600 !important;
        font-size: 0.85rem !important;
        letter-spacing: 0.03em !important;
        color: var(--text-secondary) !important;
        background: transparent !important;
        border-radius: 6px !important;
        padding: 10px 24px !important;
        transition: all 0.2s ease !important;
    }

    .stTabs [data-baseweb="tab"]:hover {
        color: var(--text-primary) !important;
        background: var(--navy-600) !important;
    }

    .stTabs [aria-selected="true"] {
        background: var(--navy-500) !important;
        color: var(--teal-accent) !important;
        border-bottom: none !important;
    }

    .stTabs [data-baseweb="tab-highlight"] {
        display: none !important;
    }

    .stTabs [data-baseweb="tab-border"] {
        display: none !important;
    }

    /* ---- TABLES ---- */
    .stTable, [data-testid="stTable"] {
        border-radius: 8px !important;
        overflow: hidden !important;
    }

    table {
        width: 100% !important;
        border-collapse: separate !important;
        border-spacing: 0 !important;
        font-family: var(--font-body) !important;
        background: var(--surface-card) !important;
        border-radius: 8px !important;
        overflow: hidden !important;
        border: 1px solid var(--border-subtle) !important;
    }

    thead tr th {
        background: var(--navy-600) !important;
        color: var(--text-secondary) !important;
        font-family: var(--font-mono) !important;
        font-size: 0.7rem !important;
        font-weight: 500 !important;
        letter-spacing: 0.08em !important;
        text-transform: uppercase !important;
        padding: 14px 16px !important;
        border-bottom: 2px solid var(--teal-accent) !important;
        white-space: nowrap !important;
    }

    tbody tr td {
        background: var(--surface-card) !important;
        color: var(--text-primary) !important;
        font-family: var(--font-mono) !important;
        font-size: 0.82rem !important;
        padding: 12px 16px !important;
        border-bottom: 1px solid var(--border-subtle) !important;
        white-space: nowrap !important;
    }

    tbody tr:hover td {
        background: var(--surface-elevated) !important;
    }

    tbody tr:last-child td {
        border-bottom: none !important;
    }

    /* ---- STATUS BADGES (used in table cells) ---- */
    /* ---- ALERTS ---- */
    [data-testid="stAlert"] {
        border-radius: 8px !important;
        border: 1px solid var(--border-subtle) !important;
        font-family: var(--font-body) !important;
    }

    /* ---- EXPANDER / STATUS ---- */
    [data-testid="stExpander"],
    [data-testid="stStatus"] {
        background: var(--surface-card) !important;
        border: 1px solid var(--border-subtle) !important;
        border-radius: 8px !important;
    }

    /* ---- CAPTION ---- */
    [data-testid="stCaptionContainer"] p {
        color: var(--text-muted) !important;
        font-family: var(--font-mono) !important;
        font-size: 0.75rem !important;
        letter-spacing: 0.04em !important;
    }

    /* ---- CUSTOM COMPONENTS ---- */
    .ws-header {
        display: flex;
        align-items: center;
        gap: 16px;
        padding: 8px 0 20px 0;
        border-bottom: 1px solid var(--border-subtle);
        margin-bottom: 24px;
    }

    .ws-logo {
        width: 44px;
        height: 44px;
        background: linear-gradient(135deg, var(--teal-accent), var(--teal-muted));
        border-radius: 10px;
        display: flex;
        align-items: center;
        justify-content: center;
        box-shadow: 0 0 20px var(--teal-glow);
        flex-shrink: 0;
    }

    .ws-logo svg {
        width: 24px;
        height: 24px;
    }

    .ws-header-text h1 {
        font-size: 1.5rem !important;
        margin: 0 !important;
        padding: 0 !important;
        line-height: 1.2 !important;
        color: var(--text-primary) !important;
    }

    .ws-header-text p {
        font-size: 0.78rem !important;
        color: var(--text-muted) !important;
        margin: 2px 0 0 0 !important;
        font-family: var(--font-mono) !important;
        letter-spacing: 0.06em !important;
        text-transform: uppercase !important;
    }

    /* Sidebar branding */
    .ws-sidebar-brand {
        padding: 12px 0;
        margin-bottom: 16px;
        border-bottom: 1px solid var(--border-subtle);
    }

    .ws-sidebar-brand h3 {
        font-size: 0.78rem !important;
        color: var(--text-muted) !important;
        font-family: var(--font-mono) !important;
        letter-spacing: 0.1em !important;
        text-transform: uppercase !important;
        margin: 0 0 4px 0 !important;
    }

    .ws-config-item {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 8px 12px;
        background: var(--navy-700);
        border-radius: 6px;
        margin-bottom: 6px;
        border: 1px solid var(--border-subtle);
    }

    .ws-config-label {
        font-size: 0.75rem;
        color: var(--text-secondary);
        font-family: var(--font-mono);
        letter-spacing: 0.04em;
    }

    .ws-config-value {
        font-size: 0.75rem;
        font-family: var(--font-mono);
        font-weight: 600;
    }

    .ws-config-value.active { color: var(--green-accent); }
    .ws-config-value.inactive { color: var(--red-accent); }
    .ws-config-value.info { color: var(--teal-accent); }

    /* Alert banner */
    .ws-alert-banner {
        display: flex;
        align-items: flex-start;
        gap: 12px;
        padding: 14px 18px;
        background: linear-gradient(135deg, rgba(240, 160, 48, 0.08), rgba(240, 160, 48, 0.03));
        border: 1px solid rgba(240, 160, 48, 0.25);
        border-left: 3px solid var(--amber-accent);
        border-radius: 8px;
        margin-bottom: 8px;
    }

    .ws-alert-icon {
        width: 20px;
        height: 20px;
        background: var(--amber-accent);
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        flex-shrink: 0;
        margin-top: 1px;
    }

    .ws-alert-icon svg {
        width: 12px;
        height: 12px;
    }

    .ws-alert-content {
        flex: 1;
    }

    .ws-alert-title {
        font-size: 0.82rem;
        font-weight: 600;
        color: var(--amber-accent);
        margin-bottom: 2px;
    }

    .ws-alert-detail {
        font-size: 0.75rem;
        color: var(--text-secondary);
        font-family: var(--font-mono);
    }

    /* Status bar */
    .ws-status-bar {
        display: flex;
        align-items: center;
        gap: 20px;
        padding: 10px 16px;
        background: var(--surface-card);
        border: 1px solid var(--border-subtle);
        border-radius: 8px;
        margin-bottom: 16px;
    }

    .ws-status-item {
        display: flex;
        align-items: center;
        gap: 6px;
        font-size: 0.75rem;
        font-family: var(--font-mono);
        color: var(--text-secondary);
        letter-spacing: 0.03em;
    }

    .ws-status-dot {
        width: 7px;
        height: 7px;
        border-radius: 50%;
        flex-shrink: 0;
    }

    .ws-status-dot.green {
        background: var(--green-accent);
        box-shadow: 0 0 8px rgba(0, 230, 118, 0.4);
    }

    .ws-status-dot.amber {
        background: var(--amber-accent);
        box-shadow: 0 0 8px rgba(240, 160, 48, 0.4);
    }

    .ws-status-dot.red {
        background: var(--red-accent);
        box-shadow: 0 0 8px rgba(255, 77, 106, 0.3);
    }

    /* Tab section header */
    .ws-tab-header {
        display: flex;
        align-items: center;
        gap: 10px;
        margin-bottom: 12px;
    }

    .ws-port-badge {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 4px 12px;
        background: var(--navy-600);
        border: 1px solid var(--steel-400);
        border-radius: 20px;
        font-family: var(--font-mono);
        font-size: 0.7rem;
        font-weight: 600;
        color: var(--teal-accent);
        letter-spacing: 0.06em;
        text-transform: uppercase;
    }

    .ws-port-badge .dot {
        width: 6px;
        height: 6px;
        border-radius: 50%;
        background: var(--teal-accent);
    }

    .ws-vessel-count {
        font-family: var(--font-mono);
        font-size: 0.72rem;
        color: var(--text-muted);
        letter-spacing: 0.04em;
    }

    /* Scrollbar */
    ::-webkit-scrollbar {
        width: 6px;
        height: 6px;
    }
    ::-webkit-scrollbar-track {
        background: var(--navy-800);
    }
    ::-webkit-scrollbar-thumb {
        background: var(--navy-500);
        border-radius: 3px;
    }
    ::-webkit-scrollbar-thumb:hover {
        background: var(--steel-400);
    }

    /* Divider override */
    hr {
        border-color: var(--border-subtle) !important;
    }

    /* Hide default streamlit branding */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}

    /* Metric cards override */
    [data-testid="stMetric"] {
        background: var(--surface-card) !important;
        border: 1px solid var(--border-subtle) !important;
        border-radius: 8px !important;
        padding: 16px !important;
    }

    [data-testid="stMetricLabel"] p {
        font-family: var(--font-mono) !important;
        font-size: 0.7rem !important;
        text-transform: uppercase !important;
        letter-spacing: 0.08em !important;
        color: var(--text-muted) !important;
    }

    [data-testid="stMetricValue"] {
        font-family: var(--font-body) !important;
        font-weight: 700 !important;
        color: var(--text-primary) !important;
    }
</style>
""", unsafe_allow_html=True)


# ============================================================
# 2. BANCO DE DADOS
# ============================================================
def init_db():
    try:
        conn = sqlite3.connect('monitor_navios.db', check_same_thread=False)
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS navios
                     (nome TEXT PRIMARY KEY, eta TEXT, etb TEXT, etd TEXT, clp TEXT, atualizacao TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS appointments
                     (nome TEXT PRIMARY KEY, porto TEXT, detectado_em TEXT, alertado INTEGER DEFAULT 0)''')
        c.execute('''CREATE TABLE IF NOT EXISTS resultados
                     (navio TEXT, porto TEXT, prospect_am TEXT, prospect_pm TEXT,
                      eta TEXT, etb TEXT, etd TEXT, clp TEXT, atualizacao TEXT,
                      PRIMARY KEY (navio, porto))''')
        conn.commit()
        conn.close()
    except: pass


def ler_banco(nome_id):
    try:
        conn = sqlite3.connect('monitor_navios.db', check_same_thread=False)
        c = conn.cursor()
        c.execute("SELECT eta, etb, etd, clp FROM navios WHERE nome=?", (nome_id,))
        res = c.fetchone()
        conn.close()
        return res if res else ("-", "-", "-", "PENDENTE")
    except: return ("-", "-", "-", "PENDENTE")


def salvar_banco(nome_id, eta, etb, etd, clp):
    try:
        conn = sqlite3.connect('monitor_navios.db', check_same_thread=False)
        c = conn.cursor()
        ex = ler_banco(nome_id)
        eta_f = eta if (eta != "-" and eta is not None) else ex[0]
        etb_f = etb if (etb != "-" and etb is not None) else ex[1]
        etd_f = etd if (etd != "-" and etd is not None) else ex[2]
        c.execute("INSERT OR REPLACE INTO navios VALUES (?,?,?,?,?,?)",
                  (nome_id, eta_f, etb_f, etd_f, clp, datetime.now(BR_TZ).strftime("%H:%M")))
        conn.commit()
        conn.close()
    except: pass


def salvar_appointment(nome, porto):
    try:
        conn = sqlite3.connect('monitor_navios.db', check_same_thread=False)
        c = conn.cursor()
        c.execute("INSERT OR IGNORE INTO appointments VALUES (?,?,?,0)",
                  (nome, porto, datetime.now(BR_TZ).strftime("%d/%m/%Y %H:%M")))
        conn.commit()
        conn.close()
    except: pass


def ler_appointments_pendentes():
    try:
        conn = sqlite3.connect('monitor_navios.db', check_same_thread=False)
        c = conn.cursor()
        c.execute("SELECT nome, porto, detectado_em FROM appointments WHERE alertado=0")
        res = c.fetchall()
        conn.close()
        return res
    except: return []


def confirmar_appointments():
    try:
        conn = sqlite3.connect('monitor_navios.db', check_same_thread=False)
        c = conn.cursor()
        c.execute("UPDATE appointments SET alertado=1 WHERE alertado=0")
        conn.commit()
        conn.close()
    except: pass


def salvar_resultados(dados, porto):
    try:
        conn = sqlite3.connect('monitor_navios.db', check_same_thread=False)
        c = conn.cursor()
        at = datetime.now(BR_TZ).strftime("%H:%M")
        for r in dados:
            c.execute("INSERT OR REPLACE INTO resultados VALUES (?,?,?,?,?,?,?,?,?)",
                      (r["Navio"], porto, r["Prospect AM"], r["Prospect PM"],
                       r["ETA"], r["ETB"], r["ETD"], r["CLP"], at))
        conn.commit()
        conn.close()
    except: pass


def carregar_resultados(porto):
    try:
        conn = sqlite3.connect('monitor_navios.db', check_same_thread=False)
        c = conn.cursor()
        c.execute("SELECT navio, prospect_am, prospect_pm, eta, etb, etd, clp, atualizacao FROM resultados WHERE porto=?", (porto,))
        rows = c.fetchall()
        conn.close()
        if not rows:
            return [], "-"
        dados = []
        at = rows[0][7]
        for r in rows:
            dados.append({
                "Navio": r[0], "Prospect AM": r[1], "Prospect PM": r[2],
                "ETA": r[3], "ETB": r[4], "ETD": r[5], "CLP": r[6]
            })
        return dados, at
    except: return [], "-"


# ============================================================
# 3. FUNCOES AUXILIARES
# ============================================================
def extrair_corpo_email(msg):
    corpo = ""
    try:
        if msg.is_multipart():
            for parte in msg.walk():
                if parte.get_content_type() in ['text/plain', 'text/html']:
                    p = parte.get_payload(decode=True).decode(errors='ignore')
                    corpo += p
        else:
            corpo = msg.get_payload(decode=True).decode(errors='ignore')
    except: pass
    return corpo


def decodificar_assunto(m):
    subj = m.get("Subject", "")
    if not subj: return ""
    decoded = decode_header(subj)
    res = ""
    for part, enc in decoded:
        if isinstance(part, bytes): res += part.decode(enc or 'utf-8', errors='ignore')
        else: res += str(part)
    return res.upper()


def limpar_visual_nome(n):
    n = n.upper()
    porto = re.search(r'(\(.*?\))', n)
    p_str = porto.group(1) if porto else ""
    limpo = re.sub(r'^(MV|M/V|MT|M/T)\s+', '', n)
    limpo = limpo.split(' - ')[0].split(' (')[0].strip()
    return f"{limpo} {p_str}".strip()


def extrair_nome_navio_subject(subj):
    nome = re.sub(r'^(RE|FW|FWD|ENC)\s*:\s*', '', subj, flags=re.IGNORECASE)
    nome = re.sub(r'\b(PROSPECT|NOTICE|BERTHING|DAILY|REPORT|ARRIVAL|UPDATE)\b', '', nome, flags=re.IGNORECASE)
    nome = re.sub(r'-\s*\d+\s*-', ' ', nome)
    nome = nome.split(' - ')[0].strip()
    nome = re.sub(r'\s+', ' ', nome).strip()
    return nome


def extrair_datas_prospect_regex(corpo_sujo, envio):
    res = {"ETA": "-", "ETB": "-", "ETD": "-"}
    txt = re.sub(r'<[^>]+>', ' ', corpo_sujo).upper()
    txt = " ".join(txt.split())
    meses_map = {'JAN':1,'FEB':2,'MAR':3,'APR':4,'MAY':5,'JUN':6,'JUL':7,'AUG':8,'SEP':9,'OCT':10,'NOV':11,'DEC':12}
    hoje = datetime.now(BR_TZ).replace(hour=0, minute=0, second=0, microsecond=0)

    def parse_data(s):
        m_mes = re.search(r'(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)', s)
        m_dia = re.search(r'(\d{1,2})', s)
        if m_mes and m_dia:
            dia, mes = int(m_dia.group(1)), meses_map[m_mes.group(1)]
            dt_encontrada = datetime(envio.year, mes, dia, tzinfo=BR_TZ)
            if dt_encontrada < (hoje - timedelta(days=15)):
                return "-"
            return f"{dia:02d}/{mes:02d}/{envio.year}"
        return "-"

    termos_eta = [
        r"NOTICE OF READINESS\s*[:\-]?\s*([A-Z]{3,}\s+\d{1,2})",
        r"ARRIVAL AT ROADS\s*[:\-]?\s*([A-Z]{3,}\s+\d{1,2})",
        r"ETA AT MOSQUEIRO\s*[:\-]?\s*([A-Z]{3,}\s+\d{1,2})",
        r"ETA AT VILA\s*[:\-]?\s*([A-Z]{3,}\s+\d{1,2})",
        r"ETA\s*[:\-]?\s*([A-Z]{3,}\s+\d{1,2})"
    ]

    for t in termos_eta:
        m = re.search(t, txt)
        if m:
            val = parse_data(m.group(1))
            if val != "-":
                res["ETA"] = val
                break

    for k in ["ETB", "ETD", "ETS"]:
        m = re.search(rf"{k}\s*[:\-]?\s*([A-Z]{{3,}}\s+\d{{1,2}})", txt)
        if m:
            dt = parse_data(m.group(1))
            if dt != "-": res["ETD" if k=="ETS" else k] = dt

    return res


def enviar_relatorio(dados_slz, dados_bel):
    try:
        msg = MIMEMultipart()
        msg['From'] = EMAIL_USER
        msg['To'] = DESTINATARIO
        msg['Subject'] = f"Monitor Operacional WS - {datetime.now(BR_TZ).strftime('%d/%m %H:%M')}"

        def gerar_html(titulo, lista):
            h = f"<h3 style='font-family:Arial; background:#f2f2f2; padding:8px;'>{titulo}</h3>"
            h += "<table border='1' style='border-collapse:collapse; width:100%; font-family:Arial; font-size:12px;'>"
            h += "<tr style='background:#004a99; color:white;'><th>Navio</th><th>Prospect AM</th><th>Prospect PM</th><th>ETA</th><th>ETB</th><th>ETD</th><th>CLP</th></tr>"
            for r in lista:
                c_am = "background:#d4edda;" if r["Prospect AM"] == "OK" else "background:#f8d7da;"
                c_pm = "background:#d4edda;" if r["Prospect PM"] == "OK" else "background:#f8d7da;"
                bg_clp = "#d4edda" if "EMITIDA" in r['CLP'] else ("#fff3cd" if "CRITICO" in r['CLP'] else "#f8d7da")
                h += f"<tr style='text-align:center;'><td>{r['Navio']}</td><td style='{c_am}'>{r['Prospect AM']}</td><td style='{c_pm}'>{r['Prospect PM']}</td><td>{r['ETA']}</td><td>{r['ETB']}</td><td>{r['ETD']}</td><td style='background:{bg_clp};'>{r['CLP']}</td></tr>"
            return h + "</table><br>"

        corpo = f"<html><body>{gerar_html('Sao Luis', dados_slz)}{gerar_html('Belem', dados_bel)}</body></html>"
        msg.attach(MIMEText(corpo, 'html'))
        s = smtplib.SMTP('smtp.gmail.com', 587); s.starttls(); s.login(EMAIL_USER, EMAIL_PASS); s.send_message(msg); s.quit()
        return True
    except: return False


# ============================================================
# 4. STATUS LABEL HELPERS (no emojis)
# ============================================================
def clp_label(status):
    """Return clean text CLP status."""
    if "EMITIDA" in status:
        return "EMITIDA"
    elif "CRITICO" in status or "CRÍTICO" in status:
        return "CRITICO"
    else:
        return "PENDENTE"

def prospect_label(has_it):
    return "OK" if has_it else "--"


# ============================================================
# 5. INTERFACE
# ============================================================
init_db()

# --- Header ---
st.markdown("""
<div class="ws-header">
    <div class="ws-logo">
        <svg viewBox="0 0 24 24" fill="none" stroke="#060d1a" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
            <path d="M2 20 L6 16 L12 10 L18 16 L22 20"/>
            <path d="M4 20 L20 20"/>
            <line x1="12" y1="4" x2="12" y2="10"/>
        </svg>
    </div>
    <div class="ws-header-text">
        <h1>Monitor Operacional</h1>
        <p>Wilson Sons &middot; Controle de Navios</p>
    </div>
</div>
""", unsafe_allow_html=True)

# --- Session state (carregar do banco se disponivel) ---
if 'slz' not in st.session_state:
    slz_saved, at_saved = carregar_resultados("SLZ")
    bel_saved, at_bel = carregar_resultados("BEL")
    st.session_state.slz = slz_saved
    st.session_state.bel = bel_saved
    st.session_state.at = at_saved if slz_saved or bel_saved else "-"
if 'ai_errors' not in st.session_state: st.session_state.ai_errors = 0
if 'new_appointments' not in st.session_state: st.session_state.new_appointments = []

# --- Sidebar ---
with st.sidebar:
    st.markdown("""
    <div class="ws-sidebar-brand">
        <h3>Configuracoes</h3>
    </div>
    """, unsafe_allow_html=True)

    if OPENROUTER_API_KEY:
        st.markdown(f"""
        <div class="ws-config-item">
            <span class="ws-config-label">API Key</span>
            <span class="ws-config-value active">Ativa</span>
        </div>
        <div class="ws-config-item">
            <span class="ws-config-label">Modelo IA</span>
            <span class="ws-config-value info">{OPENROUTER_MODEL.split('/')[-1]}</span>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <div class="ws-config-item">
            <span class="ws-config-label">API Key</span>
            <span class="ws-config-value inactive">Ausente</span>
        </div>
        """, unsafe_allow_html=True)
        st.caption("Configure em .streamlit/secrets.toml")

    st.markdown("<br>", unsafe_allow_html=True)

    # Sidebar stats when data is available
    if st.session_state.at != "-":
        st.markdown(f"""
        <div class="ws-config-item">
            <span class="ws-config-label">Ultima Atualizacao</span>
            <span class="ws-config-value info">{st.session_state.at}</span>
        </div>
        <div class="ws-config-item">
            <span class="ws-config-label">Navios SLZ</span>
            <span class="ws-config-value active">{len(st.session_state.slz)}</span>
        </div>
        <div class="ws-config-item">
            <span class="ws-config-label">Navios BEL</span>
            <span class="ws-config-value active">{len(st.session_state.bel)}</span>
        </div>
        """, unsafe_allow_html=True)
        if st.session_state.ai_errors > 0:
            st.markdown(f"""
            <div class="ws-config-item">
                <span class="ws-config-label">Fallback Regex</span>
                <span class="ws-config-value inactive">{st.session_state.ai_errors}</span>
            </div>
            """, unsafe_allow_html=True)

    # --- Reprocessar navio especifico ---
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("""
    <div class="ws-sidebar-brand">
        <h3>Reprocessar Navio</h3>
    </div>
    """, unsafe_allow_html=True)

    todos_navios = [r["Navio"] for r in st.session_state.slz + st.session_state.bel]
    if todos_navios:
        navio_sel = st.selectbox("Selecione o navio", todos_navios, label_visibility="collapsed")
        if st.button("Reprocessar", use_container_width=True):
            try:
                with st.status("Reprocessando...", expanded=True):
                    mail = imaplib.IMAP4_SSL("imap.gmail.com")
                    mail.login(EMAIL_USER, EMAIL_PASS)
                    agora = datetime.now(BR_TZ)

                    n_id = re.sub(r'^(MV|M/V|MT|M/T)\s+', '', navio_sel.upper()).split(' - ')[0].split(' (')[0].strip()
                    st.write(f"Buscando prospects para {n_id}...")

                    mail.select("PROSPECT", readonly=True)
                    _, d_p = mail.search(None, f'(SINCE "{agora.strftime("%d-%b-%Y")}")')
                    matches = []
                    if d_p[0]:
                        ids_p = d_p[0].split()[-120:]
                        _, headers_data = mail.fetch(b','.join(ids_p), '(BODY[HEADER.FIELDS (SUBJECT DATE)])')
                        ids_match = []
                        for item in headers_data:
                            if isinstance(item, tuple):
                                hdr = email.message_from_bytes(item[1])
                                subj = decodificar_assunto(hdr)
                                if n_id in subj:
                                    seq = re.search(rb'^(\d+)', item[0])
                                    if seq: ids_match.append(seq.group(1))

                        if ids_match:
                            _, full_data = mail.fetch(b','.join(ids_match), '(RFC822)')
                            vistos = set()
                            for item in full_data:
                                if isinstance(item, tuple):
                                    m_msg = email.message_from_bytes(item[1])
                                    subj = decodificar_assunto(m_msg)
                                    envio = email.utils.parsedate_to_datetime(m_msg.get("Date")).astimezone(BR_TZ)
                                    chave = f"{subj}|{envio.strftime('%Y%m%d%H%M')}"
                                    if chave in vistos: continue
                                    vistos.add(chave)
                                    corpo = extrair_corpo_email(m_msg)

                                    st.write(f"IA analisando: {subj[:50]}...")
                                    ship_name = extrair_nome_navio_subject(subj)
                                    datas = analyze_prospect_email(corpo, ship_name)
                                    if datas["ETA"] == "-" and datas["ETB"] == "-" and datas["ETD"] == "-":
                                        datas = extrair_datas_prospect_regex(corpo, envio)
                                    matches.append({"subj": subj, "date": envio, "datas": datas})

                    # CLP
                    mail.select("CLP", readonly=True)
                    _, d_c = mail.search(None, f'(SINCE "{(agora - timedelta(days=30)).strftime("%d-%b-%Y")}")')
                    tem_clp = False
                    if d_c[0]:
                        ids_clp = d_c[0].split()[-60:]
                        _, batch_clp = mail.fetch(b','.join(ids_clp), '(BODY[HEADER.FIELDS (SUBJECT)])')
                        for item in batch_clp:
                            if isinstance(item, tuple):
                                subj = decodificar_assunto(email.message_from_bytes(item[1]))
                                if detect_clp(subj) and n_id in subj:
                                    tem_clp = True
                                    break

                    mail.logout()

                    # Atualizar o navio nas listas
                    matches.sort(key=lambda x: x["date"], reverse=True)
                    p_datas = matches[0]["datas"] if matches else {"ETA":"-","ETB":"-","ETD":"-"}
                    db = ler_banco(navio_sel)
                    eta = p_datas["ETA"] if p_datas["ETA"] != "-" else db[0]
                    etb = p_datas["ETB"] if p_datas["ETB"] != "-" else db[1]
                    etd = p_datas["ETD"] if p_datas["ETD"] != "-" else db[2]

                    if tem_clp:
                        st_clp = "EMITIDA"
                    elif eta != "-" and "/" in eta:
                        try:
                            d, m_d, a = eta.split("/")
                            data_eta = datetime(int(a), int(m_d), int(d), tzinfo=BR_TZ).replace(hour=0,minute=0,second=0,microsecond=0)
                            diff = (data_eta - agora.replace(hour=0,minute=0,second=0,microsecond=0)).days
                            st_clp = "CRITICO" if diff <= 4 else "PENDENTE"
                        except: st_clp = "PENDENTE"
                    else:
                        st_clp = "PENDENTE"

                    salvar_banco(navio_sel, eta, etb, etd, st_clp)
                    today_m = [e for e in matches if e["date"].date() == agora.date()]

                    novo = {
                        "Navio": navio_sel,
                        "Prospect AM": prospect_label(any(e["date"].hour < 13 for e in today_m)),
                        "Prospect PM": prospect_label(any(e["date"].hour >= 13 for e in today_m)),
                        "ETA": eta, "ETB": etb, "ETD": etd,
                        "CLP": clp_label(st_clp)
                    }

                    # Substituir nas listas
                    for lista, porto in [(st.session_state.slz, "SLZ"), (st.session_state.bel, "BEL")]:
                        for i, r in enumerate(lista):
                            if r["Navio"] == navio_sel:
                                lista[i] = novo
                                break

                    salvar_resultados(st.session_state.slz, "SLZ")
                    salvar_resultados(st.session_state.bel, "BEL")
                    st.write(f"Navio {navio_sel} atualizado.")
                    st.rerun()

            except Exception as e:
                st.error(f"Erro: {e}")
    else:
        st.caption("Carregue os dados primeiro.")


# --- Appointment alerts ---
appointments_pendentes = ler_appointments_pendentes()
if appointments_pendentes:
    for nome, porto, detectado in appointments_pendentes:
        st.markdown(f"""
        <div class="ws-alert-banner">
            <div class="ws-alert-icon">
                <svg viewBox="0 0 12 12" fill="none" stroke="#060d1a" stroke-width="2">
                    <line x1="6" y1="2" x2="6" y2="7"/>
                    <circle cx="6" cy="9.5" r="0.5" fill="#060d1a"/>
                </svg>
            </div>
            <div class="ws-alert-content">
                <div class="ws-alert-title">Novo Apontamento: {nome}</div>
                <div class="ws-alert-detail">Porto: {porto} &middot; Detectado: {detectado}</div>
            </div>
        </div>
        """, unsafe_allow_html=True)
    if st.button("Confirmar alertas", use_container_width=False):
        confirmar_appointments()
        st.rerun()

# --- Action buttons ---
c1, c2 = st.columns([1, 3])

with c1:
    if st.button("ATUALIZAR DADOS", use_container_width=True, type="primary"):
        try:
            with st.status("Conectando ao servidor de email...", expanded=True) as status:
                mail = imaplib.IMAP4_SSL("imap.gmail.com")
                mail.login(EMAIL_USER, EMAIL_PASS)
                agora = datetime.now(BR_TZ)
                ai_errors = 0

                # === PASSO 1: Lista de navios ===
                st.write("Buscando lista de navios...")
                mail.select("INBOX", readonly=True)
                _, d_l = mail.search(None, '(SUBJECT "LISTA NAVIOS")')
                slz_raw, bel_raw = [], []
                if d_l[0]:
                    for eid in reversed(d_l[0].split()[-10:]):
                        _, d = mail.fetch(eid, '(RFC822)')
                        corpo_lista = extrair_corpo_email(email.message_from_bytes(d[0][1]))
                        corpo_upper = corpo_lista.upper()
                        if "SLZ" not in corpo_upper and "BELEM" not in corpo_upper:
                            continue
                        linhas = [l.strip() for l in corpo_lista.split('\n') if len(l.strip()) > 1]
                        secao = None
                        for linha in linhas:
                            l_upper = linha.upper()
                            if "SLZ" in l_upper: secao = "SLZ"; continue
                            if "BELEM" in l_upper: secao = "BEL"; continue
                            if any(term in l_upper for term in FILTRO_ASSINATURA): continue
                            if secao == "SLZ" and len(linha) > 3: slz_raw.append(linha)
                            elif secao == "BEL" and len(linha) > 3: bel_raw.append(linha)
                        break

                st.write(f"Encontrados: {len(slz_raw)} navios SLZ, {len(bel_raw)} navios BEL")

                # === PASSO 2: Prospects ===
                st.write("Buscando prospects...")
                mail.select("PROSPECT", readonly=True)
                _, d_p = mail.search(None, f'(SINCE "{agora.strftime("%d-%b-%Y")}")')
                prospy = []
                if d_p[0]:
                    ids_prospect = d_p[0].split()[-120:]

                    _, headers_data = mail.fetch(b','.join(ids_prospect), '(BODY[HEADER.FIELDS (SUBJECT DATE)])')
                    ids_relevantes = []
                    for item in headers_data:
                        if isinstance(item, tuple):
                            hdr = email.message_from_bytes(item[1])
                            subj = decodificar_assunto(hdr)
                            if any(term in subj for term in TERMOS_PROSPECT):
                                seq = re.search(rb'^(\d+)', item[0])
                                if seq: ids_relevantes.append(seq.group(1))

                    st.write(f"Filtrando: {len(ids_relevantes)} prospects relevantes de {len(ids_prospect)} emails")

                    if ids_relevantes:
                        _, full_data = mail.fetch(b','.join(ids_relevantes), '(RFC822)')
                        prospect_emails = []
                        vistos = set()
                        for item in full_data:
                            if isinstance(item, tuple):
                                m = email.message_from_bytes(item[1])
                                subj = decodificar_assunto(m)
                                envio = email.utils.parsedate_to_datetime(m.get("Date")).astimezone(BR_TZ)
                                chave = f"{subj}|{envio.strftime('%Y%m%d%H%M')}"
                                if chave in vistos:
                                    continue
                                vistos.add(chave)
                                corpo = extrair_corpo_email(m)
                                prospect_emails.append({"subj": subj, "date": envio, "corpo": corpo})

                        use_ai = bool(OPENROUTER_API_KEY)
                        total = len(prospect_emails)
                        for i, pe in enumerate(prospect_emails):
                            if use_ai:
                                st.write(f"IA analisando [{i+1}/{total}]: {pe['subj'][:50]}...")
                                ship_name = extrair_nome_navio_subject(pe["subj"])
                                datas = analyze_prospect_email(pe["corpo"], ship_name)
                                if datas["ETA"] == "-" and datas["ETB"] == "-" and datas["ETD"] == "-":
                                    datas = extrair_datas_prospect_regex(pe["corpo"], pe["date"])
                                    ai_errors += 1
                            else:
                                datas = extrair_datas_prospect_regex(pe["corpo"], pe["date"])

                            prospy.append({"subj": pe["subj"], "date": pe["date"], "datas": datas})

                # === PASSO 3: CLP ===
                st.write("Verificando CLPs...")
                mail.select("CLP", readonly=True)
                _, d_c = mail.search(None, f'(SINCE "{(agora - timedelta(days=30)).strftime("%d-%b-%Y")}")')
                clps_list = []
                if d_c[0]:
                    ids_clp = d_c[0].split()[-60:]
                    _, batch_clp = mail.fetch(b','.join(ids_clp), '(BODY[HEADER.FIELDS (SUBJECT)])')
                    for item in batch_clp:
                        if isinstance(item, tuple):
                            subj = decodificar_assunto(email.message_from_bytes(item[1]))
                            if detect_clp(subj):
                                clps_list.append(subj)

                # === PASSO 4: Appointments ===
                st.write("Buscando novos apontamentos...")
                mail.select("INBOX", readonly=True)
                _, d_appt = mail.search(None, f'(SINCE "{(agora - timedelta(days=7)).strftime("%d-%b-%Y")}")')
                new_appts = []
                if d_appt[0] and OPENROUTER_API_KEY:
                    appt_ids = d_appt[0].split()[-50:]
                    _, appt_headers = mail.fetch(b','.join(appt_ids), '(BODY[HEADER.FIELDS (SUBJECT)])')

                    appt_terms = ["APPOINTMENT", "NOMINATION", "APONTAMENTO", "NOMEACAO", "NOMEACAO"]
                    ids_appt_relevantes = []
                    for item in appt_headers:
                        if isinstance(item, tuple):
                            subj = decodificar_assunto(email.message_from_bytes(item[1]))
                            if any(term in subj for term in appt_terms):
                                seq = re.search(rb'^(\d+)', item[0])
                                if seq: ids_appt_relevantes.append(seq.group(1))

                    if ids_appt_relevantes:
                        _, appt_full = mail.fetch(b','.join(ids_appt_relevantes), '(RFC822)')
                        for item in appt_full:
                            if isinstance(item, tuple):
                                m = email.message_from_bytes(item[1])
                                subj = decodificar_assunto(m)
                                corpo = extrair_corpo_email(m)
                                result = detect_appointment(subj, corpo)
                                if result:
                                    salvar_appointment(result["ship_name"], result["port"])
                                    new_appts.append(result)

                mail.logout()

                # === PASSO 5: Processar dados ===
                st.write("Processando dados...")

                def processar(lista, belem=False):
                    res = []
                    for n in lista:
                        n_id = re.sub(r'^(MV|M/V|MT|M/T)\s+', '', n.upper()).split(' - ')[0].split(' (')[0].strip()
                        matches = [e for e in prospy if n_id in e["subj"]]
                        matches.sort(key=lambda x: x["date"], reverse=True)

                        p_datas = matches[0]["datas"] if matches else {"ETA":"-","ETB":"-","ETD":"-"}
                        db = ler_banco(n)

                        eta = p_datas["ETA"] if p_datas["ETA"] != "-" else db[0]
                        etb = p_datas["ETB"] if p_datas["ETB"] != "-" else db[1]
                        etd = p_datas["ETD"] if p_datas["ETD"] != "-" else db[2]

                        tem_clp = any(n_id in s for s in clps_list)
                        if tem_clp:
                            st_clp = "EMITIDA"
                        elif eta != "-" and "/" in eta:
                            try:
                                d, m, a = eta.split("/")
                                data_eta = datetime(int(a), int(m), int(d), tzinfo=BR_TZ).replace(hour=0, minute=0, second=0, microsecond=0)
                                data_hoje = agora.replace(hour=0, minute=0, second=0, microsecond=0)
                                diff = (data_eta - data_hoje).days
                                st_clp = "CRITICO" if diff <= 4 else "PENDENTE"
                            except:
                                st_clp = "PENDENTE"
                        else:
                            st_clp = "PENDENTE"

                        salvar_banco(n, eta, etb, etd, st_clp)
                        today_m = [e for e in matches if e["date"].date() == agora.date()]
                        res.append({
                            "Navio": limpar_visual_nome(n) if belem else n,
                            "Prospect AM": prospect_label(any(e["date"].hour < 13 for e in today_m)),
                            "Prospect PM": prospect_label(any(e["date"].hour >= 13 for e in today_m)),
                            "ETA": eta, "ETB": etb, "ETD": etd,
                            "CLP": clp_label(st_clp)
                        })
                    return res

                st.session_state.slz = processar(slz_raw, False)
                st.session_state.bel = processar(bel_raw, True)
                st.session_state.at = agora.strftime("%H:%M")
                st.session_state.ai_errors = ai_errors
                st.session_state.new_appointments = new_appts

                # Salvar resultados no banco
                salvar_resultados(st.session_state.slz, "SLZ")
                salvar_resultados(st.session_state.bel, "BEL")

                if ai_errors > 0:
                    st.write(f"Atencao: {ai_errors} analises usaram fallback regex")
                st.write("Atualizacao completa.")

                st.rerun()

        except Exception as e: st.error(f"Erro: {e}")

# --- Status bar ---
if st.session_state.at != "-":
    total_navios = len(st.session_state.slz) + len(st.session_state.bel)
    clp_pendentes = sum(1 for r in st.session_state.slz + st.session_state.bel if r["CLP"] == "PENDENTE")
    clp_criticos = sum(1 for r in st.session_state.slz + st.session_state.bel if r["CLP"] == "CRITICO")

    dot_class = "green" if clp_criticos == 0 else ("red" if clp_criticos > 2 else "amber")

    st.markdown(f"""
    <div class="ws-status-bar">
        <div class="ws-status-item">
            <div class="ws-status-dot green"></div>
            Atualizado as {st.session_state.at}
        </div>
        <div class="ws-status-item">
            <div class="ws-status-dot {dot_class}"></div>
            {total_navios} navios &middot; {clp_criticos} criticos &middot; {clp_pendentes} pendentes
        </div>
    </div>
    """, unsafe_allow_html=True)

# --- Data tables ---
if st.session_state.at != "-":
    t1, t2 = st.tabs(["Sao Luis", "Belem"])

    with t1:
        st.markdown(f"""
        <div class="ws-tab-header">
            <span class="ws-port-badge"><span class="dot"></span>SLZ</span>
            <span class="ws-vessel-count">{len(st.session_state.slz)} embarcacoes</span>
        </div>
        """, unsafe_allow_html=True)
        if st.session_state.slz:
            st.table(st.session_state.slz)
        else:
            st.caption("Nenhum navio registrado para este porto.")

    with t2:
        st.markdown(f"""
        <div class="ws-tab-header">
            <span class="ws-port-badge"><span class="dot"></span>BEL</span>
            <span class="ws-vessel-count">{len(st.session_state.bel)} embarcacoes</span>
        </div>
        """, unsafe_allow_html=True)
        if st.session_state.bel:
            st.table(st.session_state.bel)
        else:
            st.caption("Nenhum navio registrado para este porto.")
else:
    st.markdown("""
    <div style="text-align:center; padding: 80px 20px;">
        <div style="width:64px; height:64px; margin:0 auto 20px auto; background:var(--navy-600); border-radius:16px; display:flex; align-items:center; justify-content:center; border: 1px solid var(--border-subtle);">
            <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="var(--text-muted)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                <path d="M2 20 L6 16 L12 10 L18 16 L22 20"/>
                <path d="M4 20 L20 20"/>
                <line x1="12" y1="4" x2="12" y2="10"/>
            </svg>
        </div>
        <p style="font-size:1rem; color:var(--text-secondary); margin-bottom:4px; font-weight:500;">Nenhum dado carregado</p>
        <p style="font-size:0.8rem; color:var(--text-muted); font-family:var(--font-mono);">Clique em ATUALIZAR DADOS para iniciar</p>
    </div>
    """, unsafe_allow_html=True)

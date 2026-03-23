import streamlit as st
import imaplib, email, re, smtplib, sqlite3
from email.header import decode_header
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from streamlit_autorefresh import st_autorefresh
import pytz

# --- CONFIGURAÇÕES ---
EMAIL_USER = "leonardo.alves@wilsonsons.com.br"
EMAIL_PASS = "nlvr vmyv cbcq oexe"
DESTINATARIO = "leonardo.alves@wilsonsons.com.br"
LABEL_PROSPECT = "PROSPECT"
LABEL_CLP = "CLP" # Seu novo marcador
BR_TZ = pytz.timezone('America/Sao_Paulo')

st_autorefresh(interval=300000, key="auto_refresh")

# --- BANCO DE DADOS ---

def init_db():
    conn = sqlite3.connect('monitor_navios.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS navios 
                 (nome TEXT PRIMARY KEY, eta TEXT, etb TEXT, etd TEXT, clp TEXT, ultima_atualizacao TEXT)''')
    conn.commit()
    conn.close()

def salvar_no_banco(nome, eta, etb, etd, clp):
    conn = sqlite3.connect('monitor_navios.db')
    c = conn.cursor()
    c.execute("SELECT eta, etb, etd, clp FROM navios WHERE nome=?", (nome,))
    existente = c.fetchone()
    if existente:
        eta = eta if eta != "-" else existente[0]
        etb = etb if etb != "-" else existente[1]
        etd = etd if etd != "-" else existente[2]
        clp = clp if clp != "-" else existente[3]
    c.execute('''INSERT OR REPLACE INTO navios (nome, eta, etb, etd, clp, ultima_atualizacao)
                 VALUES (?, ?, ?, ?, ?, ?)''', (nome, eta, etb, etd, clp, datetime.now(BR_TZ).strftime("%d/%m %H:%M")))
    conn.commit()
    conn.close()

def ler_do_banco(nome):
    conn = sqlite3.connect('monitor_navios.db')
    c = conn.cursor()
    c.execute("SELECT eta, etb, etd, clp FROM navios WHERE nome=?", (nome,))
    res = c.fetchone()
    conn.close()
    return res if res else ("-", "-", "-", "-")

# --- FUNÇÕES DE APOIO ---

def limpar_html(html):
    texto = re.sub(r'<[^>]+>', ' ', html)
    return " ".join(texto.split())

def extrair_datas_prospect(corpo, data_email):
    res = {"ETA": "-", "ETB": "-", "ETD": "-"}
    if not corpo: return res
    txt = corpo.upper().split("LINEUP DETAILS")[0]
    # ... (lógica de extração de datas permanece a mesma das versões anteriores)
    for k in ["ETB", "ETD", "ETS"]:
        m = re.search(rf"{k}\s+.*?([A-Z]{{3,}}\s+\d{{1,2}}(?:ST|ND|RD|TH)?)", txt)
        if m:
            dia_m = re.search(r'(\d{1,2})', m.group(1))
            mes_m = re.search(r'(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)', m.group(1).upper())
            if dia_m and mes_m:
                res["ETD" if k == "ETS" else k] = f"{int(dia_m.group(1)):02d}/{mes_m.group(1)}"
    for g in ["ARRIVAL AT ROADS", "NOTICE OF READINESS", "ETA"]:
        m = re.search(rf"{g}\s+.*?([A-Z]{{3,}}\s+\d{{1,2}}(?:ST|ND|RD|TH)?)", txt)
        if m:
            dia_m = re.search(r'(\d{1,2})', m.group(1))
            mes_m = re.search(r'(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)', m.group(1).upper())
            if dia_m and mes_m:
                res["ETA"] = f"{int(dia_m.group(1)):02d}/{mes_m.group(1)}"
                break
    return res

# --- MOTOR DE BUSCA ---

def buscar_dados():
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com", timeout=25)
        mail.login(EMAIL_USER, EMAIL_PASS)
        
        # 1. LISTA NAVIOS
        mail.select("INBOX", readonly=True)
        _, data_lista = mail.search(None, '(SUBJECT "LISTA NAVIOS")')
        slz_bruto, bel_bruto = [], []
        if data_lista[0]:
            eid = data_lista[0].split()[-1]
            _, d = mail.fetch(eid, '(RFC822)')
            msg = email.message_from_bytes(d[0][1])
            # Extração de corpo simplificada para o exemplo
            corpo_l = limpar_html(msg.get_payload(decode=True).decode(errors="ignore")) if not msg.is_multipart() else ""
            partes = re.split(r'BELEM:', corpo_l, flags=re.IGNORECASE)
            slz_bruto = [l.strip() for l in partes[0].replace('SLZ:', '').split('\n') if 3 < len(l.strip()) < 60]
            if len(partes) > 1: bel_bruto = [l.strip() for l in partes[1].split('\n') if 3 < len(l.strip()) < 60]

        # 2. PROSPECTS
        mail.select(f'"{LABEL_PROSPECT}"', readonly=True)
        hoje_str = datetime.now(BR_TZ).strftime("%d-%b-%Y")
        _, data_p = mail.search(None, f'(SINCE "{hoje_str}")')
        prospects_list = []
        if data_p[0]:
            for eid in data_p[0].split()[-40:]:
                _, d = mail.fetch(eid, '(RFC822)')
                m = email.message_from_bytes(d[0][1])
                subj = "".join(str(c.decode(ch or 'utf-8') if isinstance(c, bytes) else c) for c, ch in decode_header(m.get("Subject", ""))).upper()
                prospects_list.append({"subj": subj, "date": email.utils.parsedate_to_datetime(m.get("Date")).astimezone(BR_TZ), "datas": extrair_datas_prospect("", email.utils.parsedate_to_datetime(m.get("Date")))})

        # 3. CLP (BUSCA NO MARCADOR NOVO)
        mail.select(f'"{LABEL_CLP}"', readonly=True)
        _, data_clp = mail.search(None, "ALL")
        clp_subjects = []
        if data_clp[0]:
            for eid in data_clp[0].split()[-50:]:
                _, d = mail.fetch(eid, '(BODY[HEADER.FIELDS (SUBJECT)])')
                msg_c = email.message_from_bytes(d[0][1])
                subj_c = "".join(str(c.decode(ch or 'utf-8') if isinstance(c, bytes) else c) for c, ch in decode_header(msg_c.get("Subject", ""))).upper()
                clp_subjects.append(subj_c)

        mail.logout()
        return slz_bruto, bel_bruto, prospects_list, clp_subjects
    except Exception as e: return None, None, str(e), []

# --- UI ---
st.set_page_config(page_title="Monitor WS", layout="wide")
init_db()

st.title("🚢 Monitor Operacional Wilson Sons")

if 'dados' not in st.session_state: st.session_state.dados = {"slz": [], "bel": [], "at": "-"}

if st.button("🔄 ATUALIZAR AGORA", use_container_width=True, type="primary"):
    with st.spinner("Sincronizando Prospects e CLP..."):
        slz, bel, prospects, clps = buscar_dados()
        if slz is not None:
            def montar(lista, p_filtro=None):
                res = []
                hoje = datetime.now(BR_TZ)
                for n_bruto in lista:
                    nome = re.sub(r'^(MV|M/V|MT|M/T)\s+', '', n_bruto.strip(), flags=re.IGNORECASE).split(' - ')[0].split(' (')[0].strip().upper()
                    match = [e for e in prospects if nome in e["subj"]]
                    match.sort(key=lambda x: x["date"], reverse=True)
                    
                    # Lógica CLP
                    possui_clp = any(nome in s for s in clps)
                    info_db = ler_do_banco(nome)
                    
                    # Datas (Prioriza hoje, senão pega banco)
                    eta_val = match[0]["datas"]["ETA"] if match else info_db[0]
                    
                    # Cálculo de Alerta Crítico (4 dias antes)
                    status_clp = "✅ EMITIDA" if possui_clp else "❌ PENDENTE"
                    if not possui_clp and eta_val != "-":
                        try:
                            # Tenta calcular se falta menos de 4 dias
                            dia, mes = eta_val.split("/")
                            data_eta = datetime(hoje.year, int(mes), int(dia), tzinfo=BR_TZ)
                            if (data_eta - hoje).days <= 4: status_clp = "⚠️ CRÍTICO"
                        except: pass
                    
                    salvar_no_banco(nome, eta_val, info_db[1], info_db[2], status_clp)
                    res.append({"Navio": n_bruto, "AM": "✅" if any(e["date"].hour < 13 for e in match) else "❌", "PM": "✅" if any(e["date"].hour >= 13 for e in match) else "❌", "ETA": eta_val, "ETB": info_db[1], "ETD": info_db[2], "CLP": status_clp})
                return res
            st.session_state.dados = {"slz": montar(slz), "bel": montar(bel, "BELEM"), "at": hoje.strftime("%H:%M")}

if st.session_state.dados["at"] != "-":
    t1, t2 = st.tabs(["📍 São Luís", "📍 Belém"])
    with t1: st.table(st.session_state.dados["slz"])
    with t2: st.table(st.session_state.dados["bel"])

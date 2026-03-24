import streamlit as st
import imaplib, email, re, smtplib, sqlite3
from email.header import decode_header
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
import pytz
import time

# 1. Configuração da Página
st.set_page_config(page_title="Monitor WS", layout="wide")
BR_TZ = pytz.timezone('America/Sao_Paulo')

# --- CONFIGURAÇÕES ---
EMAIL_USER = "leonardo.alves@wilsonsons.com.br"
EMAIL_PASS = "nlvr vmyv cbcq oexe"
DESTINATARIO = "leonardo.alves@wilsonsons.com.br"
TERMOS_PROSPECT = ["PROSPECT", "ARRIVAL", "NOR TENDERED", "BERTHING", "BERTH", "DAILY"]

# --- BANCO DE DADOS ---
def init_db():
    try:
        conn = sqlite3.connect('monitor_navios.db', check_same_thread=False)
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS navios 
                     (nome TEXT PRIMARY KEY, eta TEXT, etb TEXT, etd TEXT, clp TEXT, atualizacao TEXT)''')
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
        return res if res else ("-", "-", "-", "❌ PENDENTE")
    except: return ("-", "-", "-", "❌ PENDENTE")

def salvar_banco(nome_id, eta, etb, etd, clp):
    try:
        conn = sqlite3.connect('monitor_navios.db', check_same_thread=False)
        c = conn.cursor()
        ex = ler_banco(nome_id)
        eta_f = eta if (eta != "-" and eta) else ex[0]
        etb_f = etb if (etb != "-" and etb) else ex[1]
        etd_f = etd if (etd != "-" and etd) else ex[2]
        c.execute("INSERT OR REPLACE INTO navios VALUES (?,?,?,?,?,?)", 
                  (nome_id, eta_f, etb_f, etd_f, clp, datetime.now(BR_TZ).strftime("%H:%M")))
        conn.commit()
        conn.close()
    except: pass

# --- APOIO ---
def decodificar_texto(payload):
    if not payload: return ""
    return payload.decode(errors='ignore') if isinstance(payload, bytes) else str(payload)

def decodificar_assunto(m):
    subj = m.get("Subject", "")
    if not subj: return ""
    decoded = decode_header(subj)
    res = ""
    for part, enc in decoded:
        if isinstance(part, bytes): res += part.decode(enc or 'utf-8', errors='ignore')
        else: res += str(part)
    return res.upper()

def extrair_datas_prospect(texto, envio):
    res = {"ETA": "-", "ETB": "-", "ETD": "-"}
    txt = " ".join(texto.upper().split())
    meses_map = {'JAN':1,'FEB':2,'MAR':3,'APR':4,'MAY':5,'JUN':6,'JUL':7,'AUG':8,'SEP':9,'OCT':10,'NOV':11,'DEC':12}
    
    def parse_data(s):
        m_mes = re.search(r'(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)', s)
        m_dia = re.search(r'(\d{1,2})', s)
        if m_mes and m_dia:
            return f"{int(m_dia.group(1)):02d}/{meses_map[m_mes.group(1)]:02d}/{envio.year}"
        return "-"

    m_eta = re.search(r"(NOTICE OF READINESS|ARRIVAL AT ROADS|ETA)\s*[:\-]?\s*([A-Z]{3,}\s+\d{1,2})", txt)
    if m_eta: res["ETA"] = parse_data(m_eta.group(2))
    
    for k in ["ETB", "ETD", "ETS"]:
        m = re.search(rf"{k}\s*[:\-]?\s*([A-Z]{{3,}}\s+\d{{1,2}})", txt)
        if m: res["ETD" if k=="ETS" else k] = parse_data(m.group(1))
    return res

# --- INTERFACE ---
st.title("🚢 Monitor Operacional Wilson Sons")
init_db()

if 'slz' not in st.session_state: st.session_state.slz, st.session_state.bel, st.session_state.at = [], [], "-"

if st.button("🔄 ATUALIZAR AGORA", use_container_width=True, type="primary"):
    try:
        progresso = st.progress(0)
        status_msg = st.empty()

        with st.status("Iniciando Sincronização...", expanded=True) as status:
            mail = imaplib.IMAP4_SSL("imap.gmail.com")
            mail.login(EMAIL_USER, EMAIL_PASS)
            agora = datetime.now(BR_TZ)
            hoje_br = agora.date()
            progresso.progress(10)

            # 1. LISTA NAVIOS (Inbox)
            status_msg.info("Buscando Lista de Navios...")
            mail.select("INBOX", readonly=True)
            _, d_l = mail.search(None, '(SUBJECT "LISTA NAVIOS")')
            slz_raw, bel_raw = [], []
            if d_l[0]:
                _, d = mail.fetch(d_l[0].split()[-1], '(BODY.PEEK[TEXT])')
                corpo = decodificar_texto(d[0][1])
                secao = None
                for linha in corpo.split('\n'):
                    l = linha.strip().upper()
                    if "SLZ" in l: secao = "SLZ"; continue
                    if "BELEM" in l: secao = "BEL"; continue
                    if secao and len(l) > 3:
                        if secao == "SLZ": slz_raw.append(linha.strip())
                        else: bel_raw.append(linha.strip())
            progresso.progress(25)

            # 2. PROSPECTS (LIMITADO RIGOROSAMENTE A 40)
            mail.select("PROSPECT", readonly=True)
            _, d_p = mail.search(None, "ALL")
            prospy = []
            if d_p[0]:
                # CORTE RIGOROSO: Apenas os últimos 40 IDs
                lista_ids = d_p[0].split()[-40:]
                total = len(lista_ids)
                for i, eid in enumerate(lista_ids):
                    status_msg.info(f"Lendo Prospect {i+1} de {total}...")
                    progresso.progress(25 + int((i/total)*40))
                    
                    _, d = mail.fetch(eid, '(BODY.PEEK[HEADER.FIELDS (Subject Date)] BODY.PEEK[TEXT])')
                    head = email.message_from_bytes(d[0][1])
                    body = decodificar_texto(d[1][1])
                    subj = decodificar_assunto(head)
                    
                    if any(term in subj for term in TERMOS_PROSPECT):
                        envio = email.utils.parsedate_to_datetime(head.get("Date")).astimezone(BR_TZ)
                        if envio.date() >= (hoje_br - timedelta(days=1)):
                            prospy.append({"subj": subj, "date": envio, "datas": extrair_datas_prospect(body, envio)})
            progresso.progress(65)

            # 3. CLP (LIMITADO RIGOROSAMENTE A 40)
            status_msg.info("Verificando Marcador CLP...")
            mail.select("CLP", readonly=True)
            _, d_c = mail.search(None, "ALL")
            clps_hoje = []
            if d_c[0]:
                lista_ids_c = d_c[0].split()[-40:]
                total_c = len(lista_ids_c)
                for i, e in enumerate(lista_ids_c):
                    status_msg.info(f"Checando CLP {i+1} de {total_c}...")
                    progresso.progress(65 + int((i/total_c)*25))
                    _, d = mail.fetch(e, '(BODY.PEEK[HEADER.FIELDS (Subject)])')
                    clps_hoje.append(decodificar_assunto(email.message_from_bytes(d[0][1])))
            
            mail.logout()
            progresso.progress(90)

            # 4. PROCESSAMENTO FINAL
            def processar(lista, belem=False):
                res = []
                for n in lista:
                    n_id = re.sub(r'^(MV|M/V|MT|M/T)\s+', '', n.upper()).split(' - ')[0].strip()
                    matches = sorted([e for e in prospy if n_id in e["subj"]], key=lambda x: x["date"], reverse=True)
                    p_datas = matches[0]["datas"] if matches else {"ETA":"-","ETB":"-","ETD":"-"}
                    db = ler_banco(n)
                    eta = p_datas["ETA"] if p_datas["ETA"] != "-" else db[0]
                    etb = p_datas["ETB"] if p_datas["ETB"] != "-" else db[1]
                    etd = p_datas["ETD"] if p_datas["ETD"] != "-" else db[2]
                    
                    st_clp = "✅ EMITIDA" if any(n_id in s for s in clps_hoje) else db[3]
                    if st_clp != "✅ EMITIDA" and eta != "-" and "/" in eta:
                        try:
                            d,m,a = eta.split("/")
                            diff = (datetime(int(a),int(m),int(d)).date() - hoje_br).days
                            if diff <= 4: st_clp = "⚠️ CRÍTICO"
                        except: pass
                    
                    salvar_banco(n, eta, etb, etd, st_clp)
                    res.append({"Navio": n_id if belem else n, "Prospect Manhã": "✅" if any(e["date"].hour < 13 and e["date"].date() == hoje_br for e in matches) else "❌", "Prospect Tarde": "✅" if any(e["date"].hour >= 13 and e["date"].date() == hoje_br for e in matches) else "❌", "ETA": eta, "ETB": etb, "ETD": etd, "CLP": st_clp})
                return res

            st.session_state.slz = processar(slz_raw, False)
            st.session_state.bel = processar(bel_raw, True)
            st.session_state.at = agora.strftime("%H:%M")
            progresso.progress(100)
            st.rerun()

    except Exception as e: st.error(f"Erro: {e}")

if st.session_state.at != "-":
    st.write(f"⏱️ Última atualização: {st.session_state.at}")
    t1, t2 = st.tabs(["📍 São Luís", "📍 Belém"])
    with t1: st.table(st.session_state.slz)
    with t2: st.table(st.session_state.bel)

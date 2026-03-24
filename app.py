import streamlit as st
import imaplib, email, re, smtplib, sqlite3
from email.header import decode_header
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
import pytz
import time

# 1. Configuração e Fuso
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

def decodificar_assunto(subj_raw):
    if not subj_raw: return ""
    try:
        decoded = decode_header(subj_raw)
        res = ""
        for part, enc in decoded:
            if isinstance(part, bytes): res += part.decode(enc or 'utf-8', errors='ignore')
            else: res += str(part)
        return res.upper()
    except: return str(subj_raw).upper()

def extrair_datas(texto, ano):
    res = {"ETA": "-", "ETB": "-", "ETD": "-"}
    meses = {'JAN':1,'FEB':2,'MAR':3,'APR':4,'MAY':5,'JUN':6,'JUL':7,'AUG':8,'SEP':9,'OCT':10,'NOV':11,'DEC':12}
    txt = " ".join(texto.upper().split())
    def fmt(s):
        m_m = re.search(r'(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)', s)
        m_d = re.search(r'(\d{1,2})', s)
        return f"{int(m_d.group(1)):02d}/{meses[m_m.group(1)]:02d}/{ano}" if m_m and m_d else "-"
    m_eta = re.search(r"(NOTICE OF READINESS|ARRIVAL AT ROADS|ETA)\s*[:\-]?\s*([A-Z]{3,}\s+\d{1,2})", txt)
    if m_eta: res["ETA"] = fmt(m_eta.group(2))
    for k in ["ETB", "ETD", "ETS"]:
        m = re.search(rf"{k}\s*[:\-]?\s*([A-Z]{{3,}}\s+\d{{1,2}})", txt)
        if m: res["ETD" if k=="ETS" else k] = fmt(m.group(1))
    return res

# --- INTERFACE ---
st.title("🚢 Monitor Operacional Wilson Sons")
init_db()

if 'slz' not in st.session_state: 
    st.session_state.slz, st.session_state.bel, st.session_state.at = [], [], "-"

c1, c2 = st.columns(2)
with c1:
    if st.button("🔄 ATUALIZAR AGORA", use_container_width=True, type="primary"):
        try:
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            with st.status("🚀 Iniciando Sincronização...", expanded=True) as status:
                # ETAPA 1: Conexão
                status_text.text("Conectando ao Gmail...")
                mail = imaplib.IMAP4_SSL("imap.gmail.com")
                mail.login(EMAIL_USER, EMAIL_PASS)
                hoje_br = datetime.now(BR_TZ).date()
                progress_bar.progress(10)

                # ETAPA 2: Lista Navios (INBOX)
                status_text.text("Buscando Lista de Navios (Inbox)...")
                mail.select("INBOX", readonly=True)
                _, ids_l = mail.search(None, 'SUBJECT', '"LISTA NAVIOS"')
                slz_raw, bel_raw = [], []
                if ids_l[0]:
                    last_id = ids_l[0].split()[-1]
                    _, d = mail.fetch(last_id, '(BODY.PEEK[TEXT])')
                    corpo = decodificar_texto(d[0][1])
                    secao, vistos = None, set()
                    for linha in corpo.split('\n'):
                        l = linha.strip()
                        if "SLZ" in l.upper(): secao = "SLZ"; continue
                        if "BELEM" in l.upper(): secao = "BEL"; continue
                        if secao and len(l) > 3 and l.upper() not in vistos:
                            if secao == "SLZ": slz_raw.append(l)
                            else: bel_raw.append(l)
                            vistos.add(l.upper())
                progress_bar.progress(30)

                # ETAPA 3: Prospects (Bulk Fetch)
                status_text.text("Lendo Marcador PROSPECT...")
                mail.select("PROSPECT", readonly=True)
                _, msg_count = mail.select("PROSPECT", readonly=True)
                total_p = int(msg_count[0])
                prospy = []
                if total_p > 0:
                    start_p = max(1, total_p - 40) # Pega os últimos 40 direto pelo ID
                    ids_p = ",".join(map(str, range(start_p, total_p + 1)))
                    _, data_p = mail.fetch(ids_p, '(BODY.PEEK[HEADER.FIELDS (Subject Date)] BODY.PEEK[TEXT])')
                    
                    for i in range(0, len(data_p), 2):
                        if isinstance(data_p[i], tuple):
                            head = email.message_from_bytes(data_p[i][1])
                            body = decodificar_texto(data_p[i+1][1])
                            envio = email.utils.parsedate_to_datetime(head.get("Date")).astimezone(BR_TZ)
                            if envio.date() == hoje_br:
                                subj = decodificar_assunto(head.get("Subject"))
                                if any(t in subj for t in TERMOS_PROSPECT):
                                    prospy.append({"subj": subj, "date": envio, "datas": extrair_datas(body, envio.year)})
                progress_bar.progress(60)

                # ETAPA 4: CLP (Bulk Fetch)
                status_text.text("Lendo Marcador CLP...")
                mail.select("CLP", readonly=True)
                _, msg_count_c = mail.select("CLP", readonly=True)
                total_c = int(msg_count_c[0])
                clps_hoje = []
                if total_c > 0:
                    start_c = max(1, total_c - 30)
                    ids_c = ",".join(map(str, range(start_c, total_c + 1)))
                    _, data_c = mail.fetch(ids_c, '(BODY.PEEK[HEADER.FIELDS (Subject Date)])')
                    for item in data_c:
                        if isinstance(item, tuple):
                            m_c = email.message_from_bytes(item[1])
                            env_c = email.utils.parsedate_to_datetime(m_c.get("Date")).astimezone(BR_TZ).date()
                            if env_c == hoje_br:
                                clps_hoje.append(decodificar_assunto(m_c.get("Subject")))
                progress_bar.progress(85)

                # ETAPA 5: Processamento
                status_text.text("Finalizando cálculos...")
                mail.logout()

                def processar(lista, belem=False):
                    res = []
                    for n in lista:
                        n_id = re.sub(r'^(MV|M/V|MT|M/T)\s+', '', n.upper()).split(' - ')[0].strip()
                        matches = [e for e in prospy if n_id in e["subj"]]
                        matches.sort(key=lambda x: x["date"], reverse=True)
                        p_datas = matches[0]["datas"] if matches else {"ETA":"-","ETB":"-","ETD":"-"}
                        db = ler_banco(n)
                        eta = p_datas["ETA"] if p_datas["ETA"] != "-" else db[0]
                        etb = p_datas["ETB"] if p_datas["ETB"] != "-" else db[1]
                        etd = p_datas["ETD"] if p_datas["ETD"] != "-" else db[2]
                        st_clp = "✅ EMITIDA" if any(n_id in c for c in clps_hoje) else db[3]
                        
                        if st_clp != "✅ EMITIDA" and eta != "-":
                            try:
                                d,m,a = eta.split("/"); diff = (datetime(int(a),int(m),int(d)).date() - hoje_br).days
                                if diff <= 4: st_clp = "⚠️ CRÍTICO"
                            except: pass
                        
                        salvar_banco(n, eta, etb, etd, st_clp)
                        res.append({"Navio": n_id if belem else n, "Prospect Manhã": "✅" if any(e["date"].hour < 13 for e in matches) else "❌", "Prospect Tarde": "✅" if any(e["date"].hour >= 13 for e in matches) else "❌", "ETA": eta, "ETB": etb, "ETD": etd, "CLP": st_clp})
                    return res

                st.session_state.slz = processar(slz_raw, False)
                st.session_state.bel = processar(bel_raw, True)
                st.session_state.at = datetime.now(BR_TZ).strftime("%H:%M")
                
                progress_bar.progress(100)
                status_text.text("Concluído!")
                time.sleep(1)
                st.rerun()
        except Exception as e: st.error(f"Erro: {e}")

if st.session_state.at != "-":
    st.write(f"⏱️ Atualizado em: {st.session_state.at}")
    t1, t2 = st.tabs(["📍 São Luís", "📍 Belém"])
    with t1: st.table(st.session_state.slz)
    with t2: st.table(st.session_state.bel)

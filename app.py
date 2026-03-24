import streamlit as st
import imaplib, email, re, smtplib, sqlite3
from email.header import decode_header
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import pytz

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
        eta_f = eta if (eta != "-" and eta is not None) else ex[0]
        etb_f = etb if (etb != "-" and etb is not None) else ex[1]
        etd_f = etd if (etd != "-" and etd is not None) else ex[2]
        c.execute("INSERT OR REPLACE INTO navios VALUES (?,?,?,?,?,?)", 
                  (nome_id, eta_f, etb_f, etd_f, clp, datetime.now(BR_TZ).strftime("%H:%M")))
        conn.commit()
        conn.close()
    except: pass

# --- APOIO ---
def decodificar_texto_limpo(payload):
    if not payload: return ""
    txt = payload.decode(errors='ignore') if isinstance(payload, bytes) else str(payload)
    txt = re.sub(r'<(br|div|p|/tr|tr)[^>]*>', '\n', txt, flags=re.IGNORECASE)
    txt = re.sub(r'<[^>]+>', '', txt)
    return txt

def decodificar_assunto(subj):
    if not subj: return ""
    try:
        decoded = decode_header(subj)
        res = ""
        for part, enc in decoded:
            if isinstance(part, bytes): res += part.decode(enc or 'utf-8', errors='ignore')
            else: res += str(part)
        return res.upper()
    except: return str(subj).upper()

def extrair_datas_prospect(texto_puro, envio):
    res = {"ETA": "-", "ETB": "-", "ETD": "-"}
    txt = " ".join(texto_puro.upper().split())
    meses_map = {'JAN':1,'FEB':2,'MAR':3,'APR':4,'MAY':5,'JUN':6,'JUL':7,'AUG':8,'SEP':9,'OCT':10,'NOV':11,'DEC':12}
    def parse_data(s):
        m_mes = re.search(r'(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)', s)
        m_dia = re.search(r'(\d{1,2})', s)
        if m_mes and m_dia:
            return f"{int(m_dia.group(1)):02d}/{meses_map[m_mes.group(1)]:02d}/{envio.year}"
        return "-"
    for k in ["ETA", "ETB", "ETD"]:
        m = re.search(rf"{k}\s*[:\-]?\s*([A-Z]{{3,}}\s+\d{{1,2}})", txt)
        if m: res[k] = parse_data(m.group(1))
    return res

# --- INTERFACE ---
st.title("🚢 Monitor Operacional Wilson Sons")
init_db()

if 'slz' not in st.session_state: st.session_state.slz = []
if 'bel' not in st.session_state: st.session_state.bel = []
if 'at' not in st.session_state: st.session_state.at = "-"

c1, c2 = st.columns(2)
with c1:
    if st.button("🔄 ATUALIZAR AGORA", use_container_width=True, type="primary"):
        try:
            with st.status("🔍 Sincronizando (Filtro Python)...", expanded=True):
                mail = imaplib.IMAP4_SSL("imap.gmail.com")
                mail.login(EMAIL_USER, EMAIL_PASS)
                hoje_br = datetime.now(BR_TZ).date()
                
                # 1. LISTA NAVIOS (Pega os últimos 10 e-mails do INBOX)
                mail.select("INBOX", readonly=True)
                _, data_l = mail.search(None, 'ALL')
                ids_l = data_l[0].split()
                slz_raw, bel_raw = [], []
                
                for eid in reversed(ids_l[-10:]): # Olha os últimos 10
                    _, d = mail.fetch(eid, '(BODY.PEEK[HEADER.FIELDS (Subject Date)] BODY.PEEK[TEXT])')
                    msg_h = email.message_from_bytes(d[0][1])
                    assunto = decodificar_assunto(msg_h.get("Subject"))
                    data_envio = email.utils.parsedate_to_datetime(msg_h.get("Date")).astimezone(BR_TZ).date()
                    
                    if "LISTA NAVIOS" in assunto and data_envio == hoje_br:
                        corpo = decodificar_texto_limpo(d[1][1])
                        secao, vistos = None, set()
                        for linha in corpo.split('\n'):
                            l = linha.strip()
                            if "SLZ" in l.upper(): secao = "SLZ"; continue
                            if "BELEM" in l.upper(): secao = "BEL"; continue
                            if secao and len(l) > 3 and l.upper() not in vistos:
                                if secao == "SLZ": slz_raw.append(l)
                                else: bel_raw.append(l)
                                vistos.add(l.upper())
                        break # Achou a lista de hoje, para de buscar

                # 2. PROSPECTS (Pega os últimos 100 da pasta PROSPECT)
                mail.select("PROSPECT", readonly=True)
                _, data_p = mail.search(None, 'ALL')
                ids_p = data_p[0].split()
                prospy = []
                
                for eid in ids_p[-100:]: # Olha os últimos 100
                    _, d = mail.fetch(eid, '(BODY.PEEK[HEADER.FIELDS (Subject Date)] BODY.PEEK[TEXT])')
                    msg_h = email.message_from_bytes(d[0][1])
                    data_envio = email.utils.parsedate_to_datetime(msg_h.get("Date")).astimezone(BR_TZ)
                    
                    if data_envio.date() == hoje_br:
                        subj = decodificar_assunto(msg_h.get("Subject"))
                        if any(t in subj for t in TERMOS_PROSPECT):
                            corpo_txt = d[1][1].decode(errors='ignore') if len(d)>1 else ""
                            prospy.append({"subj": subj, "date": data_envio, "datas": extrair_datas_prospect(corpo_txt, data_envio)})

                # 3. CLP (Pega os últimos 50 da pasta CLP)
                mail.select("CLP", readonly=True)
                _, data_c = mail.search(None, 'ALL')
                ids_c = data_c[0].split()
                clps_hoje = []
                
                for eid in ids_c[-50:]:
                    _, d = mail.fetch(eid, '(BODY.PEEK[HEADER.FIELDS (Subject Date)])')
                    msg_h = email.message_from_bytes(d[0][1])
                    data_envio = email.utils.parsedate_to_datetime(msg_h.get("Date")).astimezone(BR_TZ).date()
                    if data_envio == hoje_br:
                        clps_hoje.append(decodificar_assunto(msg_h.get("Subject")))

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
                        
                        salvar_banco(n, eta, etb, etd, st_clp)
                        res.append({
                            "Navio": n_id if belem else n,
                            "Prospect Manhã": "✅" if any(e["date"].hour < 13 for e in matches) else "❌",
                            "Prospect Tarde": "✅" if any(e["date"].hour >= 13 for e in matches) else "❌",
                            "ETA": eta, "ETB": etb, "ETD": etd, "CLP": st_clp
                        })
                    return res

                st.session_state.slz = processar(slz_raw, False)
                st.session_state.bel = processar(bel_raw, True)
                st.session_state.at = datetime.now(BR_TZ).strftime("%H:%M")
                st.rerun()
        except Exception as e: st.error(f"Erro: {e}")

if st.session_state.at != "-":
    t1, t2 = st.tabs(["📍 São Luís", "📍 Belém"])
    with t1: st.table(st.session_state.slz)
    with t2: st.table(st.session_state.bel)

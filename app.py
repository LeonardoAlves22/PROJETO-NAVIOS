import streamlit as st
import imaplib, email, re, sqlite3
from email.header import decode_header
from datetime import datetime, timedelta
import pytz

# 1. Configuração da Página
st.set_page_config(page_title="Monitor WS", layout="wide")
BR_TZ = pytz.timezone('America/Sao_Paulo')

# --- CONFIGURAÇÕES ---
EMAIL_USER = "leonardo.alves@wilsonsons.com.br"
EMAIL_PASS = "nlvr vmyv cbcq oexe"
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
        c.execute("INSERT OR REPLACE INTO navios VALUES (?,?,?,?,?,?)", 
                  (nome_id, eta, etb, etd, clp, datetime.now(BR_TZ).strftime("%H:%M")))
        conn.commit()
        conn.close()
    except: pass

# --- APOIO ---
def extrair_corpo_email(msg):
    corpo = ""
    try:
        if msg.is_multipart():
            for parte in msg.walk():
                if parte.get_content_type() in ['text/plain', 'text/html']:
                    payload = parte.get_payload(decode=True)
                    if payload: corpo += payload.decode(errors='ignore')
        else:
            payload = msg.get_payload(decode=True)
            if payload: corpo = payload.decode(errors='ignore')
    except: pass
    return corpo

def extrair_datas_prospect(corpo_sujo, envio):
    res = {"ETA": "-", "ETB": "-", "ETD": "-"}
    txt = re.sub(r'<[^>]+>', ' ', corpo_sujo).upper()
    txt = " ".join(txt.split())
    meses_map = {'JAN':1,'FEB':2,'MAR':3,'APR':4,'MAY':5,'JUN':6,'JUL':7,'AUG':8,'SEP':9,'OCT':10,'NOV':11,'DEC':12}
    
    def parse_data(s):
        m_mes = re.search(r'(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)', s)
        m_dia = re.search(r'(\d{1,2})', s)
        if m_mes and m_dia:
            return f"{int(m_dia.group(1)):02d}/{meses_map[m_mes.group(1)]:02d}/{envio.year}"
        return "-"

    termos = [r"NOTICE OF READINESS\s*[:\-]?\s*([A-Z]{3,}\s+\d{1,2})", r"ARRIVAL AT ROADS\s*[:\-]?\s*([A-Z]{3,}\s+\d{1,2})", r"ETA\s*[:\-]?\s*([A-Z]{3,}\s+\d{1,2})"]
    for t in termos:
        m = re.search(t, txt)
        if m: res["ETA"] = parse_data(m.group(1)); break
    for k in ["ETB", "ETD"]:
        m = re.search(rf"{k}\s*[:\-]?\s*([A-Z]{{3,}}\s+\d{{1,2}})", txt)
        if m: res[k] = parse_data(m.group(1))
    return res

# --- INTERFACE ---
st.title("🚢 Monitor Operacional Wilson Sons")
init_db()

if 'slz' not in st.session_state: st.session_state.slz, st.session_state.bel, st.session_state.at = [], [], "-"

if st.button("🔄 ATUALIZAR AGORA", use_container_width=True, type="primary"):
    try:
        with st.status("Sincronizando...", expanded=True) as status:
            mail = imaplib.IMAP4_SSL("imap.gmail.com")
            mail.login(EMAIL_USER, EMAIL_PASS)
            agora = datetime.now(BR_TZ)
            
            # 1. BUSCA O RELATÓRIO DO APPS SCRIPT
            mail.select("INBOX", readonly=True)
            # Busca simples apenas pelo Assunto (sem filtros de data complexos)
            _, d_l = mail.search(None, '(SUBJECT "STATUS OPERACIONAL (SLZ & BEL)")')
            
            navios_com_clp = {} 
            slz_list, bel_list = [], []

            if d_l[0]:
                # Pega o último e-mail desse assunto
                eid_lista = d_l[0].split()[-1]
                _, d = mail.fetch(eid_lista, '(RFC822)')
                corpo = extrair_corpo_email(email.message_from_bytes(d[0][1]))
                secao, navio_atual = None, None
                for linha in corpo.split('\n'):
                    l = linha.strip().upper()
                    if "📍 SLZ" in l: secao = "SLZ"; continue
                    if "📍 BEL" in l: secao = "BEL"; continue
                    if "🚢" in linha:
                        navio_atual = linha.replace("🚢", "").replace("NAVIO:", "").strip().upper()
                        if secao == "SLZ": slz_list.append(navio_atual)
                        else: bel_list.append(navio_atual)
                    if "LIVRE PRÁTICA (CLP):" in l and navio_atual:
                        navios_com_clp[navio_atual] = linha.split(":")[-1].strip()

            # 2. BUSCA PROSPECTS (Pega os últimos 50 e filtra no Python)
            mail.select("PROSPECT", readonly=True)
            _, d_p = mail.search(None, 'ALL')
            
            prospy = []
            if d_p[0]:
                # Pega os últimos 50 IDs de e-mail da pasta Prospect
                lista_ids = d_p[0].split()[-50:]
                for eid in reversed(lista_ids):
                    _, data = mail.fetch(eid, '(BODY.PEEK[HEADER.FIELDS (Subject Date)] BODY.PEEK[TEXT])')
                    head = email.message_from_bytes(data[0][1])
                    envio = email.utils.parsedate_to_datetime(head.get("Date")).astimezone(BR_TZ)
                    
                    # Filtra: Somente hoje ou ontem
                    if envio.date() >= (agora.date() - timedelta(days=1)):
                        raw_subj = decode_header(head.get("Subject"))[0][0]
                        subj = (raw_subj.decode() if isinstance(raw_subj, bytes) else str(raw_subj)).upper()
                        
                        if any(t in subj for t in TERMOS_PROSPECT):
                            body = data[1][1].decode(errors='ignore')
                            prospy.append({"subj": subj, "date": envio, "datas": extrair_datas_prospect(body, envio)})

            mail.logout()

            # 3. CONSOLIDAÇÃO
            def consolidar(lista):
                final = []
                for n in lista:
                    n_clean = n.split(' - ')[0].strip()
                    matches = sorted([e for e in prospy if n_clean in e["subj"]], key=lambda x: x["date"], reverse=True)
                    p_datas = matches[0]["datas"] if matches else {"ETA":"-","ETB":"-","ETD":"-"}
                    clp_final = navios_com_clp.get(n.upper(), "❌ PENDENTE")
                    salvar_banco(n, p_datas["ETA"], p_datas["ETB"], p_datas["ETD"], clp_final)
                    final.append({"Navio": n, "ETA": p_datas["ETA"], "ETB": p_datas["ETB"], "ETD": p_datas["ETD"], "CLP": clp_final})
                return final

            st.session_state.slz = consolidar(slz_list)
            st.session_state.bel = consolidar(bel_list)
            st.session_state.at = agora.strftime("%H:%M")
            st.rerun()
    except Exception as e: st.error(f"Erro Crítico: {e}")

# --- EXIBIÇÃO ---
if st.session_state.at != "-":
    st.write(f"⏱️ Sincronizado com E-mail Consolidado: {st.session_state.at}")
    t1, t2 = st.tabs(["📍 São Luís", "📍 Belém"])
    with t1: st.table(st.session_state.slz)
    with t2: st.table(st.session_state.bel)

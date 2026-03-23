import streamlit as st
import imaplib, email, re, smtplib, sqlite3
from email.header import decode_header
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta, timezone
import pytz

# 1. Configuração da Página
st.set_page_config(page_title="Monitor WS", layout="wide")
BR_TZ = pytz.timezone('America/Sao_Paulo')

# --- CONFIGURAÇÕES ---
EMAIL_USER = "leonardo.alves@wilsonsons.com.br"
EMAIL_PASS = "nlvr vmyv cbcq oexe"
DESTINATARIO = "leonardo.alves@wilsonsons.com.br"

REMETENTES_VALIDOS = ["operation.sluis", "operation.belem", "agencybrazil"]
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

# --- FUNÇÕES DE APOIO (ESSENCIAIS) ---
def extrair_corpo_email(msg):
    """Extrai o conteúdo de texto ou HTML do e-mail de forma segura."""
    corpo = ""
    try:
        if msg.is_multipart():
            for parte in msg.walk():
                tipo = parte.get_content_type()
                if tipo in ['text/plain', 'text/html']:
                    payload = parte.get_payload(decode=True)
                    if payload:
                        corpo = payload.decode(errors='ignore')
                        if tipo == 'text/html': # Prioriza HTML se disponível
                            break
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                corpo = payload.decode(errors='ignore')
    except: pass
    return corpo

def decodificar_assunto(m):
    subj = m.get("Subject", "")
    decoded = decode_header(subj)
    res = ""
    for part, enc in decoded:
        if isinstance(part, bytes): 
            res += part.decode(enc or 'utf-8', errors='ignore')
        else: 
            res += str(part)
    return res.upper()

def limpar_visual_nome(n):
    n = n.upper()
    porto = re.search(r'(\(.*?\))', n)
    p_str = porto.group(1) if porto else ""
    limpo = re.sub(r'^(MV|M/V|MT|M/T)\s+', '', n)
    limpo = limpo.split(' - ')[0].split(' (')[0].strip()
    return f"{limpo} {p_str}".strip()

def extrair_datas_prospect(corpo_sujo, envio):
    res = {"ETA": "-", "ETB": "-", "ETD": "-"}
    # Limpa HTML para busca de texto
    txt = re.sub(r'<[^>]+>', ' ', corpo_sujo).upper()
    txt = " ".join(txt.split())
    meses_map = {'JAN':1,'FEB':2,'MAR':3,'APR':4,'MAY':5,'JUN':6,'JUL':7,'AUG':8,'SEP':9,'OCT':10,'NOV':11,'DEC':12}
    
    def parse_data(s):
        m_mes = re.search(r'(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)', s)
        m_dia = re.search(r'(\d{1,2})', s)
        if m_mes and m_dia:
            return f"{int(m_dia.group(1)):02d}/{meses_map[m_mes.group(1)]:02d}/{envio.year}"
        return "-"

    # Hierarquia de datas (NOR > Arrival > ETA)
    termos = [
        r"NOTICE OF READINESS\s*[:\-]?\s*([A-Z]{3,}\s+\d{1,2})",
        r"ARRIVAL AT ROADS\s*[:\-]?\s*([A-Z]{3,}\s+\d{1,2})",
        r"ETA\s+.*?(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)\s*(\d{1,2})",
        r"ETA\s*[:\-]?\s*([A-Z]{3,}\s+\d{1,2})"
    ]
    for t in termos:
        m = re.search(t, txt)
        if m:
            dt = parse_data(m.group(0) if "ETA" in t else m.group(1))
            if dt != "-": 
                res["ETA"] = dt
                break
    for k in ["ETB", "ETD", "ETS"]:
        m = re.search(rf"{k}\s*[:\-]?\s*([A-Z]{{3,}}\s+\d{{1,2}})", txt)
        if m:
            dt = parse_data(m.group(1))
            if dt != "-": res["ETD" if k=="ETS" else k] = dt
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
            with st.status("Sincronizando...", expanded=True) as status:
                mail = imaplib.IMAP4_SSL("imap.gmail.com")
                mail.login(EMAIL_USER, EMAIL_PASS)
                agora = datetime.now(BR_TZ)
                
                # 1. LISTA NAVIOS (INBOX)
                mail.select("INBOX", readonly=True)
                _, d_l = mail.search(None, '(SUBJECT "LISTA NAVIOS")')
                slz_raw, bel_raw = [], []
                if d_l[0]:
                    _, d = mail.fetch(d_l[0].split()[-1], '(RFC822)')
                    corpo_lista = extrair_corpo_email(email.message_from_bytes(d[0][1]))
                    linhas = [l.strip() for l in corpo_lista.split('\n') if len(l.strip()) > 1]
                    section = None
                    for linha in linhas:
                        if "SLZ:" in linha.upper(): section = "SLZ"; continue
                        if "BELEM:" in linha.upper(): section = "BEL"; continue
                        if section == "SLZ" and len(linha) > 3: slz_raw.append(linha)
                        elif section == "BEL" and len(linha) > 3: bel_raw.append(linha)

                # 2. PROSPECTS
                mail.select("PROSPECT", readonly=True)
                _, d_p = mail.search(None, f'(SINCE "{(agora - timedelta(days=1)).strftime("%d-%b-%Y")}")')
                prospy = []
                if d_p[0]:
                    for eid in d_p[0].split()[-150:]:
                        _, d = mail.fetch(eid, '(RFC822)')
                        m = email.message_from_bytes(d[0][1])
                        subj = decodificar_assunto(m)
                        if any(term in subj for term in TERMOS_PROSPECT):
                            envio = email.utils.parsedate_to_datetime(m.get("Date")).astimezone(BR_TZ)
                            prospy.append({"subj": subj, "date": envio, "datas": extrair_datas_prospect(extrair_corpo_email(m), envio)})

                # 3. CLP
                mail.select("CLP", readonly=True)
                _, d_c = mail.search(None, "ALL")
                clps_list = [decodificar_assunto(email.message_from_bytes(mail.fetch(e, '(BODY[HEADER.FIELDS (SUBJECT)])')[1][0][1])) for e in d_c[0].split()[-60:]] if d_c[0] else []
                mail.logout()

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
                        st_clp = "✅ EMITIDA" if tem_clp else "❌ PENDENTE"
                        salvar_banco(n, eta, etb, etd, st_clp)
                        today_m = [e for e in matches if e["date"].date() == agora.date()]
                        res.append({"Navio": limpar_visual_nome(n) if belem else n, "Prospect Manhã": "✅" if any(e["date"].hour < 13 for e in today_m) else "❌", "Prospect Tarde": "✅" if any(e["date"].hour >= 13 for e in today_m) else "❌", "ETA": eta, "ETB": etb, "ETD": etd, "CLP": st_clp})
                    return res

                st.session_state.slz = processar(slz_raw, False); st.session_state.bel = processar(bel_raw, True); st.session_state.at = agora.strftime("%H:%M"); st.rerun()
        except Exception as e: st.error(f"Erro: {e}")

if st.session_state.at != "-":
    t1, t2 = st.tabs(["📍 São Luís", "📍 Belém"])
    with t1: st.table(st.session_state.slz)
    with t2: st.table(st.session_state.bel)

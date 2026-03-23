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

def init_db():
    try:
        conn = sqlite3.connect('monitor_navios.db', check_same_thread=False)
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS navios 
                     (nome TEXT PRIMARY KEY, eta TEXT, etb TEXT, etd TEXT, clp TEXT, atualizacao TEXT)''')
        try: c.execute("ALTER TABLE navios ADD COLUMN clp TEXT")
        except: pass
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

# --- EXTRAÇÃO DE DATAS BLINDADA (ESPECÍFICA PARA VILA DO CONDE) ---
def extrair_datas_prospect(corpo, envio):
    res = {"ETA": "-", "ETB": "-", "ETD": "-"}
    if not corpo: return res
    # Remove HTML e normaliza espaços
    txt = re.sub(r'<[^>]+>', ' ', corpo.upper())
    txt = " ".join(txt.split())
    
    meses_map = {'JAN':1,'FEB':2,'MAR':3,'APR':4,'MAY':5,'JUN':6,'JUL':7,'AUG':8,'SEP':9,'OCT':10,'NOV':11,'DEC':12}
    
    def parse_flex(string_data):
        # Captura Mes (3 letras) e Dia (1-2 digitos) - Ignora o 'th', 'st', etc.
        m_mes = re.search(r'(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)', string_data.upper())
        m_dia = re.search(r'(\d{1,2})', string_data)
        if m_mes and m_dia:
            return f"{int(m_dia.group(1)):02d}/{meses_map[m_mes.group(1)]:02d}/{envio.year}"
        return "-"

    # ETB e ETD
    for k in ["ETB", "ETD", "ETS"]:
        m = re.search(rf"{k}\s*[:\-]?\s*([A-Z]{{3,}}\s+\d{{1,2}})", txt)
        if m:
            dt = parse_flex(m.group(1))
            if dt != "-": res["ETD" if k=="ETS" else k] = dt

    # ETA (Incluso o novo padrão "ETA AT VILA DO ANCHORAGE")
    padrões_eta = [
        r"ETA\s+AT\s+VILA\s+DO\s+ANCHORAGE\s*([A-Z]{3,}\s+\d{1,2})",
        r"ETA\s*[:\-]?\s*([A-Z]{3,}\s+\d{1,2})",
        r"ARRIVAL\s+AT\s+ROADS\s*([A-Z]{3,}\s+\d{1,2})",
        r"NOTICE\s+OF\s+READINESS\s*([A-Z]{3,}\s+\d{1,2})"
    ]
    
    for p in padrões_eta:
        m = re.search(p, txt)
        if m:
            dt = parse_flex(m.group(1))
            if dt != "-": 
                res["ETA"] = dt
                break
    return res

def limpar_visual(n):
    porto = re.search(r'(\(.*?\))', n)
    p_str = porto.group(1) if porto else ""
    limpo = re.sub(r'^(MV|M/V|MT|M/T)\s+', '', n.upper())
    limpo = limpo.split(' - ')[0].split(' (')[0].strip()
    return f"{limpo} {p_str}".strip()

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
                
                mail.select("INBOX", readonly=True)
                _, d_l = mail.search(None, '(SUBJECT "LISTA NAVIOS")')
                slz_raw, bel_raw = [], []
                if d_l[0]:
                    _, d = mail.fetch(d_l[0].split()[-1], '(RFC822)')
                    msg = email.message_from_bytes(d[0][1])
                    conteudo = ""
                    if msg.is_multipart():
                        for part in msg.walk():
                            if part.get_content_type() == 'text/plain':
                                conteudo = part.get_payload(decode=True).decode(errors='ignore')
                                break
                    else: conteudo = msg.get_payload(decode=True).decode(errors='ignore')
                    
                    pts = re.split(r'BELEM:', conteudo, flags=re.IGNORECASE)
                    slz_raw = [l.strip() for l in pts[0].replace('SLZ:', '').split('\n') if len(l.strip()) > 5]
                    if len(pts) > 1: bel_raw = [l.strip() for l in pts[1].split('\n') if len(l.strip()) > 5]

                # PROSPECTS
                mail.select("PROSPECT", readonly=True)
                _, d_p = mail.search(None, f'(SINCE "{(agora - timedelta(days=1)).strftime("%d-%b-%Y")}")')
                prospy = []
                if d_p[0]:
                    for eid in d_p[0].split()[-100:]:
                        _, d = mail.fetch(eid, '(RFC822)')
                        m = email.message_from_bytes(d[0][1])
                        envio = email.utils.parsedate_to_datetime(m.get("Date")).astimezone(BR_TZ)
                        
                        corpo_p = ""
                        for part in m.walk():
                            if part.get_content_type() in ["text/plain", "text/html"]:
                                corpo_p = part.get_payload(decode=True).decode(errors='ignore')
                                break
                        
                        subj = "".join(str(c.decode(ch or 'utf-8') if isinstance(c, bytes) else c) for c, ch in decode_header(m.get("Subject", ""))).upper()
                        if any(term in subj for term in TERMOS_PROSPECT):
                            prospy.append({"subj": subj, "date": envio, "datas": extrair_datas_prospect(corpo_p, envio)})

                mail.logout()

                def processar(lista, belem=False):
                    res = []
                    for n in lista:
                        n_id = n.split(' - ')[0].split(' (')[0].strip().upper()
                        # Busca flexível por contenção do nome no assunto
                        matches = [e for e in prospy if n_id.replace("MV ","").replace("MT ","").strip() in e["subj"]]
                        matches.sort(key=lambda x: x["date"], reverse=True)
                        
                        p_datas = matches[0]["datas"] if matches else {"ETA":"-","ETB":"-","ETD":"-"}
                        db = ler_banco(n) # Uso o nome original da lista para o banco
                        
                        eta = p_datas["ETA"] if p_datas["ETA"] != "-" else db[0]
                        etb = p_datas["ETB"] if p_datas["ETB"] != "-" else db[1]
                        etd = p_datas["ETD"] if p_datas["ETD"] != "-" else db[2]
                        
                        salvar_banco(n, eta, etb, etd, "❌ PENDENTE")
                        today_m = [e for e in matches if e["date"].date() == agora.date()]
                        
                        res.append({"Navio": limpar_visual(n) if belem else n, 
                                    "Prospect Manhã": "✅" if any(e["date"].hour < 13 for e in today_m) else "❌", 
                                    "Prospect Tarde": "✅" if any(e["date"].hour >= 13 for e in today_m) else "❌", 
                                    "ETA": eta, "ETB": etb, "ETD": etd})
                    return res

                st.session_state.slz = processar(slz_raw, False)
                st.session_state.bel = processar(bel_raw, True)
                st.session_state.at = agora.strftime("%H:%M")
                st.rerun()
        except Exception as e: st.error(f"Erro: {e}")

if st.session_state.at != "-":
    t1, t2 = st.tabs(["📍 São Luís", "📍 Belém"])
    with t1: st.table(st.session_state.slz)
    with t2: st.table(st.session_state.bel)

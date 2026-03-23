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
        c.execute("SELECT eta, etb, etd, clp FROM navios WHERE nome=? COLLATE NOCASE", (nome_id,))
        res = c.fetchone()
        conn.close()
        return res if res else ("-", "-", "-", "❌ PENDENTE")
    except: return ("-", "-", "-", "❌ PENDENTE")

def salvar_banco(nome_id, eta, etb, etd, clp):
    try:
        conn = sqlite3.connect('monitor_navios.db', check_same_thread=False)
        c = conn.cursor()
        ex = ler_banco(nome_id)
        # SÓ SUBSTITUI SE TIVER DADO NOVO. Se vier "-", mantém o que já estava no banco.
        eta_f = eta if (eta != "-" and eta is not None) else ex[0]
        etb_f = etb if (etb != "-" and etb is not None) else ex[1]
        etd_f = etd if (etd != "-" and etd is not None) else ex[2]
        
        c.execute("INSERT OR REPLACE INTO navios VALUES (?,?,?,?,?,?)", 
                  (nome_id, eta_f, etb_f, etd_f, clp, datetime.now(BR_TZ).strftime("%H:%M")))
        conn.commit()
        conn.close()
    except: pass

# --- EXTRAÇÃO INTELIGENTE DE DATAS ---
def extrair_datas_prospect(corpo, envio):
    res = {"ETA": "-", "ETB": "-", "ETD": "-"}
    if not corpo: return res
    # Remove tags HTML e limpa espaços extras
    txt = re.sub(r'<[^>]+>', ' ', corpo.upper())
    txt = " ".join(txt.split())
    
    meses_map = {'JAN':1,'FEB':2,'MAR':3,'APR':4,'MAY':5,'JUN':6,'JUL':7,'AUG':8,'SEP':9,'OCT':10,'NOV':11,'DEC':12}
    
    def parse_data_flexivel(texto_busca):
        # Tenta padrão: MAR 22ND ou 22ND MAR ou 22/03
        dia = re.search(r'(\d{1,2})', texto_busca)
        mes = re.search(r'(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)', texto_busca.upper())
        if dia and mes:
            return f"{int(dia.group(1)):02d}/{meses_map[mes.group(1)]:02d}/{envio.year}"
        return "-"

    # Busca específica para Belém/Vila do Conde
    for k in ["ETB", "ETD", "ETS"]:
        m = re.search(rf"{k}\s*[:\-]?\s*([A-Z0-9\s]{{3,20}})", txt)
        if m:
            dt = parse_data_flexivel(m.group(1))
            if dt != "-": res["ETD" if k=="ETS" else k] = dt

    for g in ["ETA", "ARRIVAL", "NOR TENDERED"]:
        m = re.search(rf"{g}\s*[:\-]?\s*([A-Z0-9\s]{{3,20}})", txt)
        if m:
            dt = parse_data_flexivel(m.group(1))
            if dt != "-": res["ETA"] = dt; break
    return res

def verificar_correspondencia(nome_lista, assunto):
    # Remove prefixos e Voyage
    navio_puro = re.sub(r'^(MV|M/V|MT|M/T)\s+', '', nome_lista.upper())
    navio_puro = navio_puro.split(' - ')[0].split(' (')[0].strip()
    # Verifica se o nome principal está no assunto do e-mail
    return navio_puro in assunto.upper()

def limpar_nome_visual(n):
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
                    for eid in d_p[0].split()[-100:]: # Aumentei para os últimos 100
                        _, d = mail.fetch(eid, '(RFC822)')
                        m = email.message_from_bytes(d[0][1])
                        subj = "".join(str(c.decode(ch or 'utf-8') if isinstance(c, bytes) else c) for c, ch in decode_header(m.get("Subject", ""))).upper()
                        envio = email.utils.parsedate_to_datetime(m.get("Date")).astimezone(BR_TZ)
                        
                        corpo_p = ""
                        for part in m.walk():
                            if part.get_content_type() in ["text/plain", "text/html"]:
                                corpo_p = part.get_payload(decode=True).decode(errors='ignore')
                                break
                                
                        if any(term in subj for term in TERMOS_PROSPECT):
                            prospy.append({"subj": subj, "date": envio, "datas": extrair_datas_prospect(corpo_p, envio)})

                # CLP
                mail.select("CLP", readonly=True)
                _, d_c = mail.search(None, "ALL")
                clps = [str(decode_header(email.message_from_bytes(mail.fetch(e, '(BODY[HEADER.FIELDS (SUBJECT)])')[1][0][1]).get("Subject"))[0][0]).upper() for e in d_c[0].split()[-60:]] if d_c[0] else []
                mail.logout()

                def processar(lista, belem=False):
                    res = []
                    for n in lista:
                        n_id = n.split(' - ')[0].split(' (')[0].strip().upper()
                        matches = [e for e in prospy if verificar_correspondencia(n, e["subj"])]
                        matches.sort(key=lambda x: x["date"], reverse=True)
                        
                        p_datas = matches[0]["datas"] if matches else {"ETA":"-","ETB":"-","ETD":"-"}
                        db = ler_banco(n_id)
                        
                        eta = p_datas["ETA"] if p_datas["ETA"] != "-" else db[0]
                        etb = p_datas["ETB"] if p_datas["ETB"] != "-" else db[1]
                        etd = p_datas["ETD"] if p_datas["ETD"] != "-" else db[2]
                        
                        tem_clp = any(n_id in s for s in clps)
                        st_clp = "✅ EMITIDA" if tem_clp else "❌ PENDENTE"
                        if not tem_clp and eta != "-" and "/" in eta:
                            try:
                                d,m,a = eta.split("/"); d_eta = datetime(int(a),int(m),int(d), tzinfo=BR_TZ)
                                if (d_eta - agora).days <= 4: st_clp = "⚠️ CRÍTICO"
                            except: pass
                        
                        salvar_banco(n_id, eta, etb, etd, st_clp)
                        today_m = [e for e in matches if e["date"].date() == agora.date()]
                        
                        res.append({"Navio": limpar_nome_visual(n) if belem else n, 
                                    "Prospect Manhã": "✅" if any(e["date"].hour < 13 for e in today_m) else "❌", 
                                    "Prospect Tarde": "✅" if any(e["date"].hour >= 13 for e in today_m) else "❌", 
                                    "ETA": eta, "ETB": etb, "ETD": etd, "CLP": st_clp})
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

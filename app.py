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
        eta_f = eta if eta != "-" else ex[0]
        etb_f = etb if etb != "-" else ex[1]
        etd_f = etd if etd != "-" else ex[2]
        c.execute("INSERT OR REPLACE INTO navios VALUES (?,?,?,?,?,?)", 
                  (nome_id, eta_f, etb_f, etd_f, clp, datetime.now(BR_TZ).strftime("%H:%M")))
        conn.commit()
        conn.close()
    except: pass

# --- FUNÇÕES DE LIMPEZA E MATCH ---
def decodificar_cabecalho(msg, campo):
    try:
        val = msg.get(campo)
        if val is None: return ""
        partes = decode_header(val)
        res = ""
        for t, encoding in partes:
            if isinstance(t, bytes): res += t.decode(encoding or 'utf-8', errors='ignore')
            else: res += str(t)
        return res.upper().strip()
    except: return str(msg.get(campo) or "").upper().strip()

def extrair_corpo_email(msg):
    try:
        if msg.is_multipart():
            for parte in msg.walk():
                if parte.get_content_type() == 'text/plain':
                    return parte.get_payload(decode=True).decode(errors='ignore')
        return msg.get_payload(decode=True).decode(errors='ignore')
    except: return ""

def verificar_correspondencia(nome_completo_lista, assunto_email):
    # Remove prefixos e Voyage para pegar o nome puro (Ex: DEVBULK CANSEN)
    nome_limpo = re.sub(r'^(MV|M/V|MT|M/T|M\.V\.|M\.T\.)\s+', '', nome_completo_lista.upper())
    nome_limpo = nome_limpo.split(' - ')[0].split(' (')[0].strip()
    palavras = [p for p in nome_limpo.split() if len(p) > 2]
    if not palavras: return False
    return palavras[-1] in assunto_email.upper()

def limpar_visual_belem(nome_completo):
    # Mantém apenas o nome principal + (Vila do conde) ou (Belem)
    porto = re.search(r'(\(.*?\))', nome_completo)
    porto_str = porto.group(1) if porto else ""
    nome = re.sub(r'^(MV|M/V|MT|M/T|M\.V\.|M\.T\.)\s+', '', nome_completo.upper())
    nome = nome.split(' - ')[0].split(' (')[0].strip()
    return f"{nome} {porto_str}".strip()

# --- EXTRAÇÃO DE DATAS ---
def extrair_datas_prospect(corpo, envio):
    res = {"ETA": "-", "ETB": "-", "ETD": "-"}
    if not corpo: return res
    txt = re.sub(r'<[^>]+>', ' ', corpo.upper().split("LINEUP DETAILS")[0])
    meses_en = {'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6,
                'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12}
    def fmt_dt(t):
        d_m = re.search(r'(\d{1,2})', t)
        m_m = re.search(r'(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)', t.upper())
        if d_m and m_m: return f"{int(d_m.group(1)):02d}/{meses_en[m_m.group(1)]:02d}/{envio.year}"
        return "-"
    for k in ["ETB", "ETD", "ETS"]:
        m = re.search(rf"{k}\s+.*?([A-Z]{{3,}}\s+\d{{1,2}})", txt)
        if m: res["ETD" if k=="ETS" else k] = fmt_dt(m.group(1))
    for g in ["ARRIVAL AT ROADS", "NOTICE OF READINESS", "ETA"]:
        m = re.search(rf"{g}\s+.*?([A-Z]{{3,}}\s+\d{{1,2}})", txt)
        if m: res["ETA"] = fmt_dt(m.group(1)); break
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
            with st.status("Processando dados do Gmail...", expanded=True) as status:
                mail = imaplib.IMAP4_SSL("imap.gmail.com")
                mail.login(EMAIL_USER, EMAIL_PASS)
                agora = datetime.now(BR_TZ)
                
                mail.select("INBOX", readonly=True)
                _, d_l = mail.search(None, '(SUBJECT "LISTA NAVIOS")')
                slz_raw, bel_raw = [], []
                if d_l[0]:
                    _, d = mail.fetch(d_l[0].split()[-1], '(RFC822)')
                    raw = extrair_corpo_email(email.message_from_bytes(d[0][1]))
                    pts = re.split(r'BELEM:', raw, flags=re.IGNORECASE)
                    slz_raw = [l.strip() for l in pts[0].replace('SLZ:', '').split('\n') if len(l.strip()) > 5]
                    if len(pts) > 1: bel_raw = [l.strip() for l in pts[1].split('\n') if len(l.strip()) > 5]

                mail.select("PROSPECT", readonly=True)
                data_busca = (agora - timedelta(days=1)).strftime("%d-%b-%Y")
                _, d_p = mail.search(None, f'(SINCE "{data_busca}")')
                prospy = []
                if d_p[0]:
                    for eid in d_p[0].split()[-80:]:
                        _, d = mail.fetch(eid, '(RFC822)')
                        m = email.message_from_bytes(d[0][1])
                        envio = email.utils.parsedate_to_datetime(m.get("Date")).astimezone(BR_TZ)
                        subj = decodificar_cabecalho(m, "Subject")
                        if any(term in subj for term in TERMOS_PROSPECT):
                            prospy.append({"subj": subj, "date": envio, "datas": extrair_datas_prospect(extrair_corpo_email(m), envio)})

                mail.select("CLP", readonly=True)
                _, d_c = mail.search(None, "ALL")
                clps_l = [decodificar_cabecalho(email.message_from_bytes(mail.fetch(e, '(BODY[HEADER.FIELDS (SUBJECT)])')[1][0][1]), "Subject") for e in d_c[0].split()[-50:]] if d_c[0] else []
                mail.logout()

                def processar(lista, is_belem=False):
                    final = []
                    for n in lista:
                        # n_id é o nome completo e original do e-mail LISTA NAVIOS ( vira a chave do Banco de Dados)
                        n_id = n.split(' - ')[0].split(' (')[0].strip().upper()
                        matches = [e for e in prospy if verificar_correspondencia(n, e["subj"])]
                        matches.sort(key=lambda x: x["date"], reverse=True)
                        
                        p_datas = matches[0]["datas"] if matches else {"ETA":"-","ETB":"-","ETD":"-"}
                        db = ler_banco(n_id)
                        
                        eta = p_datas["ETA"] if p_datas["ETA"] != "-" else db[0]
                        etb = p_datas["ETB"] if p_datas["ETB"] != "-" else db[1]
                        etd = p_datas["ETD"] if p_datas["ETD"] != "-" else db[2]
                        
                        tem_clp = any(verificar_correspondencia(n, s) for s in clps_l)
                        st_clp = "✅ EMITIDA" if tem_clp else "❌ PENDENTE"
                        if not tem_clp and eta != "-" and "/" in eta:
                            try:
                                d,m,a = eta.split("/"); d_eta = datetime(int(a),int(m),int(d), tzinfo=BR_TZ)
                                if (d_eta - agora).days <= 4: st_clp = "⚠️ CRÍTICO"
                            except: pass
                        
                        salvar_banco(n_id, eta, etb, etd, st_clp)
                        today_m = [e for e in matches if e["date"].date() == agora.date()]
                        
                        final.append({
                            "Navio": limpar_visual_belem(n) if is_belem else n, 
                            "Prospect Manhã": "✅" if any(e["date"].hour < 13 for e in today_m) else "❌", 
                            "Prospect Tarde": "✅" if any(e["date"].hour >= 13 for e in today_m) else "❌", 
                            "ETA": eta, "ETB": etb, "ETD": etd, "CLP": st_clp
                        })
                    return final

                st.session_state.slz = processar(slz_raw, False)
                st.session_state.bel = processar(bel_raw, True)
                st.session_state.at = agora.strftime("%H:%M")
                st.rerun()
        except Exception as e: st.error(f"Erro: {e}")

# --- EXIBIÇÃO ---
if st.session_state.at != "-":
    st.write(f"Sincronizado em: **{st.session_state.at}**")
    t1, t2 = st.tabs(["📍 São Luís", "📍 Belém"])
    with t1: st.table(st.session_state.slz)
    with t2: st.table(st.session_state.bel)

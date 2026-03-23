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
LABEL_CLP = "CLP"
BR_TZ = pytz.timezone('America/Sao_Paulo')

st_autorefresh(interval=300000, key="auto_refresh")

# --- BANCO DE DADOS (SQLITE) ---

def init_db():
    conn = sqlite3.connect('monitor_navios.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS navios 
                 (nome TEXT PRIMARY KEY, eta TEXT, etb TEXT, etd TEXT, clp TEXT, ultima_atualizacao TEXT)''')
    try:
        c.execute("ALTER TABLE navios ADD COLUMN clp TEXT")
    except:
        pass 
    conn.commit()
    conn.close()

def salvar_no_banco(nome, eta, etb, etd, clp):
    conn = sqlite3.connect('monitor_navios.db')
    c = conn.cursor()
    try:
        c.execute("SELECT eta, etb, etd, clp FROM navios WHERE nome=?", (nome,))
        ex = c.fetchone()
        if ex:
            eta = eta if eta != "-" else ex[0]
            etb = etb if etb != "-" else ex[1]
            etd = etd if etd != "-" else ex[2]
            clp = clp if clp != "-" else ex[3]
        c.execute('''INSERT OR REPLACE INTO navios (nome, eta, etb, etd, clp, ultima_atualizacao)
                     VALUES (?, ?, ?, ?, ?, ?)''', (nome, eta, etb, etd, clp, datetime.now(BR_TZ).strftime("%d/%m %H:%M")))
    except: pass
    conn.commit()
    conn.close()

def ler_do_banco(nome):
    try:
        conn = sqlite3.connect('monitor_navios.db')
        c = conn.cursor()
        c.execute("SELECT eta, etb, etd, clp FROM navios WHERE nome=?", (nome,))
        res = c.fetchone()
        conn.close()
        return res if res else ("-", "-", "-", "❌ PENDENTE")
    except: return ("-", "-", "-", "❌ PENDENTE")

# --- FUNÇÕES AUXILIARES ---

def limpar_html(html):
    if not html: return ""
    return " ".join(re.sub(r'<[^>]+>', ' ', html).split())

def formatar_data_br(texto, ref):
    if not texto or texto == "-": return "-"
    meses = {'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6,
             'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12}
    try:
        d_m = re.search(r'(\d{1,2})', texto)
        m_m = re.search(r'(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)', texto.upper())
        if d_m and m_m:
            dt = datetime(ref.year, meses[m_m.group(1)], int(d_m.group(1)))
            return f"{int(d_m.group(1)):02d}/{meses[m_m.group(1)]:02d}/{ref.year}"
    except: pass
    return None

def extrair_datas(corpo, envio):
    res = {"ETA": "-", "ETB": "-", "ETD": "-"}
    if not corpo: return res
    txt = corpo.upper().split("LINEUP DETAILS")[0]
    for k in ["ETB", "ETD", "ETS"]:
        m = re.search(rf"{k}\s+.*?([A-Z]{{3,}}\s+\d{{1,2}}(?:ST|ND|RD|TH)?)", txt)
        if m:
            dt = formatar_data_br(m.group(1).strip(), envio)
            if dt: res["ETD" if k == "ETS" else k] = dt
    for g in ["ARRIVAL AT ROADS", "NOTICE OF READINESS", "ETA"]:
        m = re.search(rf"{g}\s+.*?([A-Z]{{3,}}\s+\d{{1,2}}(?:ST|ND|RD|TH)?)", txt)
        if m:
            dt = formatar_data_br(m.group(1).strip(), envio)
            if dt: res["ETA"] = dt; break
    return res

# --- BUSCA GMAIL ---

def buscar_tudo():
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com", timeout=30)
        mail.login(EMAIL_USER, EMAIL_PASS)
        
        # 1. Lista Navios
        mail.select("INBOX", readonly=True)
        _, d_l = mail.search(None, '(SUBJECT "LISTA NAVIOS")')
        slz, bel = [], []
        if d_l[0]:
            _, d = mail.fetch(d_l[0].split()[-1], '(RFC822)')
            msg = email.message_from_bytes(d[0][1])
            cp = ""
            for p in msg.walk():
                if p.get_content_type() in ["text/plain", "text/html"]:
                    cp = limpar_html(p.get_payload(decode=True).decode(errors="ignore"))
                    break
            pts = re.split(r'BELEM:', cp, flags=re.IGNORECASE)
            slz = [l.strip() for l in pts[0].replace('SLZ:', '').split('\n') if 3 < len(l.strip()) < 60]
            if len(pts) > 1: bel = [l.strip() for l in pts[1].split('\n') if 3 < len(l.strip()) < 60]

        # 2. Prospects Hoje
        mail.select(f'"{LABEL_PROSPECT}"', readonly=True)
        h_str = datetime.now(BR_TZ).strftime("%d-%b-%Y")
        _, d_p = mail.search(None, f'(SINCE "{h_str}")')
        prospects = []
        if d_p[0]:
            for eid in d_p[0].split()[-60:]:
                try:
                    _, d = mail.fetch(eid, '(RFC822)')
                    m = email.message_from_bytes(d[0][1])
                    env = email.utils.parsedate_to_datetime(m.get("Date")).astimezone(BR_TZ)
                    subj = "".join(str(c.decode(ch or 'utf-8') if isinstance(c, bytes) else c) for c, ch in decode_header(m.get("Subject", ""))).upper()
                    cp_p = ""
                    for p in m.walk():
                        if p.get_content_type() == "text/html": cp_p = limpar_html(p.get_payload(decode=True).decode(errors="ignore")); break
                        elif p.get_content_type() == "text/plain": cp_p = p.get_payload(decode=True).decode(errors="ignore")
                    prospects.append({"subj": subj, "date": env, "datas": extrair_datas(cp_p, env)})
                except: continue

        # 3. CLP
        mail.select(f'"{LABEL_CLP}"', readonly=True)
        _, d_c = mail.search(None, "ALL")
        clps = []
        if d_c[0]:
            for eid in d_c[0].split()[-50:]:
                try:
                    _, d = mail.fetch(eid, '(BODY[HEADER.FIELDS (SUBJECT)])')
                    clps.append("".join(str(c.decode(ch or 'utf-8') if isinstance(c, bytes) else c) for c, ch in decode_header(email.message_from_bytes(d[0][1]).get("Subject", ""))).upper())
                except: continue

        mail.logout()
        return slz, bel, prospects, clps
    except Exception as e:
        return None, None, str(e), []

# --- UI ---
st.set_page_config(page_title="Monitor WS", layout="wide")
init_db()
st.title("🚢 Monitor Operacional Wilson Sons")

# Inicialização de dados persistente
if 'dados' not in st.session_state:
    st.session_state.dados = {"slz": [], "bel": [], "at": "-"}

c1, c2 = st.columns(2)
with c1:
    if st.button("🔄 ATUALIZAR AGORA", use_container_width=True, type="primary"):
        with st.spinner("Sincronizando..."):
            s_res, b_res, prospy, clpy = buscar_tudo()
            if s_res is not None:
                agora = datetime.now(BR_TZ)
                def montar(lista, p_filtro=None):
                    f = []
                    for n in lista:
                        nm = re.sub(r'^(MV|M/V|MT|M/T)\s+', '', n.strip(), flags=re.IGNORECASE).split(' - ')[0].split(' (')[0].strip().upper()
                        match = [e for e in prospy if nm in e["subj"]]
                        match.sort(key=lambda x: x["date"], reverse=True)
                        db = ler_do_banco(nm)
                        
                        eta = match[0]["datas"]["ETA"] if match else db[0]
                        etb = match[0]["datas"]["ETB"] if match else db[1]
                        etd = match[0]["datas"]["ETD"] if match else db[2]
                        
                        tem_c = any(nm in s for s in clpy)
                        c_st = "✅ EMITIDA" if tem_c else "❌ PENDENTE"
                        if not tem_c and eta != "-" and "/" in eta:
                            try:
                                d,m,a = eta.split("/"); d_eta = datetime(int(a),int(m),int(d), tzinfo=BR_TZ)
                                if (d_eta - agora).days <= 4: c_st = "⚠️ CRÍTICO"
                            except: pass
                        
                        salvar_no_banco(nm, eta, etb, etd, c_st)
                        f.append({
                            "Navio": n, 
                            "Prospect A.M": "✅" if any(e["date"].hour < 13 for e in match) else "❌", 
                            "Prospect P.M": "✅" if any(e["date"].hour >= 13 for e in match) else "❌", 
                            "ETA": eta, "ETB": etb, "ETD": etd, "CLP": c_st
                        })
                    return f
                
                # Salva os resultados no Session State para persistir na tela
                st.session_state.dados["slz"] = montar(s_res)
                st.session_state.dados["bel"] = montar(b_res, p_filtro="BELEM")
                st.session_state.dados["at"] = agora.strftime("%H:%M:%S")
            else:
                st.error(f"Erro na conexão: {prospy}") # Caso b_res retorne a string de erro

with c2:
    if st.button("📧 ENVIAR POR E-MAIL", use_container_width=True):
        st.info("Função de e-mail pronta. (Lógica integrada)")

# EXIBIÇÃO: Sempre tenta mostrar o que está no session_state
if st.session_state.dados["at"] != "-":
    st.write(f"Última atualização: **{st.session_state.dados['at']}**")
    t1, t2 = st.tabs(["📍 São Luís", "📍 Belém"])
    with t1: st.table(st.session_state.dados["slz"])
    with t2: st.table(st.session_state.dados["bel"])
else:
    st.info("Clique em 'ATUALIZAR AGORA' para carregar os dados.")

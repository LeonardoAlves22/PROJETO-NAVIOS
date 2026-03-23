import streamlit as st
import imaplib, email, re, smtplib, sqlite3
from email.header import decode_header
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import pytz

# 1. Configuração da Página
st.set_page_config(page_title="Monitor WS", layout="wide")

# 2. Definições
BR_TZ = pytz.timezone('America/Sao_Paulo')
EMAIL_USER = "leonardo.alves@wilsonsons.com.br"
EMAIL_PASS = "nlvr vmyv cbcq oexe"
DESTINATARIO = "leonardo.alves@wilsonsons.com.br"

# 3. Banco de Dados
def init_db():
    conn = sqlite3.connect('monitor_navios.db', check_same_thread=False)
    c = conn.cursor()
    try:
        c.execute("SELECT clp FROM navios LIMIT 1")
    except:
        c.execute("DROP TABLE IF EXISTS navios")
    c.execute('''CREATE TABLE IF NOT EXISTS navios 
                 (nome TEXT PRIMARY KEY, eta TEXT, etb TEXT, etd TEXT, clp TEXT, atualizacao TEXT)''')
    conn.commit()
    conn.close()

def ler_banco(nome):
    conn = sqlite3.connect('monitor_navios.db', check_same_thread=False)
    c = conn.cursor()
    c.execute("SELECT eta, etb, etd, clp FROM navios WHERE nome=?", (nome,))
    res = c.fetchone()
    conn.close()
    return res if res else ("-", "-", "-", "❌ PENDENTE")

def salvar_banco(nome, eta, etb, etd, clp):
    conn = sqlite3.connect('monitor_navios.db', check_same_thread=False)
    c = conn.cursor()
    c.execute("SELECT eta, etb, etd, clp FROM navios WHERE nome=?", (nome,))
    ex = c.fetchone()
    if ex:
        eta = eta if eta != "-" else ex[0]
        etb = etb if etb != "-" else ex[1]
        etd = etd if etd != "-" else ex[2]
        clp = clp if clp != "-" else ex[3]
    c.execute("INSERT OR REPLACE INTO navios VALUES (?,?,?,?,?,?)", 
              (nome, eta, etb, etd, clp, datetime.now(BR_TZ).strftime("%H:%M")))
    conn.commit()
    conn.close()

# 4. Funções de Apoio
def limpar_html(html):
    return " ".join(re.sub(r'<[^>]+>', ' ', html).split())

def extrair_datas(corpo, envio):
    res = {"ETA": "-", "ETB": "-", "ETD": "-"}
    if not corpo: return res
    txt = corpo.upper().split("LINEUP DETAILS")[0]
    meses = {'JAN':1,'FEB':2,'MAR':3,'APR':4,'MAY':5,'JUN':6,'JUL':7,'AUG':8,'SEP':9,'OCT':10,'NOV':11,'DEC':12}
    def fmt(t):
        d_m = re.search(r'(\d{1,2})', t)
        m_m = re.search(r'(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)', t.upper())
        if d_m and m_m: return f"{int(d_m.group(1)):02d}/{meses[m_m.group(1)]:02d}/{envio.year}"
        return "-"
    for k in ["ETB", "ETD", "ETS"]:
        m = re.search(rf"{k}\s+.*?([A-Z]{{3,}}\s+\d{{1,2}})", txt)
        if m: res["ETD" if k=="ETS" else k] = fmt(m.group(1))
    for g in ["ARRIVAL AT ROADS", "NOTICE OF READINESS", "ETA"]:
        m = re.search(rf"{g}\s+.*?([A-Z]{{3,}}\s+\d{{1,2}})", txt)
        if m: res["ETA"] = fmt(m.group(1)); break
    return res

# 5. Interface
st.title("🚢 Monitor Operacional Wilson Sons")
init_db()

if 'dados_slz' not in st.session_state: st.session_state.dados_slz = []
if 'dados_bel' not in st.session_state: st.session_state.dados_bel = []
if 'ultima_at' not in st.session_state: st.session_state.ultima_at = "-"

col1, col2 = st.columns(2)
with col1:
    btn_at = st.button("🔄 ATUALIZAR AGORA", use_container_width=True, type="primary")
with col2:
    btn_email = st.button("📧 ENVIAR POR E-MAIL", use_container_width=True)

if btn_at:
    try:
        with st.status("Sincronizando com Wilson Sons...", expanded=True) as status:
            mail = imaplib.IMAP4_SSL("imap.gmail.com")
            mail.login(EMAIL_USER, EMAIL_PASS)
            
            # Lista
            mail.select("INBOX", readonly=True)
            _, d_l = mail.search(None, '(SUBJECT "LISTA NAVIOS")')
            slz_b, bel_b = [], []
            if d_l[0]:
                _, d = mail.fetch(d_l[0].split()[-1], '(RFC822)')
                msg = email.message_from_bytes(d[0][1])
                cp = ""
                for p in msg.walk():
                    if p.get_content_type() in ["text/plain", "text/html"]:
                        cp = limpar_html(p.get_payload(decode=True).decode(errors="ignore"))
                        break
                pts = re.split(r'BELEM:', cp, flags=re.IGNORECASE)
                slz_b = [l.strip() for l in pts[0].replace('SLZ:', '').split('\n') if 3 < len(l.strip()) < 60]
                if len(pts) > 1: bel_b = [l.strip() for l in pts[1].split('\n') if 3 < len(l.strip()) < 60]

            # Prospects
            mail.select("PROSPECT", readonly=True)
            h_str = datetime.now(BR_TZ).strftime("%d-%b-%Y")
            _, d_p = mail.search(None, f'(SINCE "{h_str}")')
            prospy = []
            if d_p[0]:
                for eid in d_p[0].split()[-50:]:
                    _, d = mail.fetch(eid, '(RFC822)')
                    m = email.message_from_bytes(d[0][1])
                    env = email.utils.parsedate_to_datetime(m.get("Date")).astimezone(BR_TZ)
                    subj = "".join(str(c.decode(ch or 'utf-8') if isinstance(c, bytes) else c) for c, ch in decode_header(m.get("Subject", ""))).upper()
                    prospy.append({"subj": subj, "date": env, "datas": extrair_datas(limpar_html(m.get_payload(decode=True).decode(errors="ignore")) if not m.is_multipart() else "", env)})

            # CLP
            mail.select("CLP", readonly=True)
            _, d_c = mail.search(None, "ALL")
            clpy = []
            if d_c[0]:
                for eid in d_c[0].split()[-50:]:
                    _, d = mail.fetch(eid, '(BODY[HEADER.FIELDS (SUBJECT)])')
                    clpy.append("".join(str(c.decode(ch or 'utf-8') if isinstance(c, bytes) else c) for c, ch in decode_header(email.message_from_bytes(d[0][1]).get("Subject", ""))).upper())
            
            mail.logout()

            def montar(lista):
                f = []
                agora = datetime.now(BR_TZ)
                for n in lista:
                    nm = re.sub(r'^(MV|M/V|MT|M/T)\s+', '', n.strip(), flags=re.IGNORECASE).split(' - ')[0].split(' (')[0].strip().upper()
                    match = [e for e in prospy if nm in e["subj"]]
                    match.sort(key=lambda x: x["date"], reverse=True)
                    db = ler_banco(nm)
                    eta = match[0]["datas"]["ETA"] if match else db[0]
                    c_st = "✅ EMITIDA" if any(nm in s for s in clpy) else "❌ PENDENTE"
                    if "PENDENTE" in c_st and eta != "-" and "/" in eta:
                        try:
                            d,m,a = eta.split("/"); d_eta = datetime(int(a),int(m),int(d), tzinfo=BR_TZ)
                            if (d_eta - agora).days <= 4: c_st = "⚠️ CRÍTICO"
                        except: pass
                    etb_f = match[0]["datas"]["ETB"] if match else db[1]
                    etd_f = match[0]["datas"]["ETD"] if match else db[2]
                    salvar_banco(nm, eta, etb_f, etd_f, c_st)
                    f.append({"Navio": n, "Prospect Manhã": "✅" if any(e["date"].hour < 13 for e in match) else "❌", "Prospect Tarde": "✅" if any(e["date"].hour >= 13 for e in match) else "❌", "ETA": eta, "ETB": etb_f, "ETD": etd_f, "CLP": c_st})
                return f

            st.session_state.dados_slz = montar(slz_b)
            st.session_state.dados_bel = montar(bel_b)
            st.session_state.ultima_at = datetime.now(BR_TZ).strftime("%H:%M:%S")
            status.update(label="Sincronização concluída!", state="complete")
            st.rerun()
    except Exception as e:
        st.error(f"Erro: {e}")

# Exibição
if st.session_state.ultima_at != "-":
    st.write(f"Última atualização: **{st.session_state.ultima_at}**")
    t1, t2 = st.tabs(["📍 São Luís", "📍 Belém"])
    with t1: st.table(st.session_state.dados_slz)
    with t2: st.table(st.session_state.dados_bel)
else:
    st.info("Clique no botão para carregar os dados reais.")

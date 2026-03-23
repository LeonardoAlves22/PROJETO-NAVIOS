import streamlit as st
import imaplib, email, re, smtplib, sqlite3
from email.header import decode_header
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import pytz

# Configuração da página
st.set_page_config(page_title="Monitor WS", layout="wide")
BR_TZ = pytz.timezone('America/Sao_Paulo')

# --- CONFIGURAÇÕES ---
EMAIL_USER = "leonardo.alves@wilsonsons.com.br"
EMAIL_PASS = "nlvr vmyv cbcq oexe"
DESTINATARIO = "leonardo.alves@wilsonsons.com.br"

# --- BANCO DE DADOS ---
def init_db():
    conn = sqlite3.connect('monitor_navios.db')
    c = conn.cursor()
    try:
        c.execute("SELECT clp FROM navios LIMIT 1")
    except:
        c.execute("DROP TABLE IF EXISTS navios")
    c.execute('''CREATE TABLE IF NOT EXISTS navios 
                 (nome TEXT PRIMARY KEY, eta TEXT, etb TEXT, etd TEXT, clp TEXT, ultima_atualizacao TEXT)''')
    conn.commit()
    conn.close()

def salvar_no_banco(nome, eta, etb, etd, clp):
    conn = sqlite3.connect('monitor_navios.db')
    c = conn.cursor()
    c.execute("SELECT eta, etb, etd, clp FROM navios WHERE nome=?", (nome,))
    ex = c.fetchone()
    if ex:
        eta = eta if eta != "-" else ex[0]
        etb = etb if etb != "-" else ex[1]
        etd = etd if etd != "-" else ex[2]
        clp = clp if clp != "-" else ex[3]
    c.execute('''INSERT OR REPLACE INTO navios (nome, eta, etb, etd, clp, ultima_atualizacao)
                 VALUES (?, ?, ?, ?, ?, ?)''', (nome, eta, etb, etd, clp, datetime.now(BR_TZ).strftime("%d/%m %H:%M")))
    conn.commit()
    conn.close()

def ler_do_banco(nome):
    conn = sqlite3.connect('monitor_navios.db')
    c = conn.cursor()
    c.execute("SELECT eta, etb, etd, clp FROM navios WHERE nome=?", (nome,))
    res = c.fetchone()
    conn.close()
    return res if res else ("-", "-", "-", "❌ PENDENTE")

# --- FUNÇÕES DE APOIO ---
def limpar_html(html):
    return " ".join(re.sub(r'<[^>]+>', ' ', html).split())

def formatar_data(t, envio):
    d_m = re.search(r'(\d{1,2})', t)
    m_m = re.search(r'(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)', t.upper())
    meses = {'JAN':1,'FEB':2,'MAR':3,'APR':4,'MAY':5,'JUN':6,'JUL':7,'AUG':8,'SEP':9,'OCT':10,'NOV':11,'DEC':12}
    if d_m and m_m: return f"{int(d_m.group(1)):02d}/{meses[m_m.group(1)]:02d}/{envio.year}"
    return "-"

def extrair_datas(corpo, envio):
    res = {"ETA": "-", "ETB": "-", "ETD": "-"}
    if not corpo: return res
    txt = corpo.upper().split("LINEUP DETAILS")[0]
    for k in ["ETB", "ETD", "ETS"]:
        m = re.search(rf"{k}\s+.*?([A-Z]{{3,}}\s+\d{{1,2}})", txt)
        if m: res["ETD" if k=="ETS" else k] = formatar_data(m.group(1), envio)
    for g in ["ARRIVAL AT ROADS", "NOTICE OF READINESS", "ETA"]:
        m = re.search(rf"{g}\s+.*?([A-Z]{{3,}}\s+\d{{1,2}})", txt)
        if m: res["ETA"] = formatar_data(m.group(1), envio); break
    return res

# --- INTERFACE ---
st.title("🚢 Monitor Operacional Wilson Sons")
init_db()

if 'dados' not in st.session_state:
    st.session_state.dados = {"slz": [], "bel": [], "at": "-"}

c1, c2 = st.columns(2)
with c1:
    if st.button("🔄 ATUALIZAR AGORA", use_container_width=True, type="primary"):
        try:
            with st.status("Conectando ao Gmail...", expanded=True) as status:
                mail = imaplib.IMAP4_SSL("imap.gmail.com")
                mail.login(EMAIL_USER, EMAIL_PASS)
                
                st.write("Lendo Lista de Navios...")
                mail.select("INBOX", readonly=True)
                _, d_l = mail.search(None, '(SUBJECT "LISTA NAVIOS")')
                slz_bruto, bel_bruto = [], []
                if d_l[0]:
                    _, d = mail.fetch(d_l[0].split()[-1], '(RFC822)')
                    msg = email.message_from_bytes(d[0][1])
                    corpo_lista = ""
                    for p in msg.walk():
                        if p.get_content_type() in ["text/plain", "text/html"]:
                            corpo_lista = limpar_html(p.get_payload(decode=True).decode(errors="ignore"))
                            break
                    pts = re.split(r'BELEM:', corpo_lista, flags=re.IGNORECASE)
                    slz_bruto = [l.strip() for l in pts[0].replace('SLZ:', '').split('\n') if 3 < len(l.strip()) < 60]
                    if len(pts) > 1: bel_bruto = [l.strip() for l in pts[1].split('\n') if 3 < len(l.strip()) < 60]

                st.write("Buscando Prospects de hoje...")
                mail.select("PROSPECT", readonly=True)
                h_str = datetime.now(BR_TZ).strftime("%d-%b-%Y")
                _, d_p = mail.search(None, f'(SINCE "{h_str}")')
                prospects = []
                if d_p[0]:
                    for eid in d_p[0].split()[-50:]:
                        _, d = mail.fetch(eid, '(RFC822)')
                        m = email.message_from_bytes(d[0][1])
                        env = email.utils.parsedate_to_datetime(m.get("Date")).astimezone(BR_TZ)
                        subj = "".join(str(c.decode(ch or 'utf-8') if isinstance(c, bytes) else c) for c, ch in decode_header(m.get("Subject", ""))).upper()
                        prospects.append({"subj": subj, "date": env, "datas": extrair_datas(limpar_html(m.get_payload(decode=True).decode(errors="ignore")) if not m.is_multipart() else "", env)})

                st.write("Verificando CLPs...")
                mail.select("CLP", readonly=True)
                _, d_c = mail.search(None, "ALL")
                clps = []
                if d_c[0]:
                    for eid in d_c[0].split()[-50:]:
                        _, d = mail.fetch(eid, '(BODY[HEADER.FIELDS (SUBJECT)])')
                        clps.append("".join(str(c.decode(ch or 'utf-8') if isinstance(c, bytes) else c) for c, ch in decode_header(email.message_from_bytes(d[0][1]).get("Subject", ""))).upper())
                
                mail.logout()

                def montar(lista):
                    f = []
                    agora = datetime.now(BR_TZ)
                    for n in lista:
                        nm = re.sub(r'^(MV|M/V|MT|M/T)\s+', '', n.strip(), flags=re.IGNORECASE).split(' - ')[0].split(' (')[0].strip().upper()
                        match = [e for e in prospects if nm in e["subj"]]
                        match.sort(key=lambda x: x["date"], reverse=True)
                        db = ler_do_banco(nm)
                        eta = match[0]["datas"]["ETA"] if match else db[0]
                        c_st = "✅ EMITIDA" if any(nm in s for s in clps) else "❌ PENDENTE"
                        if "PENDENTE" in c_st and eta != "-" and "/" in eta:
                            try:
                                d,m,a = eta.split("/"); d_eta = datetime(int(a),int(m),int(d), tzinfo=BR_TZ)
                                if (d_eta - agora).days <= 4: c_st = "⚠️ CRÍTICO"
                            except: pass
                        salvar_no_banco(nm, eta, (match[0]["datas"]["ETB"] if match else db[1]), (match[0]["datas"]["ETD"] if match else db[2]), c_st)
                        f.append({"Navio": n, "Prospect Manhã": "✅" if any(e["date"].hour < 13 for e in match) else "❌", "Prospect Tarde": "✅" if any(e["date"].hour >= 13 for e in match) else "❌", "ETA": eta, "ETB": (match[0]["datas"]["ETB"] if match else db[1]), "ETD": (match[0]["datas"]["ETD"] if match else db[2]), "CLP": c_st})
                    return f

                st.session_state.dados["slz"] = montar(slz_bruto)
                st.session_state.dados["bel"] = montar(bel_bruto)
                st.session_state.dados["at"] = datetime.now(BR_TZ).strftime("%H:%M:%S")
                status.update(label="Sincronização concluída!", state="complete", expanded=False)
        except Exception as e:
            st.error(f"Erro na conexão: {e}")

with c2:
    st.button("📧 ENVIAR POR E-MAIL", use_container_width=True)

# EXIBIÇÃO
if st.session_state.dados["at"] != "-":
    st.write(f"Última atualização: **{st.session_state.dados['at']}**")
    t1, t2 = st.tabs(["📍 São Luís", "📍 Belém"])
    with t1: st.table(st.session_state.dados["slz"])
    with t2: st.table(st.session_state.dados["bel"])

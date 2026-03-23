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
    # Cria a tabela base
    c.execute('''CREATE TABLE IF NOT EXISTS navios 
                 (nome TEXT PRIMARY KEY, eta TEXT, etb TEXT, etd TEXT, ultima_atualizacao TEXT)''')
    # Tenta adicionar a coluna clp caso ela não exista (evita o OperationalError)
    try:
        c.execute("ALTER TABLE navios ADD COLUMN clp TEXT")
    except:
        pass # Coluna já existe
    conn.commit()
    conn.close()

def salvar_no_banco(nome, eta, etb, etd, clp):
    conn = sqlite3.connect('monitor_navios.db')
    c = conn.cursor()
    try:
        c.execute("SELECT eta, etb, etd, clp FROM navios WHERE nome=?", (nome,))
        existente = c.fetchone()
        if existente:
            eta = eta if eta != "-" else existente[0]
            etb = etb if etb != "-" else existente[1]
            etd = etd if etd != "-" else existente[2]
            clp = clp if clp != "-" else existente[3]
        
        c.execute('''INSERT OR REPLACE INTO navios (nome, eta, etb, etd, clp, ultima_atualizacao)
                     VALUES (?, ?, ?, ?, ?, ?)''', (nome, eta, etb, etd, clp, datetime.now(BR_TZ).strftime("%d/%m %H:%M")))
    except Exception as e:
        print(f"Erro ao salvar: {e}")
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
    except:
        return ("-", "-", "-", "❌ PENDENTE")

# --- FUNÇÕES DE APOIO ---

def limpar_html(html):
    texto = re.sub(r'<[^>]+>', ' ', html)
    return " ".join(texto.split())

def formatar_data_br(texto_data, data_ref):
    if not texto_data or texto_data == "-": return "-"
    meses_en = {'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6,
                'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12}
    try:
        dia_m = re.search(r'(\d{1,2})', texto_data)
        mes_m = re.search(r'(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)', texto_data.upper())
        if dia_m and mes_m:
            dia, mes = int(dia_m.group(1)), meses_en[mes_m.group(1)]
            ano = data_ref.year
            dt = datetime(ano, mes, dia)
            if (data_ref.replace(tzinfo=None) - dt).days > 45: return None
            return f"{dia:02d}/{mes:02d}/{ano}"
    except: pass
    return None

def extrair_datas_prospect(corpo, data_email):
    res = {"ETA": "-", "ETB": "-", "ETD": "-"}
    if not corpo: return res
    txt = corpo.upper().split("LINEUP DETAILS")[0]
    for k in ["ETB", "ETD", "ETS"]:
        m = re.search(rf"{k}\s+.*?([A-Z]{{3,}}\s+\d{{1,2}}(?:ST|ND|RD|TH)?)", txt)
        if m:
            dt = formatar_data_br(m.group(1).strip(), data_email)
            if dt: res["ETD" if k == "ETS" else k] = dt
    for g in ["ARRIVAL AT ROADS", "NOTICE OF READINESS", "NOR TENDERED", "ETA"]:
        m = re.search(rf"{g}\s+.*?([A-Z]{{3,}}\s+\d{{1,2}}(?:ST|ND|RD|TH)?)", txt)
        if m:
            dt = formatar_data_br(m.group(1).strip(), data_email)
            if dt: res["ETA"] = dt; break
    return res

# --- MOTOR DE BUSCA ---

def buscar_dados():
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com", timeout=30)
        mail.login(EMAIL_USER, EMAIL_PASS)
        mail.select("INBOX", readonly=True)
        _, d_l = mail.search(None, '(SUBJECT "LISTA NAVIOS")')
        slz, bel = [], []
        if d_l[0]:
            eid = d_l[0].split()[-1]
            _, d = mail.fetch(eid, '(RFC822)')
            msg = email.message_from_bytes(d[0][1])
            corpo = ""
            for part in msg.walk():
                if part.get_content_type() in ["text/plain", "text/html"]:
                    p = part.get_payload(decode=True).decode(errors="ignore")
                    corpo = limpar_html(p) if part.get_content_type() == "text/html" else p
                    break
            partes = re.split(r'BELEM:', corpo, flags=re.IGNORECASE)
            slz = [l.strip() for l in partes[0].replace('SLZ:', '').split('\n') if 3 < len(l.strip()) < 60]
            if len(partes) > 1:
                bel = [l.strip() for l in partes[1].split('\n') if 3 < len(l.strip()) < 60]

        mail.select(f'"{LABEL_PROSPECT}"', readonly=True)
        h_str = datetime.now(BR_TZ).strftime("%d-%b-%Y")
        _, d_p = mail.search(None, f'(SINCE "{h_str}")')
        prospects = []
        if d_p[0]:
            for eid in d_p[0].split()[-60:]:
                _, d = mail.fetch(eid, '(RFC822)')
                m = email.message_from_bytes(d[0][1])
                envio = email.utils.parsedate_to_datetime(m.get("Date")).astimezone(BR_TZ)
                subj = "".join(str(c.decode(ch or 'utf-8') if isinstance(c, bytes) else c) for c, ch in decode_header(m.get("Subject", ""))).upper()
                c_p = ""
                for part in m.walk():
                    if part.get_content_type() == "text/html":
                        c_p = limpar_html(part.get_payload(decode=True).decode(errors="ignore"))
                        break
                    elif part.get_content_type() == "text/plain":
                        c_p = part.get_payload(decode=True).decode(errors="ignore")
                prospects.append({"subj": subj, "date": envio, "datas": extrair_datas_prospect(c_p, envio)})

        mail.select(f'"{LABEL_CLP}"', readonly=True)
        _, d_c = mail.search(None, "ALL")
        clps_list = []
        if d_c[0]:
            for eid in d_c[0].split()[-50:]:
                _, d = mail.fetch(eid, '(BODY[HEADER.FIELDS (SUBJECT)])')
                m_c = email.message_from_bytes(d[0][1])
                clps_list.append("".join(str(c.decode(ch or 'utf-8') if isinstance(c, bytes) else c) for c, ch in decode_header(m_c.get("Subject", ""))).upper())

        mail.logout()
        return slz, bel, prospects, clps_list
    except Exception as e: return None, None, str(e), []

# --- UI ---
st.set_page_config(page_title="Monitor WS", layout="wide")
init_db()
st.title("🚢 Monitor Operacional Wilson Sons")

if 'dados' not in st.session_state: st.session_state.dados = {"slz": [], "bel": [], "at": "-"}

col1, col2 = st.columns(2)
with col1:
    if st.button("🔄 ATUALIZAR AGORA", use_container_width=True, type="primary"):
        with st.spinner("Sincronizando..."):
            slz_res, bel_res, prospects, clps = buscar_dados()
            if slz_res is not None:
                agora = datetime.now(BR_TZ)
                def montar(lista):
                    res = []
                    for n in lista:
                        nome = re.sub(r'^(MV|M/V|MT|M/T)\s+', '', n.strip(), flags=re.IGNORECASE).split(' - ')[0].split(' (')[0].strip().upper()
                        match = [e for e in prospects if nome in e["subj"]]
                        match.sort(key=lambda x: x["date"], reverse=True)
                        db = ler_do_banco(nome)
                        eta = match[0]["datas"]["ETA"] if match else db[0]
                        etb = match[0]["datas"]["ETB"] if match else db[1]
                        etd = match[0]["datas"]["ETD"] if match else db[2]
                        tem_clp = any(nome in s for s in clps)
                        clp_st = "✅ EMITIDA" if tem_clp else "❌ PENDENTE"
                        if not tem_clp and eta != "-":
                            try:
                                d, m, a = eta.split("/")
                                d_eta = datetime(int(a), int(m), int(d), tzinfo=BR_TZ)
                                if (d_eta - agora).days <= 4: clp_st = "⚠️ CRÍTICO"
                            except: pass
                        salvar_no_banco(nome, eta, etb, etd, clp_st)
                        res.append({"Navio": n, "AM": "✅" if any(e["date"].hour < 13 for e in match) else "❌", "PM": "✅" if any(e["date"].hour >= 13 for e in match) else "❌", "ETA": eta, "ETB": etb, "ETD": etd, "CLP": clp_st})
                    return res
                st.session_state.dados = {"slz": montar(slz_res), "bel": montar(bel_res), "at": agora.strftime("%H:%M:%S")}

if st.session_state.dados["at"] != "-":
    st.write(f"Última atualização: **{st.session_state.dados['at']}**")
    t1, t2 = st.tabs(["📍 São Luís", "📍 Belém"])
    with t1: st.table(st.session_state.dados["slz"])
    with t2: st.table(st.session_state.dados["bel"])

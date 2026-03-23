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
BR_TZ = pytz.timezone('America/Sao_Paulo')

st_autorefresh(interval=300000, key="auto_refresh")

# --- BANCO DE DADOS (SQLITE) ---

def init_db():
    """Cria a tabela no banco de dados se não existir"""
    conn = sqlite3.connect('monitor_navios.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS navios 
                 (nome TEXT PRIMARY KEY, eta TEXT, etb TEXT, etd TEXT, ultima_atualizacao TEXT)''')
    conn.commit()
    conn.close()

def salvar_no_banco(nome, eta, etb, etd):
    """Salva ou atualiza as datas de um navio no banco"""
    if eta == "-" and etb == "-" and etd == "-": return # Não apaga dado bom com dado vazio
    conn = sqlite3.connect('monitor_navios.db')
    c = conn.cursor()
    # Pega o que já tem no banco para não sobrepor com "-"
    c.execute("SELECT eta, etb, etd FROM navios WHERE nome=?", (nome,))
    existente = c.fetchone()
    
    # Se já existe, só atualiza o que não for "-"
    if existente:
        eta = eta if eta != "-" else existente[0]
        etb = etb if etb != "-" else existente[1]
        etd = etd if etd != "-" else existente[2]

    c.execute('''INSERT OR REPLACE INTO navios (nome, eta, etb, etd, ultima_atualizacao)
                 VALUES (?, ?, ?, ?, ?)''', (nome, eta, etb, etd, datetime.now(BR_TZ).strftime("%d/%m %H:%M")))
    conn.commit()
    conn.close()

def ler_do_banco(nome):
    """Lê as últimas datas salvas de um navio"""
    conn = sqlite3.connect('monitor_navios.db')
    c = conn.cursor()
    c.execute("SELECT eta, etb, etd FROM navios WHERE nome=?", (nome,))
    res = c.fetchone()
    conn.close()
    return res if res else ("-", "-", "-")

# --- FUNÇÕES DE APOIO ---

def limpar_html(html):
    texto = re.sub(r'<[^>]+>', ' ', html)
    return " ".join(texto.split())

def formatar_data_br(texto_data, data_referencia):
    if not texto_data or texto_data == "-": return "-"
    meses_en = {'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6,
                'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12}
    try:
        dia_match = re.search(r'(\d{1,2})', texto_data)
        mes_match = re.search(r'(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)', texto_data.upper())
        if dia_match and mes_match:
            dia, mes = int(dia_match.group(1)), meses_en[mes_match.group(1)]
            ano = data_referencia.year
            data_dt = datetime(ano, mes, dia)
            if (data_referencia.replace(tzinfo=None) - data_dt).days > 45: return None
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
        mail = imaplib.IMAP4_SSL("imap.gmail.com", timeout=25)
        mail.login(EMAIL_USER, EMAIL_PASS)
        
        # 1. LISTA NAVIOS
        mail.select("INBOX", readonly=True)
        _, data_lista = mail.search(None, '(SUBJECT "LISTA NAVIOS")')
        slz_bruto, bel_bruto = [], []
        if data_lista[0]:
            eid = data_lista[0].split()[-1]
            _, d = mail.fetch(eid, '(RFC822)')
            msg = email.message_from_bytes(d[0][1])
            corpo_l = ""
            for part in msg.walk():
                if part.get_content_type() in ["text/plain", "text/html"]:
                    p = part.get_payload(decode=True).decode(errors="ignore")
                    corpo_l = limpar_html(p) if part.get_content_type() == "text/html" else p
                    break
            partes = re.split(r'BELEM:', corpo_l, flags=re.IGNORECASE)
            slz_bruto = [l.strip() for l in partes[0].replace('SLZ:', '').split('\n') if 3 < len(l.strip()) < 60]
            if len(partes) > 1:
                bel_bruto = [l.strip() for l in partes[1].split('\n') if 3 < len(l.strip()) < 60]

        # 2. PROSPECTS (Volta a buscar apenas de HOJE para ser rápido)
        mail.select(f'"{LABEL_PROSPECT}"', readonly=True)
        hoje_str = datetime.now(BR_TZ).strftime("%d-%b-%Y")
        _, data_p = mail.search(None, f'(SINCE "{hoje_str}")')
        
        prospects_list = []
        if data_p[0]:
            ids = data_p[0].split()[-60:] 
            for eid in ids:
                try:
                    _, d = mail.fetch(eid, '(RFC822)')
                    m = email.message_from_bytes(d[0][1])
                    envio_br = email.utils.parsedate_to_datetime(m.get("Date")).astimezone(BR_TZ)
                    subj = "".join(str(c.decode(ch or 'utf-8') if isinstance(c, bytes) else c) for c, ch in decode_header(m.get("Subject", ""))).upper()
                    corpo_p = ""
                    for part in m.walk():
                        if part.get_content_type() == "text/html":
                            corpo_p = limpar_html(part.get_payload(decode=True).decode(errors="ignore"))
                            break
                        elif part.get_content_type() == "text/plain":
                            corpo_p = part.get_payload(decode=True).decode(errors="ignore")
                    prospects_list.append({"subj": subj, "date": envio_br, "datas": extrair_datas_prospect(corpo_p, envio_br)})
                except: continue
        mail.logout()
        return slz_bruto, bel_bruto, prospects_list
    except Exception as e: return None, None, str(e)

# --- UI ---
st.set_page_config(page_title="Monitor WS", layout="wide")
init_db() # Garante que o banco de dados existe

st.title("🚢 Monitor Operacional Wilson Sons")

if 'dados' not in st.session_state: st.session_state.dados = {"slz": [], "bel": [], "at": "-"}

col1, col2 = st.columns(2)
with col1:
    if st.button("🔄 ATUALIZAR AGORA", use_container_width=True, type="primary"):
        with st.spinner("Sincronizando Gmail e Banco de Dados..."):
            slz_res, bel_res, prospects = buscar_dados()
            if slz_res is not None:
                def montar(lista, p_filtro=None):
                    res = []
                    for n in lista:
                        nome = re.sub(r'^(MV|M/V|MT|M/T)\s+', '', n.strip(), flags=re.IGNORECASE).split(' - ')[0].split(' (')[0].strip().upper()
                        porto = re.search(r'\((.*?)\)', n).group(1).strip().upper() if '(' in n else None
                        match = [e for e in prospects if nome in e["subj"]]
                        if p_filtro and porto and len(match) > 1:
                            m_p = [e for e in match if porto in e["subj"]]
                            if m_p: match = m_p
                        
                        match.sort(key=lambda x: x["date"], reverse=True)
                        
                        # Se achou e-mail hoje, salva no banco. Se não achou, lê do banco.
                        if match:
                            info_hoje = match[0]["datas"]
                            salvar_no_banco(nome, info_hoje["ETA"], info_hoje["ETB"], info_hoje["ETD"])
                            eta, etb, etd = info_hoje["ETA"], info_hoje["ETB"], info_hoje["ETD"]
                        else:
                            eta, etb, etd = ler_do_banco(nome)

                        res.append({"Navio": f"{nome} ({porto})" if porto else nome,
                                    "AM": "✅" if any(e["date"].hour < 13 for e in match) else "❌",
                                    "PM": "✅" if any(e["date"].hour >= 13 for e in match) else "❌",
                                    "ETA/Arrival": eta, "ETB": etb, "ETD": etd})
                    return res
                st.session_state.dados = {"slz": montar(slz_res), "bel": montar(bel_res, p_filtro="BELEM"), "at": datetime.now(BR_TZ).strftime("%H:%M:%S")}

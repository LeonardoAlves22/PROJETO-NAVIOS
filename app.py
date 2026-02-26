import streamlit as st
import imaplib, email, re, smtplib
import pandas as pd
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from email.header import decode_header
from streamlit_autorefresh import st_autorefresh

# --- CONFIGURAÇÕES ---
EMAIL_USER = "leonardo.alves@wilsonsons.com.br"
EMAIL_PASS = "ighf pteu xtfx fkom"
DESTINO = "leonardo.alves@wilsonsons.com.br"

REMS = {
    "SLZ": ["operation.sluis@wilsonsons.com.br", "agencybrazil@cargill.com"],
    "BEL": ["operation.belem@wilsonsons.com.br"]
}

HORARIOS = ["09:30", "10:00", "11:00", "11:30", "16:00", "17:00", "17:30"]

st_autorefresh(interval=60000, key="v18_stinger_fix")

# --- MOTOR DE BUSCA ---

def conectar_gmail():
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(EMAIL_USER, EMAIL_PASS)
        for pasta in ['"[Gmail]/All Mail"', 'INBOX']:
            if mail.select(pasta, readonly=True)[0] == 'OK':
                return mail
        return None
    except:
        return None

def limpar_nome_simples(txt):
    """Limpeza agressiva para garantir match entre 'MV STINGER' e 'STINGER'"""
    n = re.sub(r'^MV\s+|^M/V\s+|^MT\s+|^M/T\s+', '', txt.strip(), flags=re.IGNORECASE)
    # Remove tudo após o primeiro espaço, hífen ou parêntese para pegar o nome core
    n = re.split(r'\s|\-|\(|\/', n)[0]
    return n.strip().upper()

def obter_lista_navios(mail):
    _, data = mail.search(None, '(SUBJECT "LISTA NAVIOS")')
    if not data[0]: return [], []
    id_recente = data[0].split()[-1]
    _, bytes_data = mail.fetch(id_recente, '(RFC822)')
    msg = email.message_from_bytes(bytes_data[0][1])
    corpo = ""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                corpo = part.get_payload(decode=True).decode(errors='ignore')
                break
    else:
        corpo = msg.get_payload(decode=True).decode(errors='ignore')
    
    corpo = re.split(r'Regards|Best regards', corpo, flags=re.IGNORECASE)[0]
    partes = re.split(r'BELEM:', corpo, flags=re.IGNORECASE)
    slz = [n.strip() for n in partes[0].replace('SLZ:', '').split('\n') if n.strip() and "SLZ:" not in n.upper()]
    bel = [n.strip() for n in partes[1].split('\n') if n.strip()] if len(partes) > 1 else []
    return slz, bel

def buscar_emails_hoje(mail):
    hoje = (datetime.now() - timedelta(hours=3)).strftime("%d-%b-%Y")
    _, data = mail.search(None, f'(SINCE "{hoje}")')
    lista = []
    if data[0]:
        for eid in data[0].split()[-200:]:
            try:
                _, d = mail.fetch(eid, '(BODY[HEADER.FIELDS (SUBJECT DATE FROM)])')
                m = email.message_from_bytes(d[0][1])
                subj = "".join(str(c.decode(ch or 'utf-8') if isinstance(c, bytes) else c) for c, ch in decode_header(m.get("Subject", ""))).upper()
                envio = email.utils.parsedate_to_datetime(m.get("Date")).replace(tzinfo=None)
                lista.append({"subj": subj, "from": m.get("From", "").lower(), "date": envio})
            except: continue
    return lista

# --- LOGICA DE EXIBIÇÃO ---

def executar():
    mail = conectar_gmail()
    if not mail: return
    slz_bruto, bel_bruto = obter_lista_navios(mail)
    db_emails = buscar_emails_hoje(mail)
    mail.logout()

    agora_br = datetime.now() - timedelta(hours=3)
    corte = agora_br.replace(hour=14, minute=0, second=0)
    
    # Identificar duplicados em Belém/VDC para sufixo
    nomes_bel_vdc_core = [limpar_nome_simples(n) for n in bel_bruto]
    
    res_slz, res_bel = [], []

    # Processar São Luís
    for n in slz_bruto:
        nome_core = limpar_nome_simples(n)
        m_g = [e for e in db_emails if nome_core in e["subj"] and any(r in e["from"] for r in REMS["SLZ"])]
        m_t = [e for e in m_g if e["date"] >= corte]
        res_slz.append({"Navio": nome_core, "Manhã": "✅" if m_g else "❌", "Tarde": "✅" if m_t else "❌"})

    # Processar Belém / VDC
    for n in bel_bruto:
        nome_core = limpar_nome_simples(n)
        is_vdc_lista = any(x in n.upper() for x in ["VILA", "VDC", "BARCARENA"])
        
        exibicao = nome_core
        if nomes_bel_vdc_core.count(nome_core) > 1:
            exibicao = f"{nome_core} (VILA DO CONDE)" if is_vdc_lista else f"{nome_core} (BELEM)"

        m_g = []
        for e in db_emails:
            # Verifica se o NOME CORE está no assunto
            if nome_core in e["subj"] and any(r in e["from"] for r in REMS["BEL"]):
                # Verifica se o porto no assunto bate com o da lista
                is_vdc_email = any(x in e["subj"] for x in ["VILA DO CONDE", "VDC", "BARCARENA", "V. CONDE"])
                
                if is_vdc_lista == is_vdc_email:
                    m_g.append(e)

        m_t = [e for e in m_g if e["date"] >= corte]
        res_bel.append({"Navio": exibicao, "Manhã": "✅" if m_g else "❌", "Tarde": "✅" if m_t else "❌"})

    st.session_state['res_slz'] = res_slz
    st.session_state['res_bel'] = res_bel

st.set_page_config(page_title="Monitor WS", layout="wide")
st.title("🚢 Monitor Wilson Sons 2.0")
agora_br = datetime.now() - timedelta(hours=3)
st.metric("Horário Brasília", agora_br.strftime("%H:%M"))

if st.button("🔄 ATUALIZAR AGORA"):
    with st.status("Sincronizando..."):
        executar()
        st.success("Dados atualizados!")

if 'res_slz' in st.session_state:
    c1, c2 = st.columns(2)
    with c1: st.subheader("SÃO LUÍS"); st.table(st.session_state['res_slz'])
    with c2: st.subheader("BELÉM / VDC"); st.table(st.session_state['res_bel'])

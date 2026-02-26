import streamlit as st
import imaplib, email, re
from email.header import decode_header
from datetime import datetime, timedelta
from streamlit_autorefresh import st_autorefresh

# --- CONFIGURAÇÕES ---
EMAIL_USER = "leonardo.alves@wilsonsons.com.br"
EMAIL_PASS = "ighf pteu xtfx fkom"

LABEL_NAME = "PROSPECT"

st_autorefresh(interval=60000, key="monitor_fast")

# --- CONEXÃO ---
def conectar_gmail():
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(EMAIL_USER, EMAIL_PASS)

        status, _ = mail.select(f'"{LABEL_NAME}"', readonly=True)
        if status != "OK":
            st.error(f"Não foi possível acessar a label {LABEL_NAME}")
            return None

        return mail
    except Exception as e:
        st.error(f"Erro conexão Gmail: {e}")
        return None

# --- LIMPAR NOME NAVIO ---
def limpar_nome(txt):
    n = re.sub(r'^(MV|M/V|MT|M/T)\s+', '', txt.strip(), flags=re.IGNORECASE)
    n = re.sub(r'\(.*?\)', '', n)
    n = re.sub(r'\s+', ' ', n)
    return n.strip().upper()

# --- OBTER LISTA NAVIOS ---
def obter_lista_navios(mail):
    _, data = mail.search(None, '(SUBJECT "LISTA NAVIOS")')
    if not data[0]:
        return [], []

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

    slz = [n.strip() for n in partes[0].replace('SLZ:', '').split('\n')
           if n.strip() and "SLZ:" not in n.upper()]

    bel = []
    if len(partes) > 1:
        bel = [n.strip() for n in partes[1].split('\n') if n.strip()]

    return slz, bel

# --- BUSCAR EMAILS DO DIA NA LABEL PROSPECT ---
def buscar_emails_hoje(mail):
    hoje = (datetime.now() - timedelta(hours=3)).strftime("%d-%b-%Y")

    _, data = mail.search(None, f'(SINCE "{hoje}")')

    lista = []
    if data[0]:
        ids = data[0].split()[-300:]

        for eid in ids:
            try:
                _, d = mail.fetch(eid, '(BODY.PEEK[HEADER.FIELDS (SUBJECT DATE)])')
                msg = email.message_from_bytes(d[0][1])

                subj = "".join(
                    str(c.decode(ch or 'utf-8') if isinstance(c, bytes) else c)
                    for c, ch in decode_header(msg.get("Subject", ""))
                ).upper()

                envio = email.utils.parsedate_to_datetime(
                    msg.get("Date")
                ).replace(tzinfo=None)

                lista.append({
                    "subj": subj,
                    "date": envio
                })
            except:
                continue

    return lista

# --- EXECUÇÃO ---
def executar():
    mail = conectar_gmail()
    if not mail:
        return

    slz_bruto, bel_bruto = obter_lista_navios(mail)
    db_emails = buscar_emails_hoje(mail)
    mail.logout()

    agora_br = datetime.now() - timedelta(hours=3)
    corte = agora_br.replace(hour=14, minute=0, second=0)

    res_slz = []
    for n in slz_bruto:
        nome = limpar_nome(n)
        m_g = [e for e in db_emails if nome in e["subj"]]
        m_t = [e for e in m_g if e["date"] >= corte]

        res_slz.append({
            "Navio": nome,
            "Manhã": "✅" if m_g else "❌",
            "Tarde": "✅" if m_t else "❌"
        })

    res_bel = []
    for n in bel_bruto:
        nome = limpar_nome(n)
        m_g = [e for e in db_emails if nome in e["subj"]]
        m_t = [e for e in m_g if e["date"] >= corte]

        res_bel.append({
            "Navio": nome,
            "Manhã": "✅" if m_g else "❌",
            "Tarde": "✅" if m_t else "❌"
        })

    st.session_state['res_slz'] = res_slz
    st.session_state['res_bel'] = res_bel

# --- STREAMLIT ---
st.set_page_config(page_title="Monitor WS Ultra Fast", layout="wide")
st.title("🚢 Monitor Wilson Sons – PROSPECT MODE")

agora_br = datetime.now() - timedelta(hours=3)
st.metric("Horário Brasília", agora_br.strftime("%H:%M"))

if st.button("🔄 ATUALIZAR AGORA"):
    with st.status("Sincronizando..."):
        executar()
        st.success("Atualizado!")

if 'res_slz' in st.session_state:
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("SÃO LUÍS")
        st.table(st.session_state['res_slz'])
    with c2:
        st.subheader("BELÉM / VDC")
        st.table(st.session_state['res_bel'])

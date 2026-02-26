import streamlit as st
import imaplib, email, re
from email.header import decode_header
from datetime import datetime, timedelta
from streamlit_autorefresh import st_autorefresh

# --- CONFIG ---
EMAIL_USER = "leonardo.alves@wilsonsons.com.br"
EMAIL_PASS = "ighf pteu xtfx fkom"
LABEL_PROSPECT = "PROSPECT"

st_autorefresh(interval=60000, key="monitor_fast")

# --- CONEXÃO ---
def conectar_gmail():
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(EMAIL_USER, EMAIL_PASS)
        return mail
    except Exception as e:
        st.error(f"Erro Gmail: {e}")
        return None

# --- LIMPAR NOME BASE ---
def limpar_nome_base(txt):
    n = re.sub(r'^(MV|M/V|MT|M/T)\s+', '', txt.strip(), flags=re.IGNORECASE)
    n = re.split(r'\s-\s', n)[0]
    n = re.sub(r'\(.*?\)', '', n)
    n = re.sub(r'\s+', ' ', n)
    return n.strip().upper()

# --- EXTRAIR PORTO ENTRE PARÊNTESES ---
def extrair_porto(txt):
    match = re.search(r'\((.*?)\)', txt)
    if match:
        return match.group(1).strip().upper()
    return None

# --- LISTA NAVIOS ---
def obter_lista_navios(mail):
    mail.select("INBOX", readonly=True)
    _, data = mail.search(None, '(SUBJECT "LISTA NAVIOS")')

    if not data[0]:
        return []

    eid = data[0].split()[-1]
    _, d = mail.fetch(eid, '(RFC822)')
    msg = email.message_from_bytes(d[0][1])

    corpo = ""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                corpo = part.get_payload(decode=True).decode(errors='ignore')
                break
    else:
        corpo = msg.get_payload(decode=True).decode(errors='ignore')

    corpo = re.split(r'Regards|Best regards', corpo, flags=re.IGNORECASE)[0]

    linhas = [l.strip() for l in corpo.split("\n") if l.strip()]
    navios = []

    for linha in linhas:
        if "SLZ:" in linha.upper() or "BELEM:" in linha.upper():
            continue
        navios.append(linha)

    return navios

# --- EMAILS PROSPECT ---
def buscar_emails_prospect(mail):
    mail.select(f'"{LABEL_PROSPECT}"', readonly=True)

    hoje = (datetime.now() - timedelta(hours=3)).strftime("%d-%b-%Y")
    _, data = mail.search(None, f'(SINCE "{hoje}")')

    lista = []
    if data[0]:
        for eid in data[0].split()[-300:]:
            try:
                _, d = mail.fetch(eid, '(BODY.PEEK[HEADER.FIELDS (SUBJECT DATE)])')
                msg = email.message_from_bytes(d[0][1])

                subj = "".join(
                    str(c.decode(ch or 'utf-8') if isinstance(c, bytes) else c)
                    for c, ch in decode_header(msg.get("Subject", ""))
                ).upper()

                envio = email.utils.parsedate_to_datetime(msg.get("Date")).replace(tzinfo=None)

                lista.append({"subj": subj, "date": envio})
            except:
                continue

    return lista

# --- EXECUÇÃO ---
def executar():
    mail = conectar_gmail()
    if not mail:
        return

    navios_lista = obter_lista_navios(mail)
    emails = buscar_emails_prospect(mail)
    mail.logout()

    resultados = []

    for item in navios_lista:
        nome_base = limpar_nome_base(item)
        porto = extrair_porto(item)

        if porto:
            criterio_subject = f"{nome_base} - {porto}"
        else:
            criterio_subject = nome_base

        emails_navio = [e for e in emails if criterio_subject in e["subj"]]

        manha = any(e["date"].hour < 12 for e in emails_navio)
        tarde = any(e["date"].hour >= 14 for e in emails_navio)

        resultados.append({
            "Navio": f"{nome_base} ({porto})" if porto else nome_base,
            "Manhã": "✅" if manha else "❌",
            "Tarde": "✅" if tarde else "❌"
        })

    st.session_state['resultado'] = resultados

# --- STREAMLIT ---
st.set_page_config(page_title="Monitor WS", layout="wide")
st.title("🚢 Monitor Wilson Sons – Diferenciação por Porto")

if st.button("🔄 Atualizar"):
    executar()

if 'resultado' in st.session_state:
    st.table(st.session_state['resultado'])

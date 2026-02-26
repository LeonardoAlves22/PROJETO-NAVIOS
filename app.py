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

# --- LIMPAR NOME NAVIO (VERSÃO FINAL) ---
def limpar_nome(txt):
    # Remove prefixos MV / M/V / MT
    n = re.sub(r'^(MV|M/V|MT|M/T)\s+', '', txt.strip(), flags=re.IGNORECASE)

    # Remove tudo após hífen
    n = re.split(r'\s-\s', n)[0]

    # Remove VOY / V. / V número no final (ex: V.26062, V 26062, VOY 01)
    n = re.sub(r'\s+(V|VOY)\.?\s*\d+.*$', '', n, flags=re.IGNORECASE)

    # Remove conteúdo entre parênteses
    n = re.sub(r'\(.*?\)', '', n)

    # Remove múltiplos espaços
    n = re.sub(r'\s+', ' ', n)

    return n.strip().upper()

# --- EXTRAIR PORTO ENTRE () ---
def extrair_porto(txt):
    m = re.search(r'\((.*?)\)', txt)
    return m.group(1).strip().upper() if m else None

# --- LISTA NAVIOS ---
def obter_lista_navios(mail):
    mail.select("INBOX", readonly=True)
    _, data = mail.search(None, '(SUBJECT "LISTA NAVIOS")')

    if not data[0]:
        return [], []

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
    partes = re.split(r'BELEM:', corpo, flags=re.IGNORECASE)

    slz = [n.strip() for n in partes[0].replace('SLZ:', '').split('\n') if n.strip()]
    bel = [n.strip() for n in partes[1].split('\n') if n.strip()] if len(partes) > 1 else []

    return slz, bel

# --- BUSCAR EMAILS PROSPECT ---
def buscar_emails(mail):
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

# --- EXECUTAR ---
def executar():
    mail = conectar_gmail()
    if not mail:
        return

    slz_lista, bel_lista = obter_lista_navios(mail)
    emails = buscar_emails(mail)
    mail.logout()

    nomes_base_bel = [limpar_nome(n) for n in bel_lista]

    def analisar(lista, is_belem=False):
        resultado = []

        for item in lista:
            nome_base = limpar_nome(item)
            porto = extrair_porto(item)

            # Diferenciar navio repetido em Belém por porto
            if is_belem and nomes_base_bel.count(nome_base) > 1 and porto:
                emails_navio = [
                    e for e in emails
                    if nome_base in e["subj"] and porto in e["subj"]
                ]
            else:
                emails_navio = [
                    e for e in emails
                    if nome_base in e["subj"]
                ]

            manha = any(e["date"].hour < 12 for e in emails_navio)
            tarde = any(e["date"].hour >= 14 for e in emails_navio)

            resultado.append({
                "Navio": f"{nome_base} ({porto})" if porto else nome_base,
                "Manhã": "✅" if manha else "❌",
                "Tarde": "✅" if tarde else "❌"
            })

        return resultado

    st.session_state['slz'] = analisar(slz_lista)
    st.session_state['bel'] = analisar(bel_lista, True)

# --- STREAMLIT ---
st.set_page_config(page_title="Monitor WS", layout="wide")
st.title("🚢 Monitor Wilson Sons")

if st.button("🔄 Atualizar"):
    executar()

if 'slz' in st.session_state:
    c1, c2 = st.columns(2)

    with c1:
        st.subheader("Filial São Luís")
        st.table(st.session_state['slz'])

    with c2:
        st.subheader("Filial Belém")
        st.table(st.session_state['bel'])

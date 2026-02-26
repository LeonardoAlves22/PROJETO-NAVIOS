import streamlit as st
import imaplib, email, re
from email.header import decode_header
from datetime import datetime, timedelta
from streamlit_autorefresh import st_autorefresh

# --- CONFIGURAÇÕES ---
EMAIL_USER = "leonardo.alves@wilsonsons.com.br"
EMAIL_PASS = "ighf pteu xtfx fkom"

REMS = {
    "SLZ": ["operation.sluis@wilsonsons.com.br", "agencybrazil@cargill.com"],
    "BEL": ["operation.belem@wilsonsons.com.br"]
}

st_autorefresh(interval=60000, key="monitor_fast")

# --- CONEXÃO GMAIL ---
def conectar_gmail():
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(EMAIL_USER, EMAIL_PASS)

        status, _ = mail.select('"[Gmail]/All Mail"', readonly=True)
        if status != "OK":
            status, _ = mail.select("INBOX", readonly=True)
            if status != "OK":
                return None

        return mail
    except Exception as e:
        st.error(f"Erro ao conectar Gmail: {e}")
        return None

# --- LIMPEZA NOME NAVIO (CORRIGIDA) ---
def limpar_nome_simples(txt):
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

# --- BUSCAR EMAILS ---
def buscar_emails_hoje(mail):
    hoje = (datetime.now() - timedelta(hours=3)).strftime("%d-%b-%Y")

    filtros = []
    for grupo in REMS.values():
        for remetente in grupo:
            filtros.append(f'(FROM "{remetente}")')

    criterio = f'(SINCE "{hoje}" {" ".join(filtros)})'
    _, data = mail.search(None, criterio)

    lista = []
    if data[0]:
        ids = data[0].split()[-200:]
        if ids:
            _, dados = mail.fetch(",".join(ids),
                                  '(BODY.PEEK[HEADER.FIELDS (SUBJECT DATE FROM)])')

            for i in range(0, len(dados), 2):
                try:
                    raw = dados[i][1]
                    msg = email.message_from_bytes(raw)

                    subj = "".join(
                        str(c.decode(ch or 'utf-8') if isinstance(c, bytes) else c)
                        for c, ch in decode_header(msg.get("Subject", ""))
                    ).upper()

                    envio = email.utils.parsedate_to_datetime(
                        msg.get("Date")
                    ).replace(tzinfo=None)

                    lista.append({
                        "subj": subj,
                        "from": msg.get("From", "").lower(),
                        "date": envio
                    })
                except:
                    continue

    return lista

# --- EXECUÇÃO PRINCIPAL ---
def executar():
    mail = conectar_gmail()
    if not mail:
        return

    slz_bruto, bel_bruto = obter_lista_navios(mail)
    db_emails = buscar_emails_hoje(mail)
    mail.logout()

    agora_br = datetime.now() - timedelta(hours=3)
    corte = agora_br.replace(hour=14, minute=0, second=0)

    nomes_bel_core = [limpar_nome_simples(n) for n in bel_bruto]

    res_slz = []
    for n in slz_bruto:
        nome_core = limpar_nome_simples(n)
        m_g = [e for e in db_emails if nome_core in e["subj"] and any(r in e["from"] for r in REMS["SLZ"])]
        m_t = [e for e in m_g if e["date"] >= corte]

        res_slz.append({
            "Navio": nome_core,
            "Manhã": "✅" if m_g else "❌",
            "Tarde": "✅" if m_t else "❌"
        })

    res_bel = []
    for n in bel_bruto:
        nome_core = limpar_nome_simples(n)
        is_vdc_lista = any(x in n.upper() for x in ["VILA", "VDC", "BARCARENA"])

        exibicao = nome_core
        if nomes_bel_core.count(nome_core) > 1:
            exibicao = f"{nome_core} (VDC)" if is_vdc_lista else f"{nome_core} (BELEM)"

        m_g = [e for e in db_emails if nome_core in e["subj"] and any(r in e["from"] for r in REMS["BEL"])]
        m_t = [e for e in m_g if e["date"] >= corte]

        res_bel.append({
            "Navio": exibicao,
            "Manhã": "✅" if m_g else "❌",
            "Tarde": "✅" if m_t else "❌"
        })

    st.session_state['res_slz'] = res_slz
    st.session_state['res_bel'] = res_bel

# --- STREAMLIT UI ---
st.set_page_config(page_title="Monitor WS FAST", layout="wide")
st.title("🚢 Monitor Wilson Sons 3.1")

agora_br = datetime.now() - timedelta(hours=3)
st.metric("Horário Brasília", agora_br.strftime("%H:%M"))

if st.button("🔄 ATUALIZAR AGORA"):
    with st.status("Sincronizando..."):
        executar()
        st.success("Dados atualizados!")

if 'res_slz' in st.session_state:
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("SÃO LUÍS")
        st.table(st.session_state['res_slz'])
    with c2:
        st.subheader("BELÉM / VDC")
        st.table(st.session_state['res_bel'])

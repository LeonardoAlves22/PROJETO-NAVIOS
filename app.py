import streamlit as st
import imaplib, email, re, smtplib
from email.header import decode_header
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from streamlit_autorefresh import st_autorefresh

# --- CONFIG ---
EMAIL_USER = "leonardo.alves@wilsonsons.com.br"
EMAIL_PASS = "ighf pteu xtfx fkom"
DESTINO = "leonardo.alves@wilsonsons.com.br"
LABEL_PROSPECT = "PROSPECT"

HORARIOS = ["09:30", "10:00", "11:00", "11:30", "16:00", "17:00", "17:30", "23:28"]

st_autorefresh(interval=60000, key="monitor_auto")  # roda a cada 60s

# --- CONEXÃO IMAP ---
def conectar_gmail():
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(EMAIL_USER, EMAIL_PASS)
        return mail
    except Exception as e:
        st.error(f"Erro Gmail: {e}")
        return None

# --- LIMPAR NOME ---
def limpar_nome(txt):
    n = re.sub(r'^(MV|M/V|MT|M/T)\s+', '', txt.strip(), flags=re.IGNORECASE)
    n = re.split(r'\s-\s', n)[0]
    n = re.sub(r'\s+(V|VOY)\.?\s*\d+.*$', '', n, flags=re.IGNORECASE)
    n = re.sub(r'\(.*?\)', '', n)
    n = re.sub(r'\s+', ' ', n)
    return n.strip().upper()

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
                corpo = part.get_payload(decode=True).decode(errors="ignore")
                break
    else:
        corpo = msg.get_payload(decode=True).decode(errors="ignore")

    corpo = re.split(r'Regards|Best regards', corpo, flags=re.IGNORECASE)[0]
    partes = re.split(r'BELEM:', corpo, flags=re.IGNORECASE)

    slz = [n.strip() for n in partes[0].replace('SLZ:', '').split('\n') if n.strip()]
    bel = [n.strip() for n in partes[1].split('\n') if n.strip()] if len(partes) > 1 else []

    return slz, bel

# --- BUSCAR EMAILS ---
def buscar_emails(mail):
    mail.select(f'"{LABEL_PROSPECT}"', readonly=True)
    hoje = (datetime.now() - timedelta(hours=3)).strftime("%d-%b-%Y")
    _, data = mail.search(None, f'(SINCE "{hoje}")')

    lista = []
    if data[0]:
        for eid in data[0].split()[-200:]:
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

# --- EMAIL ---
def enviar_email(res_slz, res_bel):
    try:
        msg = MIMEMultipart()
        msg["From"] = EMAIL_USER
        msg["To"] = DESTINO
        msg["Subject"] = "Monitor Prospects - Status"

        def linhas(lista):
            html = ""
            for r in lista:
                cor_m = "#28a745" if r["Manhã"] == "✅" else "#dc3545"
                cor_t = "#28a745" if r["Tarde"] == "✅" else "#dc3545"
                html += f"""
                <tr>
                    <td style="padding:6px;border-bottom:1px solid #ddd">{r['Navio']}</td>
                    <td style="text-align:center;background:{cor_m};color:white">{r['Manhã']}</td>
                    <td style="text-align:center;background:{cor_t};color:white">{r['Tarde']}</td>
                </tr>
                """
            return html

        html = f"""
        <html>
        <body style="font-family:Arial;background:#eaf3ff;padding:20px">
        <h2 style="background:#2b6cb0;color:white;padding:10px;border-radius:6px">🚢 Monitor Prospects</h2>
        <table width="100%"><tr>
        <td width="50%">
        <h3>Filial São Luís</h3>
        <table border="1" width="100%" style="border-collapse:collapse">
        <tr><th>Navio</th><th>Manhã</th><th>Tarde</th></tr>
        {linhas(res_slz)}
        </table>
        </td>
        <td width="50%">
        <h3>Filial Belém</h3>
        <table border="1" width="100%" style="border-collapse:collapse">
        <tr><th>Navio</th><th>Manhã</th><th>Tarde</th></tr>
        {linhas(res_bel)}
        </table>
        </td>
        </tr></table>
        </body></html>
        """

        msg.attach(MIMEText(html, "html"))

        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(EMAIL_USER, EMAIL_PASS)
        server.send_message(msg)
        server.quit()

        st.success("📧 Email enviado automaticamente!")

    except Exception as e:
        st.error(f"Erro email: {e}")

# --- EXECUTAR ---
def executar():
    mail = conectar_gmail()
    if not mail:
        return

    slz, bel = obter_lista_navios(mail)
    emails = buscar_emails(mail)
    mail.logout()

    nomes_base_bel = [limpar_nome(n) for n in bel]

    def analisar(lista, is_belem=False):
        res = []
        for item in lista:
            nome = limpar_nome(item)
            porto = extrair_porto(item)

            if is_belem and nomes_base_bel.count(nome) > 1 and porto:
                emails_navio = [e for e in emails if nome in e["subj"] and porto in e["subj"]]
            else:
                emails_navio = [e for e in emails if nome in e["subj"]]

            manha = any(e["date"].hour < 12 for e in emails_navio)
            tarde = any(e["date"].hour >= 14 for e in emails_navio)

            res.append({"Navio": f"{nome} ({porto})" if porto else nome,
                        "Manhã": "✅" if manha else "❌",
                        "Tarde": "✅" if tarde else "❌"})
        return res

    res_slz = analisar(slz)
    res_bel = analisar(bel, True)

    st.session_state['slz'] = res_slz
    st.session_state['bel'] = res_bel

    enviar_email(res_slz, res_bel)

# --- AUTO DISPARO ---
agora = (datetime.now() - timedelta(hours=3)).strftime("%H:%M")

if "ultimo_envio" not in st.session_state:
    st.session_state["ultimo_envio"] = ""

if agora in HORARIOS and st.session_state["ultimo_envio"] != agora:
    executar()
    st.session_state["ultimo_envio"] = agora

# --- INTERFACE ---
st.title("🚢 Monitor Wilson Sons - Auto")

if 'slz' in st.session_state:
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("São Luís")
        st.table(st.session_state['slz'])
    with c2:
        st.subheader("Belém")
        st.table(st.session_state['bel'])

import streamlit as st
import imaplib, email, re, smtplib
from email.header import decode_header
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from streamlit_autorefresh import st_autorefresh
import pytz

# --- CONFIG ---
EMAIL_USER = "leonardo.alves@wilsonsons.com.br"
EMAIL_PASS = "nlvr vmyv cbcq oexe"
DESTINOS = ["leonardo.alves@wilsonsons.com.br"]
LABEL_PROSPECT = "PROSPECT"
HORARIOS = ["09:30","10:00","11:00","11:30","16:00","17:00","17:30"]

# Timezone Brasil
BR_TZ = pytz.timezone('America/Sao_Paulo')

st_autorefresh(interval=60000, key="auto_refresh")

# --- AUXILIARES ---
def conectar_gmail():
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(EMAIL_USER, EMAIL_PASS)
        return mail
    except Exception as e:
        st.error(f"Erro Gmail: {e}")
        return None

def limpar_nome(txt):
    n = re.sub(r'^(MV|M/V|MT|M/T)\s+', '', txt.strip(), flags=re.IGNORECASE)
    n = re.split(r'\s-\s', n)[0]
    n = re.sub(r'\s+(V|VOY)\.?\s*\d+.*$', '', n, flags=re.IGNORECASE)
    n = re.sub(r'\(.*?\)', '', n)
    return n.strip().upper()

def extrair_porto(txt):
    m = re.search(r'\((.*?)\)', txt)
    return m.group(1).strip().upper() if m else None

def extrair_datas(corpo):
    res = {"ETA": "-", "ETB": "-", "ETD": "-"}
    if not corpo: return res
    for k in res.keys():
        m = re.search(rf"{k}\s*[:\-]?\s*(\d{{1,2}}[/|-](?:\d{{1,2}}|[A-Z]{{3}})[^ \n]*)", corpo, re.IGNORECASE)
        if m: res[k] = m.group(1).strip().upper()
    return res

# --- LISTA NAVIOS (INBOX) ---
def obter_lista_navios(mail):
    mail.select("INBOX", readonly=True)
    _, data = mail.search(None, '(SUBJECT "LISTA NAVIOS")')
    if not data[0]: return [], []

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

    partes = re.split(r'BELEM:', corpo, flags=re.IGNORECASE)
    slz = [n.strip() for n in partes[0].replace('SLZ:', '').split('\n') if n.strip() and len(n) > 3]
    bel = [n.strip() for n in partes[1].split('\n') if n.strip() and len(n) > 3] if len(partes) > 1 else []
    return slz, bel

# --- BUSCAR EMAILS (PROSPECT) ---
def buscar_emails(mail):
    # Tenta selecionar a label, se não existir, vai na Inbox
    status, _ = mail.select(f'"{LABEL_PROSPECT}"', readonly=True)
    if status != 'OK': mail.select("INBOX", readonly=True)
    
    # Busca e-mails de hoje e ontem (para garantir fuso)
    hoje_imap = (datetime.now(BR_TZ) - timedelta(days=1)).strftime("%d-%b-%Y")
    _, data = mail.search(None, f'(SINCE "{hoje_imap}")')

    lista = []
    if data[0]:
        for eid in data[0].split()[-100:]:
            try:
                _, d = mail.fetch(eid, '(RFC822)')
                msg = email.message_from_bytes(d[0][1])
                
                # Fuso Horário corrigido para o e-mail das 00:10
                envio_utc = email.utils.parsedate_to_datetime(msg.get("Date"))
                envio_br = envio_utc.astimezone(BR_TZ)

                # Só aceita se for do dia atual (Brasília)
                if envio_br.date() != datetime.now(BR_TZ).date():
                    continue

                subj = "".join(str(c.decode(ch or 'utf-8') if isinstance(c, bytes) else c)
                               for c, ch in decode_header(msg.get("Subject", ""))).upper()

                corpo = ""
                if msg.is_multipart():
                    for part in msg.walk():
                        if part.get_content_type() == "text/plain":
                            corpo = part.get_payload(decode=True).decode(errors="ignore")
                else:
                    corpo = msg.get_payload(decode=True).decode(errors="ignore")

                lista.append({
                    "subj": subj,
                    "date": envio_br,
                    "info": extrair_datas(corpo)
                })
            except: continue
    return lista

# --- GERAR RELATÓRIO ---
def gerar_relatorio():
    mail = conectar_gmail()
    if not mail: return

    slz_bruto, bel_bruto = obter_lista_navios(mail)
    emails = buscar_emails(mail)
    mail.logout()

    agora_br = datetime.now(BR_TZ)
    nomes_bel = [limpar_nome(n) for n in bel_bruto]

    def analisar(lista, is_bel=False):
        res = []
        for item in lista:
            nome = limpar_nome(item)
            porto = extrair_porto(item)
            
            # Filtro de e-mails do navio
            if is_bel and nomes_bel.count(nome) > 1 and porto:
                evs = [e for e in emails if nome in e["subj"] and porto in e["subj"]]
            else:
                evs = [e for e in emails if nome in e["subj"]]

            # Status AM/PM
            manha = any(e["date"].hour < 12 for e in evs)
            tarde = any(e["date"].hour >= 14 for e in evs) if agora_br.hour >= 14 else False
            
            # Datas ETA/ETB/ETD (do e-mail mais recente)
            dt = {"ETA": "-", "ETB": "-", "ETD": "-"}
            if evs:
                evs.sort(key=lambda x: x["date"], reverse=True)
                dt = evs[0]["info"]

            res.append({
                "Navio": f"{nome} ({porto})" if porto else nome,
                "Manhã": "✅" if manha else "❌",
                "Tarde": "✅" if tarde else "❌",
                "ETA": dt["ETA"], "ETB": dt["ETB"], "ETD": dt["ETD"]
            })
        return res

    st.session_state['slz'] = analisar(slz_bruto)
    st.session_state['bel'] = analisar(bel_bruto, True)

# --- EMAIL ---
def enviar_email():
    if 'slz' not in st.session_state: return
    try:
        msg = MIMEMultipart()
        msg["From"] = EMAIL_USER
        msg["To"] = ", ".join(DESTINOS)
        msg["Subject"] = "Monitor Prospects - " + datetime.now(BR_TZ).strftime("%d/%m %H:%M")

        def linhas(lista):
            h = ""
            for r in lista:
                cm = "#28a745" if r["Manhã"] == "✅" else "#dc3545"
                ct = "#28a745" if r["Tarde"] == "✅" else "#dc3545"
                h += f"<tr><td>{r['Navio']}</td>"
                h += f"<td style='background:{cm};color:white;text-align:center'>{r['Manhã']}</td>"
                h += f"<td style='background:{ct};color:white;text-align:center'>{r['Tarde']}</td>"
                h += f"<td>{r['ETA']}</td><td>{r['ETB']}</td><td>{r['ETD']}</td></tr>"
            return h

        corpo_html = f"""
        <html><body>
        <h2>⚓ Monitor Wilson Sons</h2>
        <h3>SÃO LUÍS</h3><table border='1' width='100%'>
        <tr style='background:#eee'><th>Navio</th><th>AM</th><th>PM</th><th>ETA</th><th>ETB</th><th>ETD</th></tr>
        {linhas(st.session_state['slz'])}</table>
        <h3>BELÉM</h3><table border='1' width='100%'>
        <tr style='background:#eee'><th>Navio</th><th>AM</th><th>PM</th><th>ETA</th><th>ETB</th><th>ETD</th></tr>
        {linhas(st.session_state['bel'])}</table>
        </body></html>"""

        msg.attach(MIMEText(corpo_html, "html"))
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(EMAIL_USER, EMAIL_PASS)
        server.send_message(msg)
        server.quit()
        st.success("Email enviado!")
    except Exception as e: st.error(f"Erro email: {e}")

# --- UI ---
st.title("🚢 Monitor Wilson Sons")

# Auto-envio
agora_hm = datetime.now(BR_TZ).strftime("%H:%M")
if "u_envio" not in st.session_state: st.session_state["u_envio"] = ""
if agora_hm in HORARIOS and st.session_state["u_envio"] != agora_hm:
    gerar_relatorio()
    enviar_email()
    st.session_state["u_envio"] = agora_hm

col1, col2 = st.columns(2)
with col1:
    if st.button("🔄 Atualizar Relatório"): gerar_relatorio()
with col2:
    if st.button("📧 Atualizar + Enviar"):
        gerar_relatorio()
        enviar_email()

if 'slz' in st.session_state:
    st.subheader("São Luís")
    st.table(st.session_state['slz'])
    st.subheader("Belém")
    st.table(st.session_state['bel'])

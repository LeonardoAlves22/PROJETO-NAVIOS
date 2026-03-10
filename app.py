import streamlit as st
import imaplib, email, re, smtplib
from email.header import decode_header
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from streamlit_autorefresh import st_autorefresh
import pytz

# --- CONFIGURAÇÕES ---
EMAIL_USER = "leonardo.alves@wilsonsons.com.br"
EMAIL_PASS = "nlvr vmyv cbcq oexe"
DESTINOS = ["leonardo.alves@wilsonsons.com.br", "operation.belem@wilsonsons.com.br", "operation.sluis@wilsonsons.com.br"]
LABEL_PROSPECT = "PROSPECT"
HORARIOS_ENVIO_EMAIL = ["09:30","10:00","11:00","11:30","16:00","17:00","17:30"]

# Timezone de Brasília
BR_TZ = pytz.timezone('America/Sao_Paulo')

st_autorefresh(interval=60000, key="auto_refresh")

# --- FUNÇÕES DE APOIO ---

def obter_agora_br():
    return datetime.now(BR_TZ)

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

def extrair_datas_corpo(corpo):
    info = {"ETA": "-", "ETB": "-", "ETD": "-"}
    if not corpo: return info
    for chave in info.keys():
        padrao = rf"{chave}\s*[:\-]?\s*(\d{{1,2}}[/|-](?:\d{{1,2}}|[A-Z]{{3}})(?:[/|-]\d{{2,4}})?(?:\s*\d{{2}}:\d{{2}})?) "
        match = re.search(padrao, corpo, re.IGNORECASE)
        if match:
            info[chave] = match.group(1).strip().upper()
    return info

# --- CONEXÃO GMAIL ---

def conectar_gmail():
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(EMAIL_USER, EMAIL_PASS)
        return mail
    except Exception as e:
        st.error(f"Falha na autenticação: {e}")
        return None

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

    corpo = re.split(r'Regards|Best regards', corpo, flags=re.IGNORECASE)[0]
    partes = re.split(r'BELEM:', corpo, flags=re.IGNORECASE)
    slz = [n.strip() for n in partes[0].replace('SLZ:', '').split('\n') if n.strip()]
    bel = [n.strip() for n in partes[1].split('\n') if n.strip()] if len(partes) > 1 else []
    return slz, bel

def buscar_emails(mail):
    # Tenta selecionar a pasta PROSPECT, se falhar tenta INBOX
    try:
        status, _ = mail.select(f'"{LABEL_PROSPECT}"', readonly=True)
        if status != 'OK': mail.select("INBOX", readonly=True)
    except:
        mail.select("INBOX", readonly=True)

    # Busca desde 2 dias atrás para garantir que nada escape do fuso
    data_busca = (obter_agora_br() - timedelta(days=2)).strftime("%d-%b-%Y")
    _, data = mail.search(None, f'(SINCE "{data_busca}")')

    lista = []
    hoje_br = obter_agora_br().date()

    if data[0]:
        for eid in data[0].split()[-150:]: # Processa os últimos 150 e-mails
            try:
                _, d = mail.fetch(eid, '(RFC822)')
                msg = email.message_from_bytes(d[0][1])
                envio_utc = email.utils.parsedate_to_datetime(msg.get("Date"))
                envio_br = envio_utc.astimezone(BR_TZ)

                # FILTRO RÍGIDO: Somente e-mails de HOJE no horário de Brasília
                if envio_br.date() != hoje_br:
                    continue

                subj = "".join(str(c.decode(ch or 'utf-8') if isinstance(c, bytes) else c)
                               for c, ch in decode_header(msg.get("Subject", ""))).upper()

                corpo = ""
                if msg.is_multipart():
                    for part in msg.walk():
                        if part.get_content_type() == "text/plain":
                            corpo = part.get_payload(decode=True).decode(errors="ignore")
                            break
                else:
                    corpo = msg.get_payload(decode=True).decode(errors="ignore")

                lista.append({
                    "subj": subj,
                    "date": envio_br,
                    "datas_op": extrair_datas_corpo(corpo)
                })
            except:
                continue
    return lista

# --- CORE ---

def gerar_relatorio():
    status_placeholder = st.empty()
    status_placeholder.info("⏳ Acessando e-mails...")
    
    mail = conectar_gmail()
    if not mail: return

    slz_bruto, bel_bruto = obter_lista_navios(mail)
    emails_prospect = buscar_emails(mail)
    mail.logout()

    agora_br = obter_agora_br()
    nomes_base_bel = [limpar_nome(n) for n in bel_bruto]

    def analisar(lista_origem, is_belem=False):
        res = []
        for item in lista_origem:
            nome = limpar_nome(item)
            porto = extrair_porto(item)
            if is_belem and nomes_base_bel.count(nome) > 1 and porto:
                evs = [e for e in emails_prospect if nome in e["subj"] and porto in e["subj"]]
            else:
                evs = [e for e in emails_prospect if nome in e["subj"]]

            # Se o e-mail foi 00:10, ele entra em Manhã (hour < 12)
            manha = any(e["date"].hour < 12 for e in evs)
            tarde = any(e["date"].hour >= 14 for e in evs) if agora_br.hour >= 14 else False

            dt = {"ETA": "-", "ETB": "-", "ETD": "-"}
            if evs:
                evs.sort(key=lambda x: x["date"], reverse=True)
                dt = evs[0]["datas_op"]

            res.append({
                "Navio": f"{nome} ({porto})" if porto else nome,
                "Manhã": "✅" if manha else "❌",
                "Tarde": "✅" if tarde else "❌",
                "ETA": dt["ETA"], "ETB": dt["ETB"], "ETD": dt["ETD"]
            })
        return res

    st.session_state['slz'] = analisar(slz_bruto)
    st.session_state['bel'] = analisar(bel_bruto, True)
    status_placeholder.success(f"✅ Atualizado em: {agora_br.strftime('%H:%M:%S')}")

def enviar_email():
    if 'slz' not in st.session_state: return
    try:
        msg = MIMEMultipart()
        msg["From"] = EMAIL_USER
        msg["To"] = ", ".join(DESTINOS)
        msg["Subject"] = "Monitor Prospects - " + obter_agora_br().strftime('%d/%m %H:%M')

        def build_rows(lista):
            rows = ""
            for r in lista:
                cm = "#28a745" if r["Manhã"] == "✅" else "#dc3545"
                ct = "#28a745" if r["Tarde"] == "✅" else "#dc3545"
                rows += "<tr>"
                rows += f"<td style='padding:5px; border:1px solid #ccc'>{r['Navio']}</td>"
                rows += f"<td style='background:{cm}; color:white; text-align:center'>{r['Manhã']}</td>"
                rows += f"<td style='background:{ct}; color:white; text-align:center'>{r['Tarde']}</td>"
                rows += f"<td style='padding:5px; border:1px solid #ccc; text-align:center'>{r['ETA']}</td>"
                rows += f"<td style='padding:5px; border:1px solid #ccc; text-align:center'>{r['ETB']}</td>"
                rows += f"<td style='padding:5px; border:1px solid #ccc; text-align:center'>{r['ETD']}</td>"
                rows += "</tr>"
            return rows

        html = f"""<html><body>
            <h2 style='color:#2b6cb0'>Monitor Wilson Sons</h2>
            <h3>São Luís</h3><table border='1' style='border-collapse:collapse; width:100%'>
            <tr style='background:#eee'><th>Navio</th><th>AM</th><th>PM</th><th>ETA</th><th>ETB</th><th>ETD</th></tr>
            {build_rows(st.session_state['slz'])}</table>
            <h3>Belém</h3><table border='1' style='border-collapse:collapse; width:100%'>
            <tr style='background:#eee'><th>Navio</th><th>AM</th><th>PM</th><th>ETA</th><th>ETB</th><th>ETD</th></tr>
            {build_rows(st.session_state['bel'])}</table>
            </body></html>"""

        msg.attach(MIMEText(html, "html"))
        with smtplib.SMTP("smtp.gmail.com", 587) as s:
            s.starttls()
            s.login(EMAIL_USER, EMAIL_PASS)
            s.send_message(msg)
        st.success("📧 E-mail enviado!")
    except Exception as e:
        st.error(f"Erro e-mail: {e}")

# --- UI ---
st.set_page_config(page_title="Monitor Wilson Sons", layout="wide")
st.title("🚢 Monitor Operacional Wilson Sons")

agora_str = obter_agora_br().strftime("%H:%M")
if "ultimo_envio" not in st.session_state: st.session_state["ultimo_envio"] = ""

if agora_str in HORARIOS_ENVIO_EMAIL and st.session_state["ultimo_envio"] != agora_str:
    gerar_relatorio()
    enviar_email()
    st.session_state["ultimo_envio"] = agora_str

c1, c2 = st.columns(2)
with c1:
    if st.button("🔄 Atualizar Relatório", use_container_width=True):
        gerar_relatorio()
with c2:
    if st.button("📧 Forçar Envio de Email", use_container_width=True):
        gerar_relatorio()
        enviar_email()

if 'slz' in st.session_state:
    tab1, tab2 = st.tabs(["📍 São Luís", "📍 Belém"])
    with tab1:
        st.dataframe(st.session_state['slz'], use_container_width=True, hide_index=True)
    with tab2:
        st.dataframe(st.session_state['bel'], use_container_width=True, hide_index=True)

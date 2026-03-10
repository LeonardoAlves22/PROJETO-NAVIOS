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
BR_TIMEZONE = pytz.timezone('America/Sao_Paulo')

st_autorefresh(interval=60000, key="auto_refresh")

# --- AUXILIARES ---

def obter_agora_br():
    return datetime.now(BR_TIMEZONE)

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
        # Regex melhorada: busca a chave e tenta pegar a data/hora logo após
        padrao = rf"{chave}\s*[:\-]?\s*(\d{{1,2}}[/|-](?:\d{{1,2}}|[A-Z]{{3}})(?:[/|-]\d{{2,4}})?(?:\s*\d{{2}}:\d{{2}})?) "
        match = re.search(padrao, corpo, re.IGNORECASE)
        if match:
            info[chave] = match.group(1).strip().upper()
    return info

# --- IMAP ---

def conectar_gmail():
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(EMAIL_USER, EMAIL_PASS)
        return mail
    except Exception as e:
        st.error(f"Erro Gmail: {e}")
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
    mail.select(f'"{LABEL_PROSPECT}"', readonly=True)
    # Buscamos desde ontem para garantir que e-mails da madrugada (00:10) sejam capturados
    ontem = (obter_agora_br() - timedelta(days=1)).strftime("%d-%b-%Y")
    _, data = mail.search(None, f'(SINCE "{ontem}")')

    lista = []
    hoje_br = obter_agora_br().date()

    if data[0]:
        for eid in data[0].split()[-150:]:
            try:
                _, d = mail.fetch(eid, '(RFC822)')
                msg = email.message_from_bytes(d[0][1])
                
                # Conversão correta de fuso
                date_str = msg.get("Date")
                envio_utc = email.utils.parsedate_to_datetime(date_str)
                envio_br = envio_utc.astimezone(BR_TIMEZONE)

                # Filtro: Só queremos e-mails que caíram no dia de HOJE (Brasília)
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

# --- LÓGICA ---

def gerar_relatorio():
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
                emails_vessel = [e for e in emails_prospect if nome in e["subj"] and porto in e["subj"]]
            else:
                emails_vessel = [e for e in emails_prospect if nome in e["subj"]]

            # Critério: Manhã (00:00 às 11:59) / Tarde (14:00 em diante)
            manha = any(e["date"].hour < 12 for e in emails_vessel)
            tarde = any(e["date"].hour >= 14 for e in emails_vessel) if agora_br.hour >= 14 else False

            # Pegar dados do e-mail mais recente deste navio
            datas_info = {"ETA": "-", "ETB": "-", "ETD": "-"}
            if emails_vessel:
                emails_vessel.sort(key=lambda x: x["date"], reverse=True)
                datas_info = emails_vessel[0]["datas_op"]

            res.append({
                "Navio": f"{nome} ({porto})" if porto else nome,
                "Manhã": "✅" if manha else "❌",
                "Tarde": "✅" if tarde else "❌",
                "ETA": datas_info["ETA"],
                "ETB": datas_info["ETB"],
                "ETD": datas_info["ETD"]
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
        msg["Subject"] = f"Monitor Prospects - {obter_agora_br().strftime('%d/%m %H:%M')}"

        def build_rows(lista):
            rows = ""
            for r in lista:
                cm = "#28a745" if r["Manhã"] == "✅" else "#dc3545"
                ct = "#28a745" if r["Tarde"] == "✅" else "#dc3545"
                rows += f"""<tr>
                    <td style="padding:5px; border:1px solid #ccc">{r['Navio']}</td>
                    <td style="background:{cm}; color:white; text-align:center">{

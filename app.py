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

BR_TZ = pytz.timezone('America/Sao_Paulo')
st_autorefresh(interval=60000, key="auto_refresh")

# --- AUXILIARES ---
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
        # Busca a sigla e pega a data/hora logo a frente
        m = re.search(rf"{k}\s*[:\-]?\s*(\d{{1,2}}[/|-](?:\d{{1,2}}|[A-Z]{{3}})[^ \n]*)", corpo, re.IGNORECASE)
        if m: res[k] = m.group(1).strip().upper()
    return res

# --- CORE FUNCTIONS ---

def gerar_relatorio():
    try:
        # 1. Conexão
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(EMAIL_USER, EMAIL_PASS)
        
        # 2. Obter Lista de Navios (E-mail com assunto "LISTA NAVIOS")
        mail.select("INBOX", readonly=True)
        _, data_lista = mail.search(None, '(SUBJECT "LISTA NAVIOS")')
        
        if not data_lista[0]:
            st.error("❌ ERRO: E-mail com assunto 'LISTA NAVIOS' não foi encontrado na INBOX.")
            mail.logout()
            return

        eid = data_lista[0].split()[-1]
        _, d = mail.fetch(eid, '(RFC822)')
        msg_lista = email.message_from_bytes(d[0][1])
        
        corpo_lista = ""
        if msg_lista.is_multipart():
            for part in msg_lista.walk():
                if part.get_content_type() == "text/plain":
                    corpo_lista = part.get_payload(decode=True).decode(errors="ignore")
                    break
        else:
            corpo_lista = msg_lista.get_payload(decode=True).decode(errors="ignore")

        # Split da lista
        partes = re.split(r'BELEM:', corpo_lista, flags=re.IGNORECASE)
        slz_bruto = [n.strip() for n in partes[0].replace('SLZ:', '').split('\n') if len(n.strip()) > 3]
        bel_bruto = [n.strip() for n in partes[1].split('\n') if len(n.strip()) > 3] if len(partes) > 1 else []

        # 3. Buscar e-mails da Label PROSPECT (ou INBOX caso falhe)
        status_p, _ = mail.select(f'"{LABEL_PROSPECT}"', readonly=True)
        if status_p != 'OK':
            mail.select("INBOX", readonly=True)
            st.warning(f"Pasta '{LABEL_PROSPECT}' não encontrada. Buscando na INBOX...")

        # Busca e-mails desde ontem (para fuso 00:10)
        data_busca = (datetime.now(BR_TZ) - timedelta(days=1)).strftime("%d-%b-%Y")
        _, data_prospects = mail.search(None, f'(SINCE "{data_busca}")')

        emails_encontrados = []
        hoje_br = datetime.now(BR_TZ).date()

        if data_prospects[0]:
            for eid in data_prospects[0].split()[-150:]: # Últimos 150 e-mails
                try:
                    _, d = mail.fetch(eid, '(RFC822)')
                    msg = email.message_from_bytes(d[0][1])
                    
                    # Fuso Horário
                    envio_utc = email.utils.parsedate_to_datetime(msg.get("Date"))
                    envio_br = envio_utc.astimezone(BR_TZ)

                    if envio_br.date() != hoje_br: continue

                    subj = "".join(str(c.decode(ch or 'utf-8') if isinstance(c, bytes) else c)
                                   for c, ch in decode_header(msg.get("Subject", ""))).upper()

                    corpo = ""
                    if msg.is_multipart():
                        for part in msg.walk():
                            if part.get_content_type() == "text/plain":
                                corpo = part.get_payload(decode=True).decode(errors="ignore")
                    else:
                        corpo = msg.get_payload(decode=True).decode(errors="ignore")

                    emails_encontrados.append({
                        "subj": subj, "date": envio_br, "info": extrair_datas(corpo)
                    })
                except: continue

        mail.logout()

        # 4. Analisar
        nomes_bel = [limpar_nome(n) for n in bel_bruto]
        def processar(lista, is_bel=False):
            final = []
            for item in lista:
                nome = limpar_nome(item)
                porto = extrair_porto(item)
                
                if is_bel and nomes_bel.count(nome) > 1 and porto:
                    evs = [e for e in emails_encontrados if nome in e["subj"] and porto in e["subj"]]
                else:
                    evs = [e for e in emails_encontrados if nome in e["subj"]]

                manha = any(e["date"].hour < 12 for e in evs)
                tarde = any(e["date"].hour >= 14 for e in evs) if datetime.now(BR_TZ).hour >= 14 else False
                
                dt_info = {"ETA": "-", "ETB": "-", "ETD": "-"}
                if evs:
                    evs.sort(key=lambda x: x["date"], reverse=True)
                    dt_info = evs[0]["info"]

                final.append({
                    "Navio": f"{nome} ({porto})" if porto else nome,
                    "AM": "✅" if manha else "❌",
                    "PM": "✅" if tarde else "❌",
                    "ETA": dt_info["ETA"], "ETB": dt_info["ETB"], "ETD": dt_info["ETD"]
                })
            return final

        st.session_state['slz'] = processar(slz_bruto)
        st.session_state['bel'] = processar(bel_bruto, True)
        st.success(f"✅ Sucesso! {len(emails_encontrados)} e-mails analisados.")

    except Exception as e:
        st.error(f"❌ Ocorreu um erro crítico: {e}")

# --- EMAIL SEND ---
def enviar_email():
    if 'slz' not in st.session_state: return
    try:
        msg = MIMEMultipart()
        msg["From"] = EMAIL_USER
        msg["To"] = ", ".join(DESTINOS)
        msg["Subject"] = f"Monitor Prospects - {datetime.now(BR_TZ).strftime('%d/%m %H:%M')}"

        def tr_html(lista):
            h = ""
            for r in lista:
                cm = "#28a745" if r["AM"] == "✅" else "#dc3545"
                ct = "#28a745" if r["PM"] == "✅" else "#dc3545"
                h += f"<tr><td>{r['Navio']}</td>"
                h += f"<td style='background:{cm};color:white;text-align:center'>{r['AM']}</td>"
                h += f"<td style='background:{ct};color:white;text-align:center'>{r['PM']}</td>"
                h += f"<td>{r['ETA']}</td><td>{r['ETB']}</td><td>{r['ETD']}</td></tr>"
            return h

        html = f"""<html><body>
        <h2>⚓ Monitor Wilson Sons</h2>
        <h3>SÃO LUÍS</h3><table border='1' width='100%'>
        <tr style='background:#eee'><th>Navio</th><th>AM</th><th>PM</th><th>ETA</th><th>ETB</th><th>ETD</th></tr>
        {tr_html(st.session_state['slz'])}</table>
        <br>
        <h3>BELÉM</h3><table border='1' width='100%'>
        <tr style='background:#eee'><th>Navio</th><th>AM</th><th>PM</th><th>ETA</th><th>ETB</th><th>ETD</th></tr>
        {tr_html(st.session_state['bel'])}</table>
        </body></html>"""

        msg.attach(MIMEText(html, "html"))
        with smtplib.SMTP("smtp.gmail.com", 587) as s:
            s.starttls()
            s.login(EMAIL_USER, EMAIL_PASS)
            s.send_message(msg)
        st.success("📧 E-mail enviado com sucesso!")
    except Exception as e:
        st.error(f"Erro no envio de e-mail: {e}")

# --- UI ---
st.title("🚢 Monitor Operacional")

# Lógica Auto-Envio
agora_hm = datetime.now(BR_TZ).strftime("%H:%M")
if "u_envio" not in st.session_state: st.session_state["u_envio"] = ""
if agora_hm in HORARIOS and st.session_state["u_envio"] != agora_hm:
    gerar_relatorio()
    enviar_email()
    st.session_state["u_envio"] = agora_hm

col1, col2 = st.columns(2)
with col1:
    if st.button("🔄 Atualizar Relatório", use_container_width=True):
        gerar_relatorio()
with col2:
    if st.button("📧 Atualizar + Enviar E-mail", use_container_width=True):
        gerar_relatorio()
        enviar_email()

if 'slz' in st.session_state:
    st.subheader("São Luís")
    st.table(st.session_state['slz'])
    st.subheader("Belém")
    st.table(st.session_state['bel'])

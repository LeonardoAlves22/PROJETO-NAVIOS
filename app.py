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

REM_SLZ = ["operation.sluis@wilsonsons.com.br", "agencybrazil@cargill.com"]
REM_BEL = ["operation.belem@wilsonsons.com.br"]
KEYWORDS = ["PROSPECT NOTICE", "BERTHING PROSPECT", "ARRIVAL NOTICE", "DAILY NOTICE", "DAILY REPORT"]
HORARIOS_DISPARO = ["09:30", "10:00", "11:00", "11:30", "16:00", "17:00", "17:30"]

PORTOS_IDENTIFICADORES = {
    "SLZ": ["SAO LUIS", "SLZ", "ITAQUI", "ALUMAR", "PONTA DA MADEIRA"],
    "BEL": ["BELEM", "OUTEIRO", "MIRAMAR"],
    "VDC": ["VILA DO CONDE", "VDC", "BARCARENA"]
}

# Atualiza o app a cada 1 minuto
st_autorefresh(interval=60000, key="v10_fix")

# --- FUNÇÕES ---
def enviar_email_html(html_conteudo, hora_ref):
    try:
        msg = MIMEMultipart()
        msg['From'] = EMAIL_USER
        msg['To'] = DESTINO
        msg['Subject'] = f"RESUMO OPERACIONAL - {datetime.now().strftime('%d/%m/%Y')} ({hora_ref})"
        msg.attach(MIMEText(html_conteudo, 'html'))
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(EMAIL_USER, EMAIL_PASS)
            server.send_message(msg)
        return True
    except Exception as e:
        st.error(f"Erro SMTP: {e}")
        return False

def selecionar_pasta_segura(mail):
    """Tenta selecionar a pasta correta para evitar o erro de estado AUTH"""
    # Ordem de tentativa: Pasta técnica do Gmail, Pasta em Português, Inbox padrão
    pastas = ['"[Gmail]/All Mail"', '"[Gmail]/Todos os e-mails"', 'INBOX']
    for pasta in pastas:
        try:
            status, _ = mail.select(pasta, readonly=True)
            if status == 'OK':
                return True
        except:
            continue
    return False

def buscar_dados_email():
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(EMAIL_USER, EMAIL_PASS)
        
        if not selecionar_pasta_segura(mail):
            st.error("Não foi possível selecionar nenhuma pasta de e-mail.")
            return [], [], [], datetime.now()

        # Busca e-mail LISTA NAVIOS
        _, messages = mail.search(None, '(SUBJECT "LISTA NAVIOS")')
        if not messages[0]:
            st.warning("E-mail 'LISTA NAVIOS' não encontrado.")
            return [], [], [], datetime.now()
        
        id_lista = messages[0].split()[-1]
        _, data = mail.fetch(id_lista, '(RFC822)')
        msg_lista = email.message_from_bytes(data[0][1])
        
        corpo = ""
        if msg_lista.is_multipart():
            for part in msg_lista.walk():
                if part.get_content_type() == "text/plain":
                    corpo = part.get_payload(decode=True).decode(errors='ignore')
                    break
        else:
            corpo = msg_lista.get_payload(decode=True).decode(errors='ignore')

        # Divide SLZ e BELEM
        corpo_limpo = re.split(r'Regards|Best regards', corpo, flags=re.IGNORECASE)[0]
        partes = re.split(r'BELEM:', corpo_limpo, flags=re.IGNORECASE)
        slz_lista = [n.strip() for n in partes[0].replace('SLZ:', '').split('\n') if n.strip() and "SLZ:" not in n.upper()]
        bel_lista = [n.strip() for n in partes[1].split('\n') if n.strip()] if len(partes) > 1 else []

        # Busca atualizações do dia (Prospects)
        agora_br = datetime.now() - timedelta(hours=3)
        hoje = agora_br.strftime("%d-%b-%Y")
        _, ids = mail.search(None, f'(SINCE "{hoje}")')
        
        emails_db = []
        if ids[0]:
            for e_id in ids[0].split():
                _, d = mail.fetch(e_id, '(BODY[HEADER.FIELDS (SUBJECT DATE FROM)])')
                m = email.message_from_bytes(d[0][1])
                subj = "".join(str(c.decode(ch or 'utf-8', errors='ignore') if isinstance(c, bytes) else c) for c, ch in decode_header(m.get("Subject", ""))).upper()
                envio = email.utils.parsedate_to_datetime(m.get("Date")).replace(tzinfo=None)
                emails_db.append({"subj": subj, "from": m.get("From").lower(), "date": envio})
        
        mail.logout()
        return slz_lista, bel_lista, emails_db, agora_br.replace(hour=14, minute=0)
    except Exception as e:
        st.error(f"Erro na conexão IMAP: {e}")
        return [], [], [], datetime.now()

def processar_fluxo():
    slz, bel, db, corte = buscar_dados_email()
    if not slz and not bel: return

    agora_br = datetime.now() - timedelta(hours=3)
    res_slz, res_bel = [], []

    # Regex para nomes compostos e diferenciação
    def limpar(txt):
        txt_up = txt.upper()
        p = " (VDC)" if "VILA" in txt_up or "VDC" in txt_up else " (BEL)" if "BELEM" in txt_up else ""
        n = re.sub(r'^MV\s+|^M/V\s+|^MT\s+', '', txt.strip(), flags=re.IGNORECASE)
        n = re.split(r'\sV\.|\sV\d|/|–', re.sub(r'\(.*?\)', '', n), flags=re.IGNORECASE)[0].strip().upper()
        return n + p

    for lista, rems, target in [(slz, REM_SLZ, res_slz), (bel, REM_BEL, res_bel)]:
        for item in lista:
            n_exibicao = limpar(item)
            n_busca = n_exibicao.split(' (')[0]
            m_g = [em for em in db if n_busca in em["subj"] and any(r in em["from"] for r in rems)]
            m_t = [em for em in m_g if em["date"] >= corte]
            target.append({"Navio": n_exibicao, "Manhã": "✅" if m_g else "❌", "Tarde": "✅" if m_t else "❌"})

    # Salva para exibir no site
    st.session_state['res_slz'] = res_slz
    st.session_state['res_bel'] = res_bel

    # Monta HTML Lado a Lado para o E-mail
    html = f"""
    <html><body>
    <h2 style="color:#003366;">Resumo Operacional - {agora_br.strftime('%d/%m/%Y')}</h2>
    <div style="display:flex; gap:20px;">
        <div style="flex:1;">
            <h3 style="background:#003366; color:white; padding:5px;">SÃO LUÍS</h3>
            <table border="1" style="border-collapse:collapse; width:100%;">
                <tr style="background:#eee;"><th>Navio</th><th>Manhã</th><th>Tarde</th></tr>
    """
    for n in res_slz: html += f"<tr><td>{n['Navio']}</td><td align='center'>{n['Manhã']}</td><td align='center'>{n['Tarde']}</td></tr>"
    html += "</table></div><div style='flex:1;'><h3 style='background:#003366; color:white; padding:5px;'>BELÉM / VDC</h3><table border='1' style='border-collapse:collapse; width:100%;'><tr style='background:#eee;'><th>Navio</th><th>Manhã</th><th>Tarde</th></tr>"
    for n in res_bel: html += f"<tr><td>{n['Navio']}</td><td align='center'>{n['Manhã']}</td><td align='center'>{n['Tarde']}</td></tr>"
    html += "</table></div></div></body></html>"

    if enviar_email_html(html, agora_br.strftime("%H:%M")):
        st.success("Relatório enviado e site atualizado!")

# --- INTERFACE ---
st.title("🚢 Monitor Wilson Sons")
agora = (datetime.now() - timedelta(hours=3)).strftime("%H:%M")
st.write(f"Última atualização: {agora}")

if st.button("🔄 Atualizar Agora"):
    processar_fluxo()

if 'res_slz' in st.session_state:
    c1, c2 = st.columns(2)
    c1.subheader("São Luís")
    c1.table(st.session_state['res_slz'])
    c2.subheader("Belém / VDC")
    c2.table(st.session_state['res_bel'])

# Disparos Automáticos
if agora in HORARIOS_DISPARO:
    if "ultimo_minuto" not in st.session_state or st.session_state.ultimo_minuto != agora:
        processar_fluxo()
        st.session_state.ultimo_minuto = agora

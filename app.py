import streamlit as st
import imaplib, email, re, smtplib
import pandas as pd
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from email.header import decode_header
from streamlit_autorefresh import st_autorefresh

# --- CONFIGURAÇÕES DE ACESSO CORPORATIVO ---
EMAIL_USER = "leonardo.alves@wilsonsons.com.br"
EMAIL_PASS = "ighf pteu xtfx fkom" 
DESTINO = "leonardo.alves@wilsonsons.com.br"

REM_SLZ = ["operation.sluis@wilsonsons.com.br", "agencybrazil@cargill.com"]
REM_BEL = ["operation.belem@wilsonsons.com.br"]
KEYWORDS = ["PROSPECT NOTICE", "BERTHING PROSPECT", "BERTHING PROSPECTS", "ARRIVAL NOTICE", "BERTH NOTICE", "DAILY NOTICE", "DAILY REPORT", "DAILY"]

HORARIOS_DISPARO = ["09:30", "10:00", "11:00", "11:30", "16:00", "17:00", "17:30"]

PORTOS_IDENTIFICADORES = {
    "SLZ": ["SAO LUIS", "SLZ", "ITAQUI", "ALUMAR", "PONTA DA MADEIRA"],
    "BEL": ["BELEM", "OUTEIRO", "MIRAMAR"],
    "VDC": ["VILA DO CONDE", "VDC", "BARCARENA"]
}

# --- AUTO-REFRESH (Mantém o app vivo para os disparos automáticos) ---
st_autorefresh(interval=60000, key="auto_disparo_monitor")

# --- FUNÇÕES DE APOIO ---
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
        st.error(f"Falha no envio do e-mail: {e}")
        return False

def buscar_dados_email():
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(EMAIL_USER, EMAIL_PASS)
        
        # Seleciona a pasta "Todos os e-mails" usando o nome técnico do Gmail
        status, _ = mail.select('"[Gmail]/Todos os e-mails"', readonly=True)
        
        if status != 'OK':
            # Backup caso o nome da pasta seja diferente na configuração da conta
            mail.select('INBOX', readonly=True)

        _, messages = mail.search(None, '(SUBJECT "LISTA NAVIOS")')
        if not messages[0]: 
            mail.logout()
            return [], [], [], (datetime.now() - timedelta(hours=3))
        
        ultimo_id = messages[0].split()[-1]
        _, data = mail.fetch(ultimo_id, '(RFC822)')
        msg_raw = email.message_from_bytes(data[0][1])
        
        # Extração do corpo
        corpo = ""
        if msg_raw.is_multipart():
            for part in msg_raw.walk():
                if part.get_content_type() == "text/plain":
                    corpo = part.get_payload(decode=True).decode(errors='ignore')
                    break
        else: corpo = msg_raw.get_payload(decode=True).decode(errors='ignore')
        
        corpo = re.split(r'Best regards|Regards', corpo, flags=re.IGNORECASE)[0]
        partes = re.split(r'BELEM:', corpo, flags=re.IGNORECASE)
        slz_lista = [n.strip() for n in partes[0].replace('SLZ:', '').split('\n') if n.strip() and "SLZ:" not in n.upper()]
        bel_lista = [n.strip() for n in partes[1].split('\n') if n.strip()] if len(partes) > 1 else []
        
        # Ajuste Fuso Horário Brasil
        agora_brasil = datetime.now() - timedelta(hours=3)
        hoje_str = agora_brasil.strftime("%d-%b-%Y")
        corte_tarde = agora_brasil.replace(hour=14, minute=0, second=0, microsecond=0)
        
        _, ids = mail.search(None, f'(SINCE "{hoje_str}")')
        emails_encontrados = []
        if ids[0]:
            for e_id in ids[0].split():
                _, data = mail.fetch(e_id, '(BODY[HEADER.FIELDS (SUBJECT DATE FROM)])')
                msg = email.message_from_bytes(data[0][1])
                data_envio = email.utils.parsedate_to_datetime(msg.get("Date")).replace(tzinfo=None)
                if data_envio >= agora_brasil.replace(hour=0, minute=0, second=0):
                    subj = "".join(str(c.decode(ch or 'utf-8', errors='ignore') if isinstance(c, bytes) else c) for c, ch in decode_header(msg.get("Subject", ""))).upper()
                    emails_encontrados.append({"subj": subj, "from": (msg.get("From") or "").lower(), "date": data_envio})
        
        mail.logout()
        return slz_lista, bel_lista, emails_encontrados, corte_tarde
    except Exception as e:
        st.error(f"Erro na leitura do e-mail: {e}")
        return [], [], [], (datetime.now() - timedelta(hours=3))

def processar_e_enviar():
    slz_bruto, bel_bruto, e_db, corte = buscar_dados_email()
    agora_br = datetime.now() - timedelta(hours=3)
    hora_ref = agora_br.strftime('%H:%M')
    
    res_slz, res_bel = [], []
    for lista, rems, target in [(slz_bruto, REM_SLZ, res_slz), (bel_bruto, REM_BEL, res_bel)]:
        for n_bruto in lista:
            n_limpo = re.sub(r'^MV\s+|^M/V\s+|^MT\s+', '', n_bruto.strip(), flags=re.IGNORECASE).split(' ')[0].upper()
            m_g = [em for em in e_db if n_limpo in em["subj"] and any(r in em["from"] for r in rems)]
            m_t = [em for em in m_g if em["date"] >= corte]
            target.append({"Navio": n_limpo, "Manhã": "✅" if m_g else "❌", "Tarde": "✅" if m_t else "❌"})

    # HTML do E-mail Lado a Lado
    html = f"""
    <html>
    <body style="font-family: Arial, sans-serif; color: #333;">
        <h2 style="color: #003366;">Resumo Operacional - {agora_br.strftime('%d/%m/%Y')} às {hora_ref}</h2>
        <table border="0" cellpadding="0" cellspacing="0" style="width: 100%; max-width: 900px;">
            <tr>
                <td style="width: 48%; vertical-align: top; padding-right: 20px;">
                    <h3 style="background-color: #003366; color: white; padding: 10px;">SÃO LUÍS</h3>
                    <table border="1" style="border-collapse: collapse; width: 100%;">
                        <tr style="background-color: #eee;"><th>Navio</th><th>Manhã</th><th>Tarde</th></tr>
    """
    for n in res_slz:
        html += f"<tr><td style='padding:5px;'>{n['Navio']}</td><td align='center'>{n['Manhã']}</td><td align='center'>{n['Tarde']}</td></tr>"
    
    html += """
                    </table>
                </td>
                <td style="width: 48%; vertical-align: top; padding-left: 20px;">
                    <h3 style="background-color: #003366; color: white; padding: 10px;">BELÉM / VDC</h3>
                    <table border="1" style="border-collapse: collapse; width: 100%;">
                        <tr style="background-color: #eee;"><th>Navio</th><th>Manhã</th><th>Tarde</th></tr>
    """
    for n in res_bel:
        html += f"<tr><td style='padding:5px;'>{n['Navio']}</td><td align='center'>{n['Manhã']}</td><td align='center'>{n['Tarde']}</td></tr>"
    
    html += """
                    </table>
                </td>
            </tr>
        </table>
    </body>
    </html>
    """
    enviar_email_html(html, hora_ref)
    return res_slz, res_bel

# --- INTERFACE ---
st.set_page_config(page_title="WS Monitor Corporativo", layout="wide")
agora_br = datetime.now() - timedelta(hours=3)
hora_minuto = agora_br.strftime("%H:%M")

st.title("🚢 Monitor Wilson Sons - Corporativo")
st.metric("Horário Brasília", hora_minuto)

# Verificação de Disparo Automático
if hora_minuto in HORARIOS_DISPARO:
    if "ultimo_envio" not in st.session_state or st.session_state.ultimo_envio != hora_minuto:
        with st.spinner(f"Disparo automático das {hora_minuto}..."):
            r_slz, r_bel = processar_e_enviar()
            st.session_state.ultimo_envio = hora_minuto
            st.toast("Relatório enviado automaticamente!")

if st.button("🔄 Gerar Agora e Enviar E-mail"):
    r_slz, r_bel = processar_e_enviar()
    st.session_state['res_slz_v'], st.session_state['res_bel_v'] = r_slz, r_bel
    st.success("Relatório enviado!")

if 'res_slz_v' in st.session_state:
    c1, c2 = st.columns(2)
    c1.table(st.session_state.res_slz_v)
    c2.table(st.session_state.res_bel_v)

import streamlit as st
import imaplib, email, re, smtplib
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

st_autorefresh(interval=60000, key="monitor_v9")

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
        st.sidebar.error(f"Erro ao enviar e-mail: {e}")
        return False

def limpar_nome_navio(nome_bruto):
    if not nome_bruto: return ""
    nome_up = nome_bruto.upper()
    sufixo = " (VILA DO CONDE)" if any(x in nome_up for x in ["VILA DO CONDE", "VDC"]) else " (BELEM)" if "BELEM" in nome_up else ""
    nome = re.sub(r'^MV\s+|^M/V\s+|^MT\s+|^M/T\s+', '', nome_bruto.strip(), flags=re.IGNORECASE)
    nome = re.split(r'\sV\.|\sV\d|/|–', re.sub(r'\(.*?\)', '', nome), flags=re.IGNORECASE)[0]
    return nome.strip().upper() + sufixo

def buscar_dados_email():
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(EMAIL_USER, EMAIL_PASS)
        mail.select('"[Gmail]/All Mail"', readonly=True)
        
        # Busca lista base
        _, messages = mail.search(None, '(SUBJECT "LISTA NAVIOS")')
        if not messages[0]: return [], [], [], datetime.now()
        
        ultimo_id = messages[0].split()[-1]
        _, data = mail.fetch(ultimo_id, '(RFC822)')
        corpo = email.message_from_bytes(data[0][1]).get_payload(decode=True).decode(errors='ignore') if not email.message_from_bytes(data[0][1]).is_multipart() else ""
        # (Lógica simplificada de extração para o exemplo)
        partes = re.split(r'BELEM:', corpo, flags=re.IGNORECASE)
        slz_lista = [n.strip() for n in partes[0].split('\n') if n.strip()][:5] # Limitado para teste
        bel_lista = [n.strip() for n in partes[1].split('\n') if n.strip()][:5] if len(partes) > 1 else []

        # Busca atualizações do dia
        hoje = (datetime.now() - timedelta(hours=3)).strftime("%d-%b-%Y")
        _, ids = mail.search(None, f'(SINCE "{hoje}")')
        emails_hoje = []
        for e_id in ids[0].split()[-20:]: # Analisa os últimos 20 e-mails do dia
            _, data = mail.fetch(e_id, '(BODY[HEADER.FIELDS (SUBJECT DATE FROM)])')
            msg = email.message_from_bytes(data[0][1])
            subj = str(decode_header(msg["Subject"])[0][0]).upper()
            emails_hoje.append({"subj": subj, "from": msg["From"].lower(), "date": email.utils.parsedate_to_datetime(msg["Date"]).replace(tzinfo=None)})
        
        mail.logout()
        return slz_lista, bel_lista, emails_hoje, (datetime.now() - timedelta(hours=3)).replace(hour=14, minute=0)
    except Exception as e:
        st.error(f"Erro na busca: {e}")
        return [], [], [], datetime.now()

def processar_e_atualizar_interface():
    slz_bruto, bel_bruto, e_db, corte = buscar_dados_email()
    if not slz_bruto and not bel_bruto:
        st.warning("Nenhum dado encontrado nos e-mails.")
        return

    res_slz, res_bel = [], []
    for lista, rems, target in [(slz_bruto, REM_SLZ, res_slz), (bel_bruto, REM_BEL, res_bel)]:
        for n in lista:
            n_limpo = limpar_nome_navio(n)
            n_busca = n_limpo.split(' (')[0]
            m_g = [em for em in e_db if n_busca in em["subj"] and any(r in em["from"] for r in rems)]
            m_t = [em for em in m_g if em["date"] >= corte]
            target.append({"Navio": n_limpo, "Manhã": "✅" if m_g else "❌", "Tarde": "✅" if m_t else "❌"})

    # Salva no estado da sessão para mostrar no site
    st.session_state['res_slz'] = res_slz
    st.session_state['res_bel'] = res_bel
    
    # Monta HTML e envia
    html = f"<h2>Resumo {datetime.now().strftime('%d/%m/%Y')}</h2><table border='1'>...</table>" # Simplificado para brevidade
    if enviar_email_html(html, datetime.now().strftime('%H:%M')):
        st.success("E-mail enviado com sucesso!")
    else:
        st.error("Falha ao enviar e-mail.")

# --- INTERFACE ---
st.title("🚢 Monitor Wilson Sons")
agora = (datetime.now() - timedelta(hours=3)).strftime("%H:%M")
st.write(f"Hora atual: {agora}")

if st.button("🔄 Atualizar Agora (Site + E-mail)"):
    processar_e_atualizar_interface()

if 'res_slz' in st.session_state:
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("São Luís")
        st.table(st.session_state['res_slz'])
    with col2:
        st.subheader("Belém / VDC")
        st.table(st.session_state['res_bel'])

# Automação de horário
if agora in HORARIOS_DISPARO:
    if "ultimo_minuto" not in st.session_state or st.session_state.ultimo_minuto != agora:
        processar_e_atualizar_interface()
        st.session_state.ultimo_minuto = agora

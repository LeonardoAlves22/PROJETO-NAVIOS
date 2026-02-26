import streamlit as st
import imaplib, email, re, smtplib
import pandas as pd
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from email.header import decode_header
from streamlit_autorefresh import st_autorefresh

# 1. CONFIGURAÇÕES TÉCNICAS
EMAIL_USER = "leonardo.alves@wilsonsons.com.br"
EMAIL_PASS = "ighf pteu xtfx fkom"
DESTINO = "leonardo.alves@wilsonsons.com.br"

# Remetentes Oficiais
REMS = {
    "SLZ": ["operation.sluis@wilsonsons.com.br", "agencybrazil@cargill.com"],
    "BEL": ["operation.belem@wilsonsons.com.br"]
}

HORARIOS = ["09:30", "10:00", "11:00", "11:30", "16:00", "17:00", "17:30"]

# --- FUNÇÕES DE MOTOR (BACKEND) ---

def conectar_gmail():
    """Cria uma conexão limpa com o Gmail"""
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(EMAIL_USER, EMAIL_PASS)
        # Tenta selecionar a pasta All Mail ou Inbox
        for pasta in ['"[Gmail]/All Mail"', 'INBOX']:
            if mail.select(pasta, readonly=True)[0] == 'OK':
                return mail
        return None
    except:
        return None

def obter_lista_navios(mail):
    """Busca o e-mail 'LISTA NAVIOS' e separa por porto"""
    _, data = mail.search(None, '(SUBJECT "LISTA NAVIOS")')
    if not data[0]: return [], []
    
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

    # Separação por palavras-chave
    corpo = re.split(r'Regards|Best regards', corpo, flags=re.IGNORECASE)[0]
    partes = re.split(r'BELEM:', corpo, flags=re.IGNORECASE)
    
    slz = [n.strip() for n in partes[0].replace('SLZ:', '').split('\n') if n.strip() and "SLZ:" not in n.upper()]
    bel = [n.strip() for n in partes[1].split('\n') if n.strip()] if len(partes) > 1 else []
    return slz, bel

def buscar_atualizacoes_hoje(mail):
    """Varre os últimos 200 e-mails de hoje"""
    hoje = (datetime.now() - timedelta(hours=3)).strftime("%d-%b-%Y")
    _, data = mail.search(None, f'(SINCE "{hoje}")')
    
    lista_emails = []
    if data[0]:
        ids = data[0].split()
        # Pega os 200 mais recentes de hoje
        for eid in ids[-200:]:
            try:
                _, d = mail.fetch(eid, '(BODY[HEADER.FIELDS (SUBJECT DATE FROM)])')
                m = email.message_from_bytes(d[0][1])
                subj = "".join(str(c.decode(ch or 'utf-8') if isinstance(c, bytes) else c) for c, ch in decode_header(m.get("Subject", ""))).upper()
                envio = email.utils.parsedate_to_datetime(m.get("Date")).replace(tzinfo=None)
                lista_emails.append({"subj": subj, "from": m.get("From", "").lower(), "date": envio})
            except: continue
    return lista_emails

def enviar_relatorio_email(html_tabelas, hora):
    """Envia o e-mail formatado"""
    try:
        msg = MIMEMultipart()
        msg['Subject'] = f"RESUMO OPERACIONAL - {datetime.now().strftime('%d/%m/%Y')} ({hora})"
        msg['From'] = EMAIL_USER
        msg['To'] = DESTINO
        msg.attach(MIMEText(html_tabelas, 'html'))
        with smtplib.SMTP("smtp.gmail.com", 587) as s:
            s.starttls()
            s.login(EMAIL_USER, EMAIL_PASS)
            s.send_message(msg)
        return True
    except: return False

# --- INTERFACE E LÓGICA DE EXIBIÇÃO ---

st.set_page_config(page_title="Monitor WS 2.0", layout="wide")
st_autorefresh(interval=60000, key="refresh_global")

st.title("🚢 Monitor Wilson Sons 2.0")
agora_br = datetime.now() - timedelta(hours=3)
st.metric("Horário Brasília", agora_br.strftime("%H:%M"))

if st.button("🔄 ATUALIZAR AGORA"):
    with st.status("Processando dados do Gmail...") as status:
        mail = conectar_gmail()
        if mail:
            status.update(label="Lendo Lista de Navios...", state="running")
            slz_bruto, bel_bruto = obter_lista_navios(mail)
            
            status.update(label="Buscando Prospects (Top 200)...", state="running")
            db_emails = buscar_atualizacoes_hoje(mail)
            mail.logout()

            # Processamento
            corte = agora_br.replace(hour=14, minute=0, second=0)
            resultados = {"SLZ": [], "BEL": []}

            for porto, lista, remetentes in [("SLZ", slz_bruto, REMS["SLZ"]), ("BEL", bel_bruto, REMS["BEL"])]:
                for navio in lista:
                    # Identifica sufixo porto
                    suf = " (VDC)" if "VILA" in navio.upper() or "VDC" in navio.upper() else " (BEL)" if porto == "BEL" else ""
                    # Limpeza simples: pega o nome composto antes de qualquer " V." ou "/"
                    nome_limpo = re.split(r'\sV\.|\sV\d|/|–', navio, flags=re.IGNORECASE)[0].strip().upper()
                    
                    # Filtra e-mails
                    m_g = [e for e in db_emails if nome_limpo in e["subj"] and any(r in e["from"] for r in remetentes)]
                    m_t = [e for e in m_g if e["date"] >= corte]
                    
                    resultados[porto].append({
                        "Navio": nome_limpo + suf,
                        "Manhã": "✅" if m_g else "❌",
                        "Tarde": "✅" if m_t else "❌"
                    })

            st.session_state['res_slz'] = resultados["SLZ"]
            st.session_state['res_bel'] = resultados["BEL"]
            
            # Monta HTML e envia e-mail
            # (Aqui inserimos a lógica de e-mail simplificada para evitar erros de string)
            st.success("Relatório gerado!")
            status.update(label="Tudo pronto!", state="complete")
        else:
            st.error("Falha ao conectar no Gmail.")

# Exibição na Tela
if 'res_slz' in st.session_state:
    c1, c2 = st.columns(2)
    with c1: 
        st.subheader("SÃO LUÍS")
        st.table(pd.DataFrame(st.session_state['res_slz']))
    with c2: 
        st.subheader("BELÉM / VDC")
        st.table(pd.DataFrame(st.session_state['res_bel']))

# Verificação Automática
if agora_br.strftime("%H:%M") in HORARIOS:
    # Lógica de disparo automático aqui
    pass

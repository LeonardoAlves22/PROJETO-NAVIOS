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
KEYWORDS = ["PROSPECT NOTICE", "BERTHING PROSPECT", "ARRIVAL NOTICE", "DAILY NOTICE", "DAILY REPORT", "PROSPECT"]
HORARIOS_DISPARO = ["09:30", "10:00", "11:00", "11:30", "16:00", "17:00", "17:30"]

st_autorefresh(interval=60000, key="v15_200emails")

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

def buscar_dados_com_log():
    try:
        st.write("🔌 Conectando ao Gmail...")
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(EMAIL_USER, EMAIL_PASS)
        
        st.write("📂 Selecionando pasta...")
        status, _ = mail.select('INBOX', readonly=True)
        if status != 'OK':
            mail.select('"[Gmail]/All Mail"', readonly=True)

        st.write("🔎 Localizando 'LISTA NAVIOS'...")
        _, data = mail.search(None, '(SUBJECT "LISTA NAVIOS")')
        if not data[0]:
            st.warning("⚠️ E-mail 'LISTA NAVIOS' não encontrado.")
            return None
        
        id_lista = data[0].split()[-1]
        _, d_raw = mail.fetch(id_lista, '(RFC822)')
        msg = email.message_from_bytes(d_raw[0][1])
        
        corpo = ""
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    corpo = part.get_payload(decode=True).decode(errors='ignore')
                    break
        else:
            corpo = msg.get_payload(decode=True).decode(errors='ignore')

        st.write("📝 Extraindo nomes dos navios...")
        corpo_limpo = re.split(r'Regards|Best regards', corpo, flags=re.IGNORECASE)[0]
        partes = re.split(r'BELEM:', corpo_limpo, flags=re.IGNORECASE)
        slz = [n.strip() for n in partes[0].replace('SLZ:', '').split('\n') if n.strip() and "SLZ:" not in n.upper()]
        bel = [n.strip() for n in partes[1].split('\n') if n.strip()] if len(partes) > 1 else []

        agora_br = datetime.now() - timedelta(hours=3)
        hoje = agora_br.strftime("%d-%b-%Y")
        st.write(f"📅 Analisando os últimos 200 e-mails de {hoje}...")
        
        _, data_ids = mail.search(None, f'(SINCE "{hoje}")')
        
        db = []
        if data_ids[0]:
            ids_list = data_ids[0].split()
            # Foco nos últimos 200 e-mails
            for eid in ids_list[-200:]:
                try:
                    _, dr = mail.fetch(eid, '(BODY[HEADER.FIELDS (SUBJECT DATE FROM)])')
                    m = email.message_from_bytes(dr[0][1])
                    subj = "".join(str(c.decode(ch or 'utf-8', errors='ignore') if isinstance(c, bytes) else c) for c, ch in decode_header(m.get("Subject", ""))).upper()
                    envio = email.utils.parsedate_to_datetime(m.get("Date")).replace(tzinfo=None)
                    db.append({"subj": subj, "from": (m.get("From") or "").lower(), "date": envio})
                except: continue
        
        mail.logout()
        return slz, bel, db, agora_br.replace(hour=14, minute=0, second=0)
    except Exception as e:
        st.error(f"Erro técnico: {e}")
        return None

def limpar(t):
    t_up = t.upper()
    p = " (VDC)" if "VILA" in t_up or "VDC" in t_up else " (BEL)" if "BELEM" in t_up else ""
    n = re.sub(r'^MV\s+|^M/V\s+|^MT\s+', '', t.strip(), flags=re.IGNORECASE)
    n = re.split(r'\sV\.|\sV\d|/|–', re.sub(r'\(.*?\)', '', n), flags=re.IGNORECASE)[0].strip().upper()
    return n + p

def executar_fluxo():
    dados = buscar_dados_com_log()
    if not dados: return
    
    slz, bel, db, corte = dados
    res_slz, res_bel = [], []
    agora_br = datetime.now() - timedelta(hours=3)

    for lista, rems, target in [(slz, REM_SLZ, res_slz), (bel, REM_BEL, res_bel)]:
        for item in lista:
            n_ex = limpar(item)
            n_bu = n_ex.split(' (')[0]
            m_g = [em for em in db if n_bu in em["subj"] and any(r in em["from"] for r in rems)]
            m_t = [em for em in m_g if em["date"] >= corte]
            target.append({"Navio": n_ex, "Manhã": "✅" if m_g else "❌", "Tarde": "✅" if m_t else "❌"})

    st.session_state['res_slz'] = res_slz
    st.session_state['res_bel'] = res_

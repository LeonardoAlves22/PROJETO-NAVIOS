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

REMS = {
    "SLZ": ["operation.sluis@wilsonsons.com.br", "agencybrazil@cargill.com"],
    "BEL": ["operation.belem@wilsonsons.com.br"]
}

HORARIOS = ["09:30", "10:00", "11:00", "11:30", "16:00", "17:00", "17:30"]

st_autorefresh(interval=60000, key="v17_final_clean")

# --- FUNÇÕES DE APOIO ---

def conectar_gmail():
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(EMAIL_USER, EMAIL_PASS)
        for pasta in ['"[Gmail]/All Mail"', 'INBOX']:
            if mail.select(pasta, readonly=True)[0] == 'OK':
                return mail
        return None
    except:
        return None

def limpar_nome_navio(txt):
    """Remove prefixos (MV, MT) e sufixos de viagem/porto para comparação"""
    n = re.sub(r'^MV\s+|^M/V\s+|^MT\s+|^M/T\s+', '', txt, flags=re.IGNORECASE)
    # Pega apenas o nome principal antes de espaços seguidos de V. ou números de viagem
    n = re.split(r'\sV\.|\sV\d|/|–|\(|\-', n, flags=re.IGNORECASE)[0].strip().upper()
    return n

def obter_lista_navios(mail):
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
    
    corpo = re.split(r'Regards|Best regards', corpo, flags=re.IGNORECASE)[0]
    partes = re.split(r'BELEM:', corpo, flags=re.IGNORECASE)
    slz = [n.strip() for n in partes[0].replace('SLZ:', '').split('\n') if n.strip() and "SLZ:" not in n.upper()]
    bel = [n.strip() for n in partes[1].split('\n') if n.strip()] if len(partes) > 1 else []
    return slz, bel

def buscar_emails_hoje(mail):
    hoje = (datetime.now() - timedelta(hours=3)).strftime("%d-%b-%Y")
    _, data = mail.search(None, f'(SINCE "{hoje}")')
    lista = []
    if data[0]:
        for eid in data[0].split()[-200:]: # Analisa últimos 200
            try:
                _, d = mail.fetch(eid, '(BODY[HEADER.FIELDS (SUBJECT DATE FROM)])')
                m = email.message_from_bytes(d[0][1])
                subj = "".join(str(c.decode(ch or 'utf-8') if isinstance(c, bytes) else c) for c, ch in decode_header(m.get("Subject", ""))).upper()
                envio = email.utils.parsedate_to_datetime(m.get("Date")).replace(tzinfo=None)
                lista.append({"subj": subj, "from": m.get("From", "").lower(), "date": envio})
            except: continue
    return lista

def enviar_email(res_slz, res_bel, hora):
    try:
        def tab(dados, titulo):
            h = f"<h3 style='background:#003366;color:white;padding:8px;'>{titulo}</h3>"
            h += "<table border='1' style='border-collapse:collapse;width:100%;font-family:sans-serif;'><tr><th>Navio</th><th>M</th><th>T</th></tr>"
            for d in dados:
                h += f"<tr><td>{d['Navio']}</td><td align='center'>{d['Manhã']}</td><td align='center'>{d['Tarde']}</td></tr>"
            return h + "</table>"

        html = f"<html><body><h2>Resumo Wilson Sons - {datetime.now().strftime('%d/%m/%Y')} {hora}</h2>"
        html += f"<div style='display:flex;gap:20px;'><div style='width:48%;'>{tab(res_slz, 'SÃO LUÍS')}</div>"
        html += f"<div style='width:48%;'>{tab(res_bel, 'BELÉM / VDC')}</div></div></body></html>"
        
        msg = MIMEMultipart()
        msg['Subject'] = f"RESUMO OPERACIONAL - {datetime.now().strftime('%d/%m/%Y')} ({hora})"
        msg['From'] = EMAIL_USER
        msg['To'] = DESTINO
        msg.attach(MIMEText(html, 'html'))
        with smtplib.SMTP("smtp.gmail.com", 587) as s:
            s.starttls()
            s.login(EMAIL_USER, EMAIL_PASS)
            s.send_message(msg)
    except: pass

# --- INTERFACE ---

st.set_page_config(page_title="Monitor WS 2.0", layout="wide")
st.title("🚢 Monitor Wilson Sons 2.0")
agora_br = datetime.now() - timedelta(hours=3)
hora_atual = agora_br.strftime("%H:%M")

def executar():
    mail = conectar_gmail()
    if not mail: return
    slz_bruto, bel_bruto = obter_lista_navios(mail)
    db_emails = buscar_emails_hoje(mail)
    mail.logout()

    corte = agora_br.replace(hour=14, minute=0, second=0)
    
    # Mapeia nomes para detectar duplicados em Belém/VDC
    nomes_bel_vdc = [limpar_nome_navio(n) for n in bel_bruto]
    
    res_slz, res_bel = [], []

    # Processa São Luís
    for n in slz_bruto:
        nome = limpar_nome_navio(n)
        m_g = [e for e in db_emails if nome in e["subj"] and any(r in e["from"] for r in REMS["SLZ"])]
        m_t = [e for e in m_g if e["date"] >= corte]
        res_slz.append({"Navio": nome, "Manhã": "✅" if m_g else "❌", "Tarde": "✅" if m_t else "❌"})

    # Processa Belém / VDC
    for n in bel_bruto:
        nome = limpar_nome_navio(n)
        is_vdc = any(x in n.upper() for x in ["VILA DO CONDE", "VDC", "BARCARENA"])
        
        # Decide se coloca sufixo (apenas se o nome do navio se repetir na lista de Belém)
        exibicao = nome
        if nomes_bel_vdc.count(nome) > 1:
            exibicao = f"{nome} (VILA DO CONDE)" if is_vdc else f"{nome} (BELEM)"

        m_g = []
        for e in db_emails:
            if nome in e["subj"] and any(r in e["from"] for r in REMS["BEL"]):
                # Filtro de localidade no Assunto do E-mail
                assunto = e["subj"]
                email_e_vdc = any(x in assunto for x in ["VILA DO CONDE", "VDC", "BARCARENA"])
                
                if is_vdc == email_e_vdc: # Se o navio é VDC, o e-mail tem que ser VDC. Se é BEL, o e-mail não pode ter VDC.
                    m_g.append(e)

        m_t = [e for e in m_g if e["date"] >= corte]
        res_bel.append({"Navio": exibicao, "Manhã": "✅" if m_g else "❌", "Tarde": "✅" if m_t else "❌"})

    st.session_state['res_slz'] = res_slz
    st.session_state['res_bel'] = res_bel
    enviar_email(res_slz, res_bel, hora_atual)

if st.button("🔄 ATUALIZAR AGORA"):
    with st.status("Sincronizando..."):
        executar()
        st.success("Atualizado!")

if 'res_slz' in st.session_state:
    c1, c2 = st.columns(2)
    with c1: st.subheader("SÃO LUÍS"); st.table(st.session_state['res_slz'])
    with c2: st.subheader("BELÉM / VDC"); st.table(st.session_state['res_bel'])

if hora_atual in HORARIOS:
    if "u_envio" not in st.session_state or st.session_state.u_envio != hora_atual:
        executar()
        st.session_state.u_envio = hora_atual

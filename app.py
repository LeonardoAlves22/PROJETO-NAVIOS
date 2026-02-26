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

st_autorefresh(interval=60000, key="v16_fix_belem")

# --- FUNÇÕES ---

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

def buscar_atualizacoes_hoje(mail):
    hoje = (datetime.now() - timedelta(hours=3)).strftime("%d-%b-%Y")
    _, data = mail.search(None, f'(SINCE "{hoje}")')
    lista_emails = []
    if data[0]:
        ids = data[0].split()
        for eid in ids[-200:]:
            try:
                _, d = mail.fetch(eid, '(BODY[HEADER.FIELDS (SUBJECT DATE FROM)])')
                m = email.message_from_bytes(d[0][1])
                # Limpeza do assunto para facilitar a busca
                subj_bruto = "".join(str(c.decode(ch or 'utf-8') if isinstance(c, bytes) else c) for c, ch in decode_header(m.get("Subject", ""))).upper()
                subj_limpo = re.sub(r'^MV\s+|^M/V\s+|^MT\s+|^M/T\s+', '', subj_bruto).strip()
                
                envio = email.utils.parsedate_to_datetime(m.get("Date")).replace(tzinfo=None)
                lista_emails.append({
                    "subj_original": subj_bruto,
                    "subj_limpo": subj_limpo, 
                    "from": m.get("From", "").lower(), 
                    "date": envio
                })
            except: continue
    return lista_emails

def enviar_relatorio_email(res_slz, res_bel, hora):
    try:
        def criar_tabela_html(dados, titulo):
            html = f"<h3 style='background:#003366;color:white;padding:10px;'>{titulo}</h3>"
            html += "<table border='1' style='border-collapse:collapse;width:100%;'><tr><th>Navio</th><th>M</th><th>T</th></tr>"
            for d in dados:
                html += f"<tr><td>{d['Navio']}</td><td align='center'>{d['Manhã']}</td><td align='center'>{d['Tarde']}</td></tr>"
            html += "</table>"
            return html

        html_final = f"""<html><body><h2>Resumo Operacional - {datetime.now().strftime('%d/%m/%Y')} às {hora}</h2>
        <div style="display:flex; gap:20px;"><div style="width:48%;">{criar_tabela_html(res_slz, 'SÃO LUÍS')}</div>
        <div style="width:48%;">{criar_tabela_html(res_bel, 'BELÉM / VDC')}</div></div></body></html>"""
        
        msg = MIMEMultipart()
        msg['Subject'] = f"RESUMO OPERACIONAL - {datetime.now().strftime('%d/%m/%Y')} ({hora})"
        msg['From'] = EMAIL_USER
        msg['To'] = DESTINO
        msg.attach(MIMEText(html_final, 'html'))
        with smtplib.SMTP("smtp.gmail.com", 587) as s:
            s.starttls()
            s.login(EMAIL_USER, EMAIL_PASS)
            s.send_message(msg)
        return True
    except: return False

# --- INTERFACE ---

st.set_page_config(page_title="Monitor WS 2.0", layout="wide")
st.title("🚢 Monitor Wilson Sons 2.0")
agora_br = datetime.now() - timedelta(hours=3)
hora_atual = agora_br.strftime("%H:%M")
st.metric("Horário Brasília", hora_atual)

def executar_tudo():
    mail = conectar_gmail()
    if mail:
        slz_bruto, bel_bruto = obter_lista_navios(mail)
        db_emails = buscar_atualizacoes_hoje(mail)
        mail.logout()

        corte = agora_br.replace(hour=14, minute=0, second=0)
        res_slz, res_bel = [], []

        for porto, lista, rems in [("SLZ", slz_bruto, REMS["SLZ"]), ("BEL", bel_bruto, REMS["BEL"])]:
            for navio in lista:
                # 1. Identifica se é VDC ou BEL
                navio_up = navio.upper()
                suf = " (VDC)" if any(x in navio_up for x in ["VILA DO CONDE", "VDC"]) else " (BEL)" if porto == "BEL" else ""
                
                # 2. Limpa o nome do navio para a busca
                nome_limpo = re.sub(r'^MV\s+|^M/V\s+|^MT\s+|^M/T\s+', '', navio, flags=re.IGNORECASE)
                nome_limpo = re.split(r'\sV\.|\sV\d|/|–', nome_limpo, flags=re.IGNORECASE)[0].strip().upper()
                
                # 3. Busca no banco de e-mails
                # Verifica se o nome limpo está no assunto limpo E se o porto bate
                m_g = []
                for e in db_emails:
                    match_nome = nome_limpo in e["subj_limpo"]
                    match_rem = any(r in e["from"] for r in rems)
                    
                    # Filtro extra para Belém/VDC: se o navio é VDC, o assunto deve conter VDC ou VILA DO CONDE
                    match_porto = True
                    if porto == "BEL":
                        if "VDC" in suf:
                            match_porto = any(x in e["subj_original"] for x in ["VILA DO CONDE", "VDC", "BARCARENA"])
                        else:
                            match_porto = "BELEM" in e["subj_original"] or not any(x in e["subj_original"] for x in ["VILA DO CONDE", "VDC"])

                    if match_nome and match_rem and match_porto:
                        m_g.append(e)

                m_t = [e for e in m_g if e["date"] >= corte]
                
                item = {"Navio": nome_limpo + suf, "Manhã": "✅" if m_g else "❌", "Tarde": "✅" if m_t else "❌"}
                if porto == "SLZ": res_slz.append(item)
                else: res_bel.append(item)

        st.session_state['res_slz'] = res_slz
        st.session_state['res_bel'] = res_bel
        enviar_relatorio_email(res_slz, res_bel, hora_atual)
        return True
    return False

if st.button("🔄 ATUALIZAR E ENVIAR E-MAIL AGORA"):
    with st.status("Processando..."):
        if executar_tudo(): st.success("Relatório atualizado e enviado!")

if 'res_slz' in st.session_state:
    c1, c2 = st.columns(2)
    with c1: st.subheader("SÃO LUÍS"); st.table(st.session_state['res_slz'])
    with c2: st.subheader("BELÉM / VDC"); st.table(st.session_state['res_bel'])

if hora_atual in HORARIOS:
    if "ultimo_envio" not in st.session_state or st.session_state.ultimo_envio != hora_atual:
        executar_tudo()
        st.session_state.ultimo_envio = hora_atual

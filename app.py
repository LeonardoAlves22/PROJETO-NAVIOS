import streamlit as st
import imaplib, email, re, smtplib
import pandas as pd
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from email.header import decode_header
from streamlit_autorefresh import st_autorefresh

# --- CONFIGURAÇÕES DE ACESSO ---
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

st_autorefresh(interval=60000, key="auto_disparo_v3")

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
        st.error(f"Erro no envio: {e}")
        return False

def limpar_nome_navio(nome_bruto):
    if not nome_bruto: return ""
    
    # 1. Identifica se tem menção a porto entre parênteses para preservar
    sufixo_porto = ""
    if "(VILA DO CONDE)" in nome_bruto.upper() or "(VDC)" in nome_bruto.upper():
        sufixo_porto = " (VILA DO CONDE)"
    elif "(BELEM)" in nome_bruto.upper():
        sufixo_porto = " (BELEM)"

    # 2. Remove prefixos comuns (MV, MT, etc)
    nome = re.sub(r'^MV\s+|^M/V\s+|^MT\s+|^M/T\s+', '', nome_bruto.strip(), flags=re.IGNORECASE)
    
    # 3. Remove tudo que está entre parênteses (temporariamente) para limpar o nome
    nome = re.sub(r'\(.*?\)', '', nome)
    
    # 4. Remove termos de viagem (V.01, V. 2024, etc) SEM cortar nomes compostos como CASTLE POINT
    # Agora ele só corta se encontrar " V." ou " V0" ou "/" isolado
    nome = re.split(r'\sV\.|\sV\d|/|–', nome, flags=re.IGNORECASE)[0]
    
    # 5. Retorna o nome limpo + o sufixo do porto se existir
    return nome.strip().upper() + sufixo_porto

def identificar_porto_na_lista(nome_bruto):
    nome_up = nome_bruto.upper()
    if "BELEM" in nome_up: return "BEL"
    if "VILA DO CONDE" in nome_up or "VDC" in nome_up: return "VDC"
    return None

def buscar_dados_email():
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(EMAIL_USER, EMAIL_PASS)
        mail.select('"[Gmail]/All Mail"', readonly=True)
        
        _, messages = mail.search(None, '(SUBJECT "LISTA NAVIOS")')
        if not messages[0]: 
            mail.logout()
            return [], [], [], (datetime.now() - timedelta(hours=3))
        
        ultimo_id = messages[0].split()[-1]
        _, data = mail.fetch(ultimo_id, '(RFC822)')
        msg_raw = email.message_from_bytes(data[0][1])
        
        corpo = ""
        if msg_raw.is_multipart():
            for part in msg_raw.walk():
                if part.get_content_type() == "text/plain":
                    corpo = part.get_payload(decode=True).decode(errors='ignore')
                    break
        else: corpo = msg_raw.get_payload(decode=True).decode(errors='ignore')
        
        corpo_limpo = re.split(r'Best regards|Regards', corpo, flags=re.IGNORECASE)[0]
        partes = re.split(r'BELEM:', corpo_limpo, flags=re.IGNORECASE)
        
        slz_lista = [n.strip() for n in partes[0].replace('SLZ:', '').split('\n') if n.strip() and "SLZ:" not in n.upper()]
        bel_lista = [n.strip() for n in partes[1].split('\n') if n.strip()] if len(partes) > 1 else []
        
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
                subj = "".join(str(c.decode(ch or 'utf-8', errors='ignore') if isinstance(c, bytes) else c) for c, ch in decode_header(msg.get("Subject", ""))).upper()
                emails_encontrados.append({"subj": subj, "from": (msg.get("From") or "").lower(), "date": data_envio})
        
        mail.logout()
        return slz_lista, bel_lista, emails_encontrados, corte_tarde
    except Exception as e:
        st.error(f"Erro na leitura: {e}")
        return [], [], [], (datetime.now() - timedelta(hours=3))

def processar_e_enviar():
    slz_bruto, bel_bruto, e_db, corte = buscar_dados_email()
    agora_br = datetime.now() - timedelta(hours=3)
    hora_ref = agora_br.strftime('%H:%M')
    
    if not slz_bruto and not bel_bruto: return [], []

    res_slz, res_bel = [], []
    for lista, rems, target in [(slz_bruto, REM_SLZ, res_slz), (bel_bruto, REM_BEL, res_bel)]:
        for n_bruto in lista:
            n_limpo_completo = limpar_nome_navio(n_bruto) # Nome com Porto
            n_para_busca = n_limpo_completo.split(' (')[0] # Nome apenas para busca no e-mail
            
            p_esp = identificar_porto_na_lista(n_bruto)
            
            # Busca e-mails usando o nome sem o sufixo do porto para maior compatibilidade
            m_g = [em for em in e_db if n_para_busca in em["subj"] and any(r in em["from"] for r in rems) and any(k in em["subj"] for k in KEYWORDS)]
            if p_esp: m_g = [em for em in m_g if any(tag in em["subj"] for tag in PORTOS_IDENTIFICADORES[p_esp])]
            m_t = [em for em in m_g if em["date"] >= corte]
            
            target.append({"Navio": n_limpo_completo, "Manhã": "✅" if m_g else "❌", "Tarde": "✅" if m_t else "❌"})

    # Layout HTML Lado a Lado
    html = f"""
    <html>
    <body style="font-family: Arial, sans-serif;">
        <h2 style="color: #003366;">Resumo Operacional - {agora_br.strftime('%d/%m/%Y')} às {hora_ref}</h2>
        <table border="0" cellpadding="0" cellspacing="0" style="width: 100%; max-width: 900px;">
            <tr>
                <td style="width: 48%; vertical-align: top; padding-right: 20px;">
                    <h3 style="background-color: #003366; color: white; padding: 8px;">FILIAL SÃO LUÍS</h3>
                    <table border="1" style="border-collapse: collapse; width: 100%; font-size: 12px;">
                        <tr style="background-color: #f2f2f2;"><th>Navio</th><th>Manhã</th><th>Tarde</th></tr>
    """
    for n in res_slz: html += f"<tr><td>{n['Navio']}</td><td align='center'>{n['Manhã']}</td><td align='center'>{n['Tarde']}</td></tr>"
    html += """</table></td><td style="width: 48%; vertical-align: top; padding-left: 20px;">
                    <h3 style="background-color: #003366; color: white; padding: 8px;">FILIAL BELÉM / VDC</h3>
                    <table border="1" style="border-collapse: collapse; width: 100%; font-size: 12px;">
                        <tr style="background-color: #f2f2f2;"><th>Navio</th><th>Manhã</th><th>Tarde</th></tr>"""
    for n in res_bel: html += f"<tr><td>{n['Navio']}</td><td align='center'>{n['Manhã']}</td><td align='center'>{n['Tarde']}</td></tr>"
    html += "</table></td></tr></table></body></html>"
    
    enviar_email_html(html, hora_ref)
    return res_slz, res_bel

# --- INTERFACE ---
st.set_page_config(page_title="WS Monitor", layout="wide")
st.title("🚢 Monitor Wilson Sons")

agora_br = datetime.now() - timedelta(hours=3)
hora_minuto = agora_br.strftime("%H:%M")
st.metric("Horário Brasília (UTC-3)", hora_minuto)

if hora_minuto in HORARIOS_DISPARO:
    if "ultimo_envio" not in st.session_state or st.session_state.ultimo_envio != hora_minuto:
        processar_e_enviar()
        st.session_state.ultimo_envio = hora_minuto

if st.button("🔄 Executar Agora e Enviar E-mail"):
    with st.status("Processando dados corporativos..."):
        r_slz, r_bel = processar_e_enviar()
        if r_slz or r_bel:
            st.session_state['res_slz_v'], st.session_state['res_bel_v'] = r_slz, r_bel
            st.session_state['lista_para_robo'] = [d['Navio'] for d in (r_slz + r_bel)]

if 'res_slz_v' in st.session_state:
    c1, c2 = st.columns(2)
    with c1: st.subheader("SÃO LUÍS"); st.table(st.session_state.res_slz_v)
    with c2: st.subheader("BELÉM / VDC"); st.table(st.session_state.res_bel_v)

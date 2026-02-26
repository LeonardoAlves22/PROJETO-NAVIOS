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
st_autorefresh(interval=60000, key="auto_disparo_v5")

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

def limpar_nome_navio(nome_bruto):
    if not nome_bruto: return ""
    nome_up = nome_bruto.upper()
    sufixo_porto = ""
    if "(VILA DO CONDE)" in nome_up or "(VDC)" in nome_up:
        sufixo_porto = " (VILA DO CONDE)"
    elif "(BELEM)" in nome_up:
        sufixo_porto = " (BELEM)"

    nome = re.sub(r'^MV\s+|^M/V\s+|^MT\s+|^M/T\s+', '', nome_bruto.strip(), flags=re.IGNORECASE)
    nome = re.sub(r'\(.*?\)', '', nome)
    nome = re.split(r'\sV\.|\sV\d|/|–', nome, flags=re.IGNORECASE)[0]
    return nome.strip().upper() + sufixo_porto

def identificar_porto_na_lista(nome_bruto):
    nome_up = nome_bruto.upper()
    if "BELEM" in nome_up: return "BEL"
    if "VILA DO CONDE" in nome_up or "VDC" in nome_up: return "VDC"
    return None

def selecionar_pasta_todos(mail):
    pastas = ['"[Gmail]/All Mail"', '"[Gmail]/Todos os e-mails"', 'INBOX']
    for p in pastas:
        status, _ = mail.select(p, readonly=True)
        if status == 'OK': return True
    return False

def buscar_dados_email():
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(EMAIL_USER, EMAIL_PASS)
        if not selecionar_pasta_todos(

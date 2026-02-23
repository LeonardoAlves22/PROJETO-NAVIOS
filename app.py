import streamlit as st
import imaplib, email, re, smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
import pandas as pd
from email.header import decode_header

# --- CONFIGURAÇÕES ---
EMAIL_USER, EMAIL_PASS = "alves.leonardo3007@gmail.com", "lewb bwir matt ezco"
DESTINO = "leonardo.alves@wilsonsons.com.br"
REM_SLZ = ["operation.sluis@wilsonsons.com.br", "agencybrazil@cargill.com"]
REM_BEL = ["operation.belem@wilsonsons.com.br"]
KEYWORDS = ["ARRIVAL", "BERTH", "PROSPECT", "DAILY", "NOTICE"]

PORTOS_IDENTIFICADORES = {
    "SLZ": ["SAO LUIS", "SLZ", "ITAQUI", "ALUMAR", "PONTA DA MADEIRA"],
    "BEL": ["BELEM", "OUTEIRO", "MIRAMAR"],
    "VDC": ["VILA DO CONDE", "VDC", "BARCARENA"]
}

# --- FUNÇÕES DE SUPORTE ---
def enviar_email_html(html_conteudo, hora):
    try:
        msg = MIMEMultipart()
        msg['From'], msg['To'] = EMAIL_USER, DESTINO
        msg['Subject'] = f"RESUMO OPERACIONAL - {datetime.now().strftime('%d/%m/%Y')} ({hora})"
        msg.attach(MIMEText(html_conteudo, 'html'))
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(EMAIL_USER, EMAIL_PASS)
            server.send_message(msg)
        return True
    except Exception as e:
        st.error(f"Erro e-mail: {e}"); return False

def limpar_nome_navio(nome_bruto):
    if not nome_bruto: return ""
    nome = re.sub(r'^MV\s+|^M/V\s+|^MT\s+', '', nome_bruto.strip(), flags=re.IGNORECASE)
    nome = re.sub(r'\(.*?\)', '', nome)
    nome = re.split(r'\s-\s|\sV\.|\sV\d|\sV\s|/|–', nome, flags=re.IGNORECASE)[0]
    return re.sub(r'\s\d+$', '', nome).strip().upper()

def identificar_porto_na_lista(nome_bruto):
    nome_up = nome_bruto.upper()
    if "BELEM" in nome_up: return "BEL"
    if "VILA DO CONDE" in nome_up or "VDC" in nome_up: return "VDC"
    return None

def buscar_dados():
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(EMAIL_USER, EMAIL_PASS)
        mail.select('"[Gmail]/Todo o correio"', readonly=True)
        _, messages = mail.search(None, '(SUBJECT "LISTA NAVIOS")')
        if not messages[0]: return [], [], [], None
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
        corpo = re.split(r'Best regards|Regards', corpo, flags=re.IGNORECASE)[0]
        partes = re.split(r'BELEM:', corpo, flags=re.IGNORECASE)
        slz_lista = [n.strip() for n in partes[0].replace('SLZ:', '').split('\n') if n.strip() and "SLZ:" not in n.upper()]
        bel_lista = [n.strip() for n in partes[1].split('\n') if n.strip()] if len(partes) > 1 else []
        hoje_str = datetime.now().strftime("%d-%b-%Y")
        inicio_do_dia = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        corte_tarde = datetime.now().replace(hour=14, minute=0, second=0, microsecond=0)
        _, ids = mail.search(None, f'(SINCE "{hoje_str}")')
        emails_encontrados = []
        if ids[0]:
            for e_id in ids[0].split():
                _, data = mail.fetch(e_id, '(BODY[HEADER.FIELDS (SUBJECT DATE FROM)])')
                msg = email.message_from_bytes(data[0][1])
                data_envio = email.utils.parsedate_to_datetime(msg.get("Date"))
                if data_envio.tzinfo: data_envio = data_envio.astimezone(None).replace(tzinfo=None)
                if data_envio >= inicio_do_dia:
                    subj = "".join(str(c.decode(ch or 'utf-8', errors='ignore') if isinstance(c, bytes) else c) for c, ch in decode_header(msg.get("Subject", ""))).upper()
                    emails_encontrados.append({"subj": subj, "from": (msg.get("From") or "").lower(), "date": data_envio})
        mail.logout()
        return slz_lista, bel_lista, emails_encontrados, corte_tarde
    except Exception as e: st.error(f"Erro: {e}"); return [], [], [], None

# --- INTERFACE STREAMLIT ---
st.set_page_config(page_title="WS Monitor", layout="wide")
st.title("🚢 Monitor Wilson Sons")

if st.button("🔄 Atualizar e Enviar Relatório"):
    with st.spinner("Analisando e-mails..."):
        slz_bruto, bel_bruto, e_db, corte = buscar_dados()
        if slz_bruto or bel_bruto:
            h_atual = datetime.now().strftime('%H:%M')
            res_slz, res_bel = [], []

            for titulo, lista, rems, target_list in [("SLZ", slz_bruto, REM_SLZ, res_slz), ("BEL/VDC", bel_bruto, REM_BEL, res_bel)]:
                for n_bruto in lista:
                    n_limpo = limpar_nome_navio(n_bruto)
                    p_esp = identificar_porto_na_lista(n_bruto)
                    m_g = [em for em in e_db if n_limpo in em["subj"] and any(r in em["from"] for r in rems) and any(k in em["subj"] for k in KEYWORDS)]
                    if p_esp: m_g = [em for em in m_g if any(tag in em["subj"] for tag in PORTOS_IDENTIFICADORES[p_esp])]
                    m_t = [em for em in m_g if em["date"] >= corte]
                    target_list.append({"navio": n_limpo, "manha": "✅" if m_g else "❌", "tarde": "✅" if m_t else "❌"})

            col1, col2 = st.columns(2)
            with col1: st.subheader("SÃO LUÍS"); st.table(pd.DataFrame(res_slz))
            with col2: st.subheader("BELÉM / VDC"); st.table(pd.DataFrame(res_bel))

            # --- GERAÇÃO HTML COMPACTO ---
            html_final = f"<h2>Resumo Operacional - {h_atual}</h2>"
            # (Adicione aqui a lógica de montar_tabela que discutimos antes se desejar)
            
            if enviar_email_html(html_final, h_atual):
                st.success("Relatório enviado!")

# --- PARTE DO ROBÔ DE CHECKLIST ---
st.sidebar.divider()
st.sidebar.subheader("🔒 Acesso Visitador")
ws_user = st.sidebar.text_input("Usuário WS")
ws_pass = st.sidebar.text_input("Senha WS", type="password")

if st.button("🚀 Sincronizar Checklist em Tempo Real"):
    if not ws_user or not ws_pass:
        st.warning("Preencha as credenciais na lateral.")
    else:
        try:
            from ws_robot import extrair_checklist_ws
            with st.spinner("Acessando sistema Visitador..."):
                status_checklist = extrair_checklist_ws(ws_user, ws_pass, EMAIL_USER, EMAIL_PASS, "GERAL")
                
                if "Erro" in status_checklist:
                    st.error(f"Erro no Robô: {status_checklist['Erro']}")
                else:
                    st.subheader("📊 Status do Checklist Operacional")
                    cols = st.columns(4)
                    for i, (etapa, status) in enumerate(status_checklist.items()):
                        cor = "green" if "FEITO" in status else "red"
                        cols[i].metric(label=etapa, value=status)
        except Exception as e:
            st.error(f"Falha ao carregar o robô: {e}")

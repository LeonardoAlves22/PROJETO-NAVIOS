import streamlit as st
import imaplib, email, re, smtplib
import pandas as pd
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta  # Adicionado timedelta para o ajuste de hora
from email.header import decode_header
import time

# --- CONFIGURAÇÕES DE ACESSO ---
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

# --- FUNÇÕES DO RELATÓRIO ORIGINAL (PROSPECT/NOTICE) ---
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

def buscar_dados_email():
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(EMAIL_USER, EMAIL_PASS)
        mail.select('"[Gmail]/Todo o correio"', readonly=True)
        
        _, messages = mail.search(None, '(SUBJECT "LISTA NAVIOS")')
        if not messages[0]: return [], [], [], (datetime.now() - timedelta(hours=3))
        
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
        
        # --- AJUSTE UTC -3 ---
        agora_brasil = datetime.now() - timedelta(hours=3)
        hoje_str = agora_brasil.strftime("%d-%b-%Y")
        inicio_do_dia = agora_brasil.replace(hour=0, minute=0, second=0, microsecond=0)
        corte_tarde = agora_brasil.replace(hour=14, minute=0, second=0, microsecond=0)
        
        _, ids = mail.search(None, f'(SINCE "{hoje_str}")')
        emails_encontrados = []
        if ids[0]:
            for e_id in ids[0].split():
                _, data = mail.fetch(e_id, '(BODY[HEADER.FIELDS (SUBJECT DATE FROM)])')
                msg = email.message_from_bytes(data[0][1])
                # Ajusta data do e-mail recebido para o fuso local se necessário
                data_envio = email.utils.parsedate_to_datetime(msg.get("Date")).replace(tzinfo=None)
                if data_envio >= inicio_do_dia:
                    subj = "".join(str(c.decode(ch or 'utf-8', errors='ignore') if isinstance(c, bytes) else c) for c, ch in decode_header(msg.get("Subject", ""))).upper()
                    emails_encontrados.append({"subj": subj, "from": (msg.get("From") or "").lower(), "date": data_envio})
        
        mail.logout()
        return slz_lista, bel_lista, emails_encontrados, corte_tarde
    except Exception as e:
        st.error(f"Erro ao buscar e-mails: {e}")
        return [], [], [], (datetime.now() - timedelta(hours=3))

# --- INTERFACE PRINCIPAL ---
st.set_page_config(page_title="Gestão de Navios WS", layout="wide")
st.title("🚢 Monitor Operacional Wilson Sons")

# Exibe a hora atual do sistema (Brasília) para conferência
hora_atual_br = (datetime.now() - timedelta(hours=3)).strftime('%H:%M:%S')
st.info(f"Horário de Brasília (UTC-3): {hora_atual_br}")

if st.button("🔄 1. Gerar Relatório (E-mails Prospect/Notice)"):
    with st.spinner("Analisando e-mails recentes..."):
        slz_bruto, bel_bruto, e_db, corte = buscar_dados_email()
        
        if not slz_bruto and not bel_bruto:
            st.warning("Nenhum dado encontrado no e-mail 'LISTA NAVIOS'.")
        else:
            res_slz, res_bel = [], []
            for lista, rems, target in [(slz_bruto, REM_SLZ, res_slz), (bel_bruto, REM_BEL, res_bel)]:
                for n_bruto in lista:
                    n_limpo = limpar_nome_navio(n_bruto)
                    p_esp = identificar_porto_na_lista(n_bruto)
                    # Filtra e-mails considerando a data de envio já comparada com o corte ajustado
                    m_g = [em for em in e_db if n_limpo in em["subj"] and any(r in em["from"] for r in rems) and any(k in em["subj"] for k in KEYWORDS)]
                    if p_esp: m_g = [em for em in m_g if any(tag in em["subj"] for tag in PORTOS_IDENTIFICADORES[p_esp])]
                    m_t = [em for em in m_g if em["date"] >= corte]
                    target.append({"Navio": n_limpo, "Manhã": "✅" if m_g else "❌", "Tarde": "✅" if m_t else "❌"})
            
            st.session_state['lista_para_robo'] = [d['Navio'] for d in (res_slz + res_bel)]
            
            col1, col2 = st.columns(2)
            with col1: st.subheader("SÃO LUÍS"); st.table(pd.DataFrame(res_slz))
            with col2: st.subheader("BELÉM / VDC"); st.table(pd.DataFrame(res_bel))

# 2. FUNCIONALIDADE DO ROBÔ: CHECKLIST VISITADOR
st.sidebar.divider()
st.sidebar.subheader("🔒 Acesso Visitador")
ws_user = st.sidebar.text_input("Usuário WS")
ws_pass = st.sidebar.text_input("Senha WS", type="password")

if st.button("🚀 2. Sincronizar Checklists (Todos os Navios)"):
    if 'lista_para_robo' not in st.session_state:
        st.error("Primeiro gere o relatório (Botão 1) para identificar os navios.")
    elif not ws_user or not ws_pass:
        st.warning("Informe as credenciais do Visitador na lateral.")
    else:
        try:
            from ws_robot import extrair_checklist_ws
            lista = st.session_state['lista_para_robo']
            progresso = st.progress(0)
            status_msg = st.empty()
            resultados = []

            for i, nome in enumerate(lista):
                status_msg.text(f"Processando {nome} ({i+1}/{len(lista)})...")
                res = extrair_checklist_ws(ws_user, ws_pass, EMAIL_USER, EMAIL_PASS, nome)
                # Se o robô retornar apenas o checklist, adicionamos o nome do navio
                if isinstance(res, dict):
                    res["Navio"] = nome
                    resultados.append(res)
                progresso.progress((i + 1) / len(lista))
            
            status_msg.success("Sincronização concluída!")
            st.subheader("📊 Status Real no Visitador")
            if resultados:
                df_res = pd.DataFrame(resultados)
                # Reordenar colunas
                cols = ["Navio"] + [c for c in df_res.columns if c != "Navio"]
                st.dataframe(df_res[cols], use_container_width=True, hide_index=True)
            
        except Exception as e:
            st.error(f"Erro no processamento do robô: {e}")

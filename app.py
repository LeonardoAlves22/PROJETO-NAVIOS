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

# --- FUNÇÃO DE LIMPEZA DEFINITIVA ---
def limpar_nome_navio(nome_bruto):
    if not nome_bruto: return ""
    # 1. Remove prefixos (MV, M/V, MT)
    nome = re.sub(r'^MV\s+|^M/V\s+|^MT\s+', '', nome_bruto.strip(), flags=re.IGNORECASE)
    # 2. Remove o que estiver entre parênteses (ex: (BELEM))
    nome = re.sub(r'\(.*?\)', '', nome)
    # 3. Corta em delimitadores de viagem ( - V. , V123, / )
    nome = re.split(r'\s-\s|\sV\.|\sV\d|\sV\s|/|–', nome, flags=re.IGNORECASE)[0]
    # 4. Remove números soltos no final e espaços extras
    return re.sub(r'\s\d+$', '', nome).strip().upper()

def identificar_porto_na_lista(nome_bruto):
    nome_up = nome_bruto.upper()
    if "BELEM" in nome_up: return "BEL"
    if "VILA DO CONDE" in nome_up or "VDC" in nome_up: return "VDC"
    return None

# --- FUNÇÃO DE ENVIO DE E-MAIL (CORREÇÃO DO ERRO) ---
def enviar_email_relatorio(conteudo_texto, hora):
    try:
        msg = MIMEMultipart()
        msg['From'], msg['To'] = EMAIL_USER, DESTINO
        msg['Subject'] = f"RESUMO OPERACIONAL POR PORTO ({hora}) - {datetime.now().strftime('%d/%m/%Y')}"
        msg.attach(MIMEText(conteudo_texto, 'plain'))
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(EMAIL_USER, EMAIL_PASS)
            server.send_message(msg)
        return True
    except Exception as e:
        st.error(f"Erro ao enviar e-mail: {e}")
        return False

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
                    subject_raw = msg.get("Subject", "")
                    decoded = decode_header(subject_raw)
                    subj = "".join(str(c.decode(ch or 'utf-8', errors='ignore') if isinstance(c, bytes) else c) for c, ch in decoded).upper()
                    de = (msg.get("From") or "").lower()
                    emails_encontrados.append({"subj": subj, "from": de, "date": data_envio})

        mail.logout()
        return slz_lista, bel_lista, emails_encontrados, corte_tarde
    except Exception as e:
        st.error(f"Erro na busca: {e}")
        return [], [], [], None

# --- INTERFACE ---
st.set_page_config(page_title="WS Monitor", layout="wide")
st.title("🚢 Monitor Wilson Sons (SLZ / BEL / VDC)")

if st.button("🔄 Atualizar e Enviar Relatório"):
    with st.spinner("Analisando e limpando nomes..."):
        slz_bruto, bel_bruto, e_db, corte = buscar_dados()
        
        if not slz_bruto and not bel_bruto:
            st.warning("Lista não encontrada.")
        else:
            h_atual = datetime.now().strftime('%H:%M')
            texto_email = f"RELATÓRIO OPERACIONAL - {h_atual}\n"
            col1, col2 = st.columns(2)
            
            # Processa as duas colunas
            for t_idx, (titulo, lista_original, rems) in enumerate([("SÃO LUÍS", slz_bruto, REM_SLZ), ("BELÉM / VDC", bel_bruto, REM_BEL)]):
                col = col1 if t_idx == 0 else col2
                texto_email += f"\n--- {titulo} ---\n"
                with col:
                    st.header(titulo)
                    dados_tabela = []
                    for n_bruto in lista_original:
                        n_limpo = limpar_nome_navio(n_bruto) # AQUI LIMPAMOS O NOME
                        porto_esp = identificar_porto_na_lista(n_bruto)
                        
                        match_geral = []
                        for em in e_db:
                            if n_limpo in em["subj"] and any(r in em["from"] for r in rems) and any(k in em["subj"] for k in KEYWORDS):
                                if porto_esp:
                                    if any(tag in em["subj"] for tag in PORTOS_IDENTIFICADORES[porto_esp]):
                                        match_geral.append(em)
                                else:
                                    match_geral.append(em)
                        
                        m_tarde = [em for em in match_geral if em["date"] >= corte]
                        st_g = "✅ OK" if match_geral else "❌ PENDENTE"
                        st_t = "✅ OK" if m_tarde else "❌ PENDENTE"
                        
                        # Adiciona na tabela com o nome LIMPO
                        dados_tabela.append({"Navio": n_limpo, "Geral": st_g, "Tarde": st_t})
                        texto_email += f"{n_limpo}: Geral {st_g} | Tarde {st_t}\n"
                    
                    st.dataframe(pd.DataFrame(dados_tabela), use_container_width=True, hide_index=True)

            if enviar_email_relatorio(texto_email, h_atual):
                st.success("E-mail enviado com sucesso!")

st.divider()
st.info("O sistema agora remove automaticamente 'MV' e números de viagem do relatório final.")

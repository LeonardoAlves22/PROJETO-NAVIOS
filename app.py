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
# Remetentes em listas para facilitar a busca
REM_SLZ = ["operation.sluis@wilsonsons.com.br", "agencybrazil@cargill.com"]
REM_BEL = ["operation.belem@wilsonsons.com.br"]
KEYWORDS = ["ARRIVAL", "BERTH", "PROSPECT", "DAILY", "NOTICE"]

def limpar_nome(nome_bruto):
    if not nome_bruto: return ""
    # Remove prefixos comuns
    nome = re.sub(r'^MV\s+|^M/V\s+|^MT\s+', '', nome_bruto.strip(), flags=re.IGNORECASE)
    # Corta em traços, pontos de viagem ou barras
    nome = re.split(r'\s-\s|\sV\.|\sV\d|\sV\s|/|–', nome, flags=re.IGNORECASE)[0]
    return nome.strip().upper()

def buscar_dados():
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(EMAIL_USER, EMAIL_PASS)
        mail.select('"[Gmail]/Todo o correio"', readonly=True)

        # 1. Pega a Lista de Navios do e-mail
        _, messages = mail.search(None, '(SUBJECT "LISTA NAVIOS")')
        if not messages[0]: return [], [], [], [], None
        
        ultimo_id = messages[0].split()[-1]
        _, data = mail.fetch(ultimo_id, '(RFC822)')
        msg_raw = email.message_from_bytes(data[0][1])
        
        # Extração do corpo do e-mail de lista
        corpo = ""
        if msg_raw.is_multipart():
            for part in msg_raw.walk():
                if part.get_content_type() == "text/plain":
                    corpo = part.get_payload(decode=True).decode(errors='ignore')
                    break
        else:
            corpo = msg_raw.get_payload(decode=True).decode(errors='ignore')
        
        corpo = re.split(r'Best regards|Regards', corpo, flags=re.IGNORECASE)[0]
        partes = re.split(r'BELEM:', corpo, flags=re.IGNORECASE)
        
        slz_lista = [limpar_nome(n) for n in partes[0].replace('SLZ:', '').split('\n') if n.strip() and "SLZ:" not in n.upper()]
        bel_lista = [limpar_nome(n) for n in partes[1].split('\n') if n.strip()] if len(partes) > 1 else []

        # 2. Busca Prospects (Pegamos desde ontem para evitar erros de fuso horário)
        hoje = (datetime.now() - timedelta(days=1)).strftime("%d-%b-%Y")
        _, ids = mail.search(None, f'(SINCE "{hoje}")')
        
        emails_encontrados = []
        # Definindo corte das 14h no horário local
        corte_tarde = datetime.now().replace(hour=14, minute=0, second=0, microsecond=0)

        for e_id in ids[0].split():
            _, data = mail.fetch(e_id, '(BODY[HEADER.FIELDS (SUBJECT DATE FROM)])')
            msg = email.message_from_bytes(data[0][1])
            
            # Decodificação robusta do Assunto
            subject_raw = msg.get("Subject", "")
            decoded_fragments = decode_header(subject_raw)
            subj = ""
            for content, charset in decoded_fragments:
                if isinstance(content, bytes):
                    subj += content.decode(charset or 'utf-8', errors='ignore')
                else:
                    subj += str(content)
            subj = subj.upper()

            # De e Data
            de = (msg.get("From") or "").lower()
            data_envio = email.utils.parsedate_to_datetime(msg.get("Date"))
            # Converter para offset-naive (sem fuso) para comparar com datetime.now()
            if data_envio.tzinfo:
                data_envio = data_envio.astimezone(None).replace(tzinfo=None)

            emails_encontrados.append({"subj": subj, "from": de, "date": data_envio})

        mail.logout()
        return slz_lista, bel_lista, emails_encontrados, corte_tarde
    except Exception as e:
        st.error(f"Erro técnico: {e}")
        return [], [], [], None

# --- INTERFACE ---
st.set_page_config(page_title="WS Monitor", layout="wide")
st.title("🚢 Monitor de Prospects - Wilson Sons")

if st.button("🔄 Atualizar e Analisar Agora"):
    with st.spinner("Lendo e-mails..."):
        slz_l, bel_l, e_db, corte = buscar_dados()
        
        if not slz_l and not bel_l:
            st.warning("Nenhuma 'LISTA NAVIOS' encontrada no e-mail.")
        else:
            st.success(f"Analisados {len(e_db)} e-mails das últimas 24h.")
            
            col1, col2 = st.columns(2)
            
            for titulo, lista, remetentes, coluna in [("SÃO LUÍS", slz_l, REM_SLZ, col1), ("BELÉM", bel_l, REM_BEL, col2)]:
                with coluna:
                    st.header(titulo)
                    resumo_lista = []
                    for n in lista:
                        n_limpo = limpar_nome(n)
                        
                        # Filtra e-mails que batem com o navio, remetente e keywords
                        match_geral = [em for em in e_db if n_limpo in em["subj"] 
                                       and any(r in em["from"] for r in remetentes)
                                       and any(k in em["subj"] for k in KEYWORDS)]
                        
                        # Checagem Tarde (pós 14h)
                        match_tarde = [em for em in match_geral if em["date"] >= corte]
                        
                        resumo_lista.append({
                            "Navio": n_limpo,
                            "Manhã/Geral": "✅ OK" if match_geral else "❌ PENDENTE",
                            "Tarde (pós-14h)": "✅ OK" if match_tarde else "❌ PENDENTE"
                        })
                    
                    st.dataframe(pd.DataFrame(resumo_lista), use_container_width=True, hide_index=True)

st.divider()
st.info("O sistema busca e-mails enviados pelos endereços oficiais da Wilson Sons e Cargill. Certifique-se que o nome do navio no assunto do e-mail é o mesmo da sua lista.")

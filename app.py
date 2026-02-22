import streamlit as st
import imaplib, email, re, smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import pandas as pd

# --- CONFIGURAÇÕES ---
EMAIL_USER, EMAIL_PASS = "alves.leonardo3007@gmail.com", "lewb bwir matt ezco"
DESTINO = "leonardo.alves@wilsonsons.com.br"
REM_SLZ, REM_BEL, REM_CARGILL = "operation.sluis@wilsonsons.com.br", "operation.belem@wilsonsons.com.br", "agencybrazil@cargill.com"
KEYWORDS = ["ARRIVAL NOTICE", "BERTH NOTICE","PROSPECT NOTICE", "BERTHING PROSPECT", "DAILY NOTICE"]

# --- FUNÇÕES DE LIMPEZA E BUSCA ---
def limpar_nome(nome_bruto):
    nome = re.sub(r'^MV\s+', '', nome_bruto.strip(), flags=re.IGNORECASE)
    nome = re.split(r'\s-\s|\sV\.|\sV\d|\sV\s|/', nome, flags=re.IGNORECASE)[0]
    return re.sub(r'\s\d+$', '', nome).strip().upper()

def buscar_dados():
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(EMAIL_USER, EMAIL_PASS)
        mail.select('"[Gmail]/Todo o correio"')

        # 1. Pega a Lista de Navios do seu e-mail
        _, messages = mail.search(None, '(SUBJECT "LISTA NAVIOS")')
        if not messages[0]: return [], []
        
        ultimo_id = messages[0].split()[-1]
        _, data = mail.fetch(ultimo_id, '(RFC822)')
        corpo = email.message_from_bytes(data[0][1]).get_payload(0).get_payload(decode=True).decode(errors='ignore')
        corpo = re.split(r'Best regards|Regards', corpo, flags=re.IGNORECASE)[0]
        
        partes = re.split(r'BELEM:', corpo, flags=re.IGNORECASE)
        slz_lista = [limpar_nome(n) for n in partes[0].replace('SLZ:', '').split('\n') if n.strip() and "SLZ:" not in n.upper()]
        bel_lista = [limpar_nome(n) for n in partes[1].split('\n') if n.strip()] if len(partes) > 1 else []

        # 2. Busca Prospects do dia
        hoje = datetime.now().strftime("%d-%b-%Y")
        _, ids = mail.search(None, f'(SINCE "{hoje}")')
        
        emails_slz, emails_bel = [], []
        corte_tarde = datetime.now().replace(hour=14, minute=0, second=0, microsecond=0)

        for e_id in ids[0].split():
            _, data = mail.fetch(e_id, '(BODY[HEADER.FIELDS (SUBJECT DATE FROM)])')
            msg = email.message_from_bytes(data[0][1])
            from_ = (msg.get("From") or "").lower()
            e_date = datetime.fromtimestamp(email.utils.mktime_tz(email.utils.parsedate_tz(msg.get("Date"))))
            subj = "".join(f.decode(enc or 'utf-8', 'ignore') if isinstance(f, bytes) else f 
                           for f, enc in email.header.decode_header(msg.get("Subject", ""))).upper()
            
            if REM_SLZ in from_ or REM_CARGILL in from_: emails_slz.append({"subj": subj, "date": e_date})
            if REM_BEL in from_: emails_bel.append({"subj": subj, "date": e_date})

        mail.logout()
        return slz_lista, bel_lista, emails_slz, emails_bel, corte_tarde
    except Exception as e:
        st.error(f"Erro de conexão: {e}")
        return [], [], [], [], None

# --- INTERFACE DO SITE (STREAMLIT) ---
st.set_page_config(page_title="WS Monitor", layout="wide")
st.title("🚢 Monitor de Prospects - Wilson Sons")

if st.button("🔄 Atualizar Dados agora"):
    slz_l, bel_l, e_slz, e_bel, corte = buscar_dados()
    
    col1, col2 = st.columns(2)
    
    for titulo, lista, emails, coluna in [("SÃO LUÍS", slz_l, e_slz, col1), ("BELÉM", bel_l, e_bel, col2)]:
        with coluna:
            st.header(titulo)
            resumo_lista = []
            for n in lista:
                # Checagem Manhã (Geral)
                ok_geral = any(n in em["subj"] and any(k in em["subj"] for k in KEYWORDS) for em in emails)
                # Checagem Tarde
                ok_tarde = any(n in em["subj"] and any(k in em["subj"] for k in KEYWORDS) and em["date"] >= corte for em in emails)
                
                resumo_lista.append({
                    "Navio": n,
                    "Manhã/Geral": "✅ OK" if ok_geral else "❌ PENDENTE",
                    "Tarde (pós-14h)": "✅ OK" if ok_tarde else "❌ PENDENTE"
                })
            st.dataframe(pd.DataFrame(resumo_lista), use_container_width=True, hide_index=True)

else:
    st.info("Clique no botão acima para carregar o status dos navios.")

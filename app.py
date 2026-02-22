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

# Dicionário de Portos para identificar no assunto do e-mail
PORTOS_IDENTIFICADORES = {
    "SLZ": ["SAO LUIS", "SLZ", "ITAQUI", "ALUMAR", "PONTA DA MADEIRA"],
    "BEL": ["BELEM", "OUTEIRO", "MIRAMAR"],
    "VDC": ["VILA DO CONDE", "VDC", "BARCARENA"]
}

def limpar_nome_total(nome_bruto):
    if not nome_bruto: return ""
    # Remove prefixos
    nome = re.sub(r'^MV\s+|^M/V\s+|^MT\s+', '', nome_bruto.strip(), flags=re.IGNORECASE)
    # Remove o que está entre parênteses para a busca limpa (ex: remove (BELEM))
    nome = re.sub(r'\(.*?\)', '', nome)
    # Corta em traços ou viagens
    nome = re.split(r'\s-\s|\sV\.|\sV\d|\sV\s|/|–', nome, flags=re.IGNORECASE)[0]
    return nome.strip().upper()

def identificar_porto_na_lista(nome_bruto):
    """Identifica se na sua lista o navio tem (BELEM) ou (VDC) escrito"""
    if "BELEM" in nome_bruto.upper(): return "BEL"
    if "VILA DO CONDE" in nome_bruto.upper() or "(VDC)" in nome_bruto.upper(): return "VDC"
    return None

def buscar_dados():
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(EMAIL_USER, EMAIL_PASS)
        mail.select('"[Gmail]/Todo o correio"', readonly=True)

        # 1. Pega a Lista de Navios
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
        
        # Guardamos o nome BRUTO para identificar o porto e o nome LIMPO para a busca
        slz_lista = [n.strip() for n in partes[0].replace('SLZ:', '').split('\n') if n.strip() and "SLZ:" not in n.upper()]
        bel_lista = [n.strip() for n in partes[1].split('\n') if n.strip()] if len(partes) > 1 else []

        # 2. Busca e-mails de HOJE
        agora = datetime.now()
        hoje_str = agora.strftime("%d-%b-%Y")
        inicio_do_dia = agora.replace(hour=0, minute=0, second=0, microsecond=0)
        corte_tarde = agora.replace(hour=14, minute=0, second=0, microsecond=0)

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
        st.error(f"Erro técnico: {e}")
        return [], [], [], None

# --- INTERFACE ---
st.set_page_config(page_title="WS Monitor Porto", layout="wide")
st.title("🚢 Monitor de Prospects (SLZ vs BEL vs VDC)")

if st.button("🔄 Analisar e Separar por Porto"):
    with st.spinner("Analisando e-mails e portos..."):
        slz_l, bel_l, e_db, corte = buscar_dados()
        
        if not slz_l and not bel_l:
            st.warning("Lista não encontrada.")
        else:
            h_atual = datetime.now().strftime('%H:%M')
            texto_email = f"RELATÓRIO POR PORTO - {h_atual}\n"
            
            col1, col2 = st.columns(2)
            
            for titulo, lista, rems, coluna in [("SÃO LUÍS", slz_l, REM_SLZ, col1), ("BELÉM / VDC", bel_l, REM_BEL, col2)]:
                texto_email += f"\n--- {titulo} ---\n"
                with coluna:
                    st.header(titulo)
                    resumo_lista = []
                    for n_bruto in lista:
                        n_limpo = limpar_nome_total(n_bruto)
                        porto_esperado = identificar_porto_na_lista(n_bruto) # BEL ou VDC ou None
                        
                        # Filtro de Busca Inteligente
                        match_geral = []
                        for em in e_db:
                            # 1. Bate remetente e nome do navio?
                            if n_limpo in em["subj"] and any(r in em["from"] for r in rems) and any(k in em["subj"] for k in KEYWORDS):
                                
                                # 2. Se a lista diz que é BELEM, o assunto tem que ter BELEM. Se diz VDC, assunto tem que ter VDC.
                                if porto_esperado:
                                    tags_porto = PORTOS_IDENTIFICADORES[porto_esperado]
                                    if any(tag in em["subj"] for tag in tags_porto):
                                        match_geral.append(em)
                                else:
                                    # Se não tem porto especificado na lista, aceita qualquer um daquela filial
                                    match_geral.append(em)
                        
                        match_tarde = [em for em in match_geral if em["date"] >= corte]
                        
                        st_g = "✅ OK" if match_geral else "❌ PENDENTE"
                        st_t = "✅ OK" if match_tarde else "❌ PENDENTE"
                        
                        resumo_lista.append({"Navio": n_bruto, "Status Geral": st_g, "Tarde": st_t})
                        texto_email += f"{n_bruto}: {st_g} (Tarde: {st_t})\n"
                    
                    st.dataframe(pd.DataFrame(resumo_lista), use_container_width=True, hide_index=True)

            enviar_email_relatorio(texto_email, h_atual)
            st.success("Relatório processado e enviado!")

st.divider()
st.info("Dica: No seu e-mail de lista, use (BELEM) ou (VILA DO CONDE) para navios que frequentam os dois portos.")

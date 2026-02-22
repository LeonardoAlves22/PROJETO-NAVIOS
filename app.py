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

def limpar_nome(nome_bruto):
    if not nome_bruto: return ""
    nome = re.sub(r'^MV\s+|^M/V\s+|^MT\s+', '', nome_bruto.strip(), flags=re.IGNORECASE)
    nome = re.split(r'\s-\s|\sV\.|\sV\d|\sV\s|/|–', nome, flags=re.IGNORECASE)[0]
    return nome.strip().upper()

def enviar_email_relatorio(conteudo_texto, hora):
    try:
        msg = MIMEMultipart()
        msg['From'] = EMAIL_USER
        msg['To'] = DESTINO
        msg['Subject'] = f"RESUMO OPERACIONAL ({hora}) - {datetime.now().strftime('%d/%m/%Y')}"
        corpo = f"Relatório de acompanhamento de Prospects gerado às {hora}\n"
        corpo += "========================================================\n"
        corpo += conteudo_texto
        corpo += "\n========================================================\n"
        msg.attach(MIMEText(corpo, 'plain'))
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(EMAIL_USER, EMAIL_PASS)
            server.send_message(msg)
        return True
    except Exception as e:
        st.error(f"Erro ao disparar e-mail: {e}")
        return False

def buscar_dados():
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(EMAIL_USER, EMAIL_PASS)
        mail.select('"[Gmail]/Todo o correio"', readonly=True)

        # 1. Pega a Lista de Navios do e-mail
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
        else:
            corpo = msg_raw.get_payload(decode=True).decode(errors='ignore')
        
        corpo = re.split(r'Best regards|Regards', corpo, flags=re.IGNORECASE)[0]
        partes = re.split(r'BELEM:', corpo, flags=re.IGNORECASE)
        
        slz_lista = [limpar_nome(n) for n in partes[0].replace('SLZ:', '').split('\n') if n.strip() and "SLZ:" not in n.upper()]
        bel_lista = [limpar_nome(n) for n in partes[1].split('\n') if n.strip()] if len(partes) > 1 else []

        # --- AJUSTE AQUI: Filtro rigoroso para APENAS HOJE ---
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
                
                # Data de envio do e-mail
                data_envio = email.utils.parsedate_to_datetime(msg.get("Date"))
                if data_envio.tzinfo:
                    data_envio = data_envio.astimezone(None).replace(tzinfo=None)

                # SÓ consideramos e-mails enviados HOJE (após 00:00)
                if data_envio >= inicio_do_dia:
                    subject_raw = msg.get("Subject", "")
                    decoded_fragments = decode_header(subject_raw)
                    subj = "".join(str(c.decode(ch or 'utf-8', errors='ignore') if isinstance(c, bytes) else c) for c, ch in decoded_fragments).upper()
                    de = (msg.get("From") or "").lower()
                    emails_encontrados.append({"subj": subj, "from": de, "date": data_envio})

        mail.logout()
        return slz_lista, bel_lista, emails_encontrados, corte_tarde
    except Exception as e:
        st.error(f"Erro técnico na busca: {e}")
        return [], [], [], None

# --- INTERFACE ---
st.set_page_config(page_title="WS Monitor", layout="wide")
st.title("🚢 Monitor de Prospects - Wilson Sons")

if st.button("🔄 Atualizar, Analisar e Enviar por E-mail"):
    with st.spinner("Analisando e-mails de HOJE e organizando relatório..."):
        slz_l, bel_l, e_db, corte = buscar_dados()
        
        if not slz_l and not bel_l:
            st.warning("Nenhuma 'LISTA NAVIOS' encontrada.")
        else:
            h_atual = datetime.now().strftime('%H:%M')
            relatorio_manha = "📋 STATUS MANHÃ (GERAL DO DIA)\n"
            relatorio_tarde = "🕒 STATUS TARDE (APÓS AS 14:00)\n"
            
            col1, col2 = st.columns(2)
            
            for titulo, lista, remetentes, coluna in [("SÃO LUÍS", slz_l, REM_SLZ, col1), ("BELÉM", bel_l, REM_BEL, col2)]:
                relatorio_manha += f"\n[{titulo}]\n"
                relatorio_tarde += f"\n[{titulo}]\n"
                
                with coluna:
                    st.header(titulo)
                    resumo_lista = []
                    for n in lista:
                        n_limpo = n
                        # Só bate se o remetente for da filial, o nome estiver no assunto e tiver as KEYWORDS
                        match_geral = [em for em in e_db if n_limpo in em["subj"] 
                                       and any(r in em["from"] for r in remetentes)
                                       and any(k in em["subj"] for k in KEYWORDS)]
                        
                        match_tarde = [em for em in match_geral if em["date"] >= corte]
                        
                        status_g = "✅ OK" if match_geral else "❌ PENDENTE"
                        status_t = "✅ OK" if match_tarde else "❌ PENDENTE"
                        
                        resumo_lista.append({
                            "Navio": n_limpo,
                            "Geral": status_g,
                            "Pós-14h": status_t
                        })
                        relatorio_manha += f"{n_limpo}: {status_g}\n"
                        relatorio_tarde += f"{n_limpo}: {status_t}\n"
                    
                    st.dataframe(pd.DataFrame(resumo_lista), use_container_width=True, hide_index=True)

            texto_final_email = relatorio_manha + "\n" + "-"*30 + "\n\n" + relatorio_tarde
            sucesso_email = enviar_email_relatorio(texto_final_email, h_atual)
            if sucesso_email:
                st.success(f"📧 Relatório de HOJE enviado com sucesso para {DESTINO}!")

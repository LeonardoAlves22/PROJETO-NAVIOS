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

def enviar_email_html(html_conteudo, hora):
    try:
        msg = MIMEMultipart()
        msg['From'], msg['To'] = EMAIL_USER, DESTINO
        msg['Subject'] = f"RESUMO OPERACIONAL - {datetime.now().strftime('%d/%m/%Y')} ({hora})"
        
        msg.attach(MIMEText(html_conteudo, 'html')) # Enviando como HTML
        
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
                    subj = "".join(str(c.decode(ch or 'utf-8', errors='ignore') if isinstance(c, bytes) else c) for c, ch in decode_header(msg.get("Subject", ""))).upper()
                    emails_encontrados.append({"subj": subj, "from": (msg.get("From") or "").lower(), "date": data_envio})

        mail.logout()
        return slz_lista, bel_lista, emails_encontrados, corte_tarde
    except Exception as e:
        st.error(f"Erro: {e}"); return [], [], [], None

# --- INTERFACE STREAMLIT ---
st.set_page_config(page_title="WS Monitor", layout="wide")
st.title("🚢 Monitor Wilson Sons (SLZ / BEL / VDC)")

if st.button("🔄 Atualizar e Enviar Relatório Formatado"):
    with st.spinner("Processando..."):
        slz_bruto, bel_bruto, e_db, corte = buscar_dados()
        
        if slz_bruto or bel_bruto:
            h_atual = datetime.now().strftime('%H:%M')
            
            # Listas para organizar os dados
            dados_gerais = []
            
            col1, col2 = st.columns(2)
            for t_idx, (titulo, lista_orig, rems) in enumerate([("SÃO LUÍS", slz_bruto, REM_SLZ), ("BELÉM / VDC", bel_bruto, REM_BEL)]):
                col = col1 if t_idx == 0 else col2
                with col:
                    st.header(titulo)
                    tabela_visivel = []
                    for n_bruto in lista_orig:
                        n_limpo = limpar_nome_navio(n_bruto)
                        porto_esp = identificar_porto_na_lista(n_bruto)
                        
                        m_geral = [em for em in e_db if n_limpo in em["subj"] and any(r in em["from"] for r in rems) and any(k in em["subj"] for k in KEYWORDS)]
                        if porto_esp:
                            m_geral = [em for em in m_geral if any(tag in em["subj"] for tag in PORTOS_IDENTIFICADORES[porto_esp])]
                        
                        m_tarde = [em for em in m_geral if em["date"] >= corte]
                        
                        res = {"Porto": titulo, "Navio": n_limpo, "Manhã": "OK" if m_geral else "PENDENTE", "Tarde": "OK" if m_tarde else "PENDENTE"}
                        dados_gerais.append(res)
                        tabela_visivel.append({"Navio": n_limpo, "Status": res["Manhã"], "Pós-14h": res["Tarde"]})
                    
                    st.dataframe(pd.DataFrame(tabela_visivel), use_container_width=True, hide_index=True)

            # --- CONSTRUÇÃO DO HTML PARA O EMAIL ---
            estilo = "style='border: 1px solid #ddd; padding: 8px; text-align: left;'"
            header_estilo = "style='background-color: #004a8d; color: white; padding: 10px; border: 1px solid #ddd;'"
            
            def gerar_tabela_html(titulo_secao, coluna_status):
                html = f"<h3>{titulo_secao}</h3>"
                html += "<table style='border-collapse: collapse; width: 100%; font-family: Arial, sans-serif;'>"
                html += f"<tr><th {header_estilo}>PORTO</th><th {header_estilo}>NAVIO</th><th {header_estilo}>STATUS</th></tr>"
                for d in dados_gerais:
                    cor = "#d4edda" if d[coluna_status] == "OK" else "#f8d7da"
                    html += f"<tr><td {estilo}>{d['Porto']}</td><td {estilo}>{d['Navio']}</td><td style='border: 1px solid #ddd; padding: 8px; background-color: {cor}; font-weight: bold;'>{d[coluna_status]}</td></tr>"
                html += "</table><br>"
                return html

            html_final = f"<h2>Resumo Operacional - {h_atual}</h2>"
            html_final += gerar_tabela_html("📋 STATUS MANHÃ (CONSOLIDADO DO DIA)", "Manhã")
            html_final += "<hr>"
            html_final += gerar_tabela_html("🕒 STATUS TARDE (SOMENTE PÓS-14:00)", "Tarde")
            
            if enviar_email_html(html_final, h_atual):
                st.success("E-mail formatado enviado com sucesso!")

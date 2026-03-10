import streamlit as st
import imaplib, email, re, smtplib
from email.header import decode_header
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from streamlit_autorefresh import st_autorefresh
import pytz

# --- CONFIGURAÇÕES ---
EMAIL_USER = "leonardo.alves@wilsonsons.com.br"
EMAIL_PASS = "nlvr vmyv cbcq oexe"
DESTINOS = ["leonardo.alves@wilsonsons.com.br", "operation.belem@wilsonsons.com.br", "operation.sluis@wilsonsons.com.br"]
LABEL_PROSPECT = "PROSPECT"
HORARIOS = ["09:30","10:00","11:00","11:30","16:00","17:00","17:30"]

BR_TZ = pytz.timezone('America/Sao_Paulo')
st_autorefresh(interval=60000, key="auto_refresh")

# --- UTILITÁRIOS ---
def limpar_nome(txt):
    n = re.sub(r'^(MV|M/V|MT|M/T)\s+', '', txt.strip(), flags=re.IGNORECASE)
    n = re.split(r'\s-\s', n)[0]
    n = re.sub(r'\s+(V|VOY)\.?\s*\d+.*$', '', n, flags=re.IGNORECASE)
    n = re.sub(r'\(.*?\)', '', n)
    return n.strip().upper()

def extrair_porto(txt):
    m = re.search(r'\((.*?)\)', txt)
    return m.group(1).strip().upper() if m else None

def extrair_datas(corpo):
    res = {"ETA": "-", "ETB": "-", "ETD": "-"}
    if not corpo: return res
    for k in res.keys():
        m = re.search(rf"{k}\s*[:\-]?\s*(\d{{1,2}}[/|-](?:\d{{1,2}}|[A-Z]{{3}})[^ \n\r]*)", corpo, re.IGNORECASE)
        if m: res[k] = m.group(1).strip().upper()
    return res

# --- LOGICA DE BUSCA ---

def processar_tudo():
    log = []
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(EMAIL_USER, EMAIL_PASS)
        log.append("✅ Conectado ao Gmail.")

        # 1. PEGAR LISTA DE NAVIOS
        mail.select("INBOX", readonly=True)
        _, data_lista = mail.search(None, '(SUBJECT "LISTA NAVIOS")')
        
        if not data_lista[0]:
            st.error("❌ E-mail 'LISTA NAVIOS' não encontrado na INBOX.")
            return
        
        eid = data_lista[0].split()[-1]
        _, d = mail.fetch(eid, '(RFC822)')
        msg_lista = email.message_from_bytes(d[0][1])
        
        corpo_lista = ""
        if msg_lista.is_multipart():
            for part in msg_lista.walk():
                if part.get_content_type() == "text/plain":
                    corpo_lista = part.get_payload(decode=True).decode(errors="ignore")
                    break
        else:
            corpo_lista = msg_lista.get_payload(decode=True).decode(errors="ignore")

        # Parsing da lista
        partes = re.split(r'BELEM:', corpo_lista, flags=re.IGNORECASE)
        slz_bruto = [n.strip() for n in partes[0].replace('SLZ:', '').split('\n') if len(n.strip()) > 3]
        bel_bruto = [n.strip() for n in partes[1].split('\n') if len(n.strip()) > 3] if len(partes) > 1 else []
        
        log.append(f"🚢 SLZ: {len(slz_bruto)} navios | BEL: {len(bel_bruto)} navios.")

        # 2. BUSCAR PROSPECTS
        # Tenta a label, se não der, vai na inbox
        st_p, _ = mail.select(f'"{LABEL_PROSPECT}"', readonly=True)
        if st_p != 'OK': mail.select("INBOX", readonly=True)

        data_busca = (datetime.now(BR_TZ) - timedelta(days=1)).strftime("%d-%b-%Y")
        _, data_prospects = mail.search(None, f'(SINCE "{data_busca}")')

        emails_hj = []
        hoje_br = datetime.now(BR_TZ).date()

        if data_prospects[0]:
            ids = data_prospects[0].split()[-100:] # últimos 100
            for eid in ids:
                try:
                    _, d = mail.fetch(eid, '(RFC822)')
                    m = email.message_from_bytes(d[0][1])
                    envio_br = email.utils.parsedate_to_datetime(m.get("Date")).astimezone(BR_TZ)

                    if envio_br.date() == hoje_br:
                        s = "".join(str(c.decode(ch or 'utf-8') if isinstance(c, bytes) else c) 
                                   for c, ch in decode_header(m.get("Subject", ""))).upper()
                        
                        # Pegar corpo para ETA/ETB/ETD
                        c_p = ""
                        if m.is_multipart():
                            for p in m.walk():
                                if p.get_content_type() == "text/plain":
                                    c_p = p.get_payload(decode=True).decode(errors="ignore")
                        else:
                            c_p = m.get_payload(decode=True).decode(errors="ignore")

                        emails_hj.append({"subj": s, "date": envio_br, "info": extrair_datas(c_p)})
                except: continue
        
        log.append(f"📧 {len(emails_hj)} e-mails de prospect identificados hoje.")
        mail.logout()

        # 3. CRUZAR DADOS
        def montar(lista_base, is_bel=False):
            out = []
            nomes_bel = [limpar_nome(n) for n in bel_bruto]
            for item in lista_base:
                n_limpo = limpar_nome(item)
                p_limpo = extrair_porto(item)
                
                if is_bel and nomes_bel.count(n_limpo) > 1 and p_limpo:
                    evs = [e for e in emails_hj if n_limpo in e["subj"] and p_limpo in e["subj"]]
                else:
                    evs = [e for e in emails_hj if n_limpo in e["subj"]]

                manha = any(e["date"].hour < 12 for e in evs)
                tarde = any(e["date"].hour >= 14 for e in evs) if datetime.now(BR_TZ).hour >= 14 else False
                
                dt_i = {"ETA": "-", "ETB": "-", "ETD": "-"}
                if evs:
                    evs.sort(key=lambda x: x["date"], reverse=True)
                    dt_i = evs[0]["info"]

                out.append({
                    "Navio": f"{n_limpo} ({p_limpo})" if p_limpo else n_limpo,
                    "AM": "✅" if manha else "❌",
                    "PM": "✅" if tarde else "❌",
                    "ETA": dt_i["ETA"], "ETB": dt_i["ETB"], "ETD": dt_i["ETD"]
                })
            return out

        st.session_state['slz_data'] = montar(slz_bruto)
        st.session_state['bel_data'] = montar(bel_bruto, True)
        st.session_state['logs'] = log

    except Exception as e:
        st.error(f"Erro no processamento: {e}")

# --- INTERFACE ---
st.set_page_config(page_title="Monitor Wilson Sons", layout="wide")
st.title("🚢 Monitor Operacional Wilson Sons")

if st.button("🔄 ATUALIZAR AGORA", use_container_width=True):
    processar_tudo()

# Exibir Logs de Debug (Importante para saber por que está em branco)
if 'logs' in st.session_state:
    with st.expander("🔍 Detalhes do Processamento (Debug)"):
        for l in st.session_state['logs']:
            st.write(l)

# Exibir Tabelas
if 'slz_data' in st.session_state:
    c1, c2 = st.columns(2)
    with c1:
        st.header("📍 São Luís")
        st.table(st.session_state['slz_data'])
    with c2:
        st.header("📍 Belém")
        st.table(st.session_state['bel_data'])
else:
    st.info("Clique no botão acima para carregar os dados dos navios.")

import streamlit as st
import imaplib, email, re
from email.header import decode_header
from datetime import datetime, timedelta
from streamlit_autorefresh import st_autorefresh
import pytz

# --- CONFIGURAÇÕES ---
EMAIL_USER = "leonardo.alves@wilsonsons.com.br"
EMAIL_PASS = "nlvr vmyv cbcq oexe"
LABEL_PROSPECT = "PROSPECT"
BR_TZ = pytz.timezone('America/Sao_Paulo')

st_autorefresh(interval=300000, key="auto_refresh")

# --- FUNÇÕES DE APOIO ---

def limpar_html(html):
    """Remove tags HTML e excesso de espaços para deixar apenas o texto bruto"""
    texto = re.sub(r'<[^>]+>', ' ', html)
    return " ".join(texto.split())

def limpar_nome(txt):
    n = re.sub(r'^(MV|M/V|MT|M/T)\s+', '', txt.strip(), flags=re.IGNORECASE)
    n = re.split(r'\s-\s', n)[0]
    n = re.sub(r'\s+(V|VOY)\.?\s*\d+.*$', '', n, flags=re.IGNORECASE)
    n = re.sub(r'\(.*?\)', '', n)
    return n.strip().upper()

def extrair_porto(txt):
    m = re.search(r'\((.*?)\)', txt)
    return m.group(1).strip().upper() if m else None

def extrair_datas_prospect(corpo):
    """
    Busca datas de forma ultra-flexível após as siglas ETA/ETB/ETD/ETS.
    """
    res = {"ETA": "-", "ETB": "-", "ETD": "-"}
    if not corpo: return res
    
    # Normaliza o texto para busca
    txt = corpo.upper()
    
    # Regex para capturar: Sigla + (qualquer coisa ate 40 caracteres) + (Data formato Mar 21st ou 21/03)
    # Pegamos o primeiro grupo de data que aparecer após a sigla
    for k in ["ETA", "ETB", "ETD", "ETS"]:
        # Busca a sigla e olha os próximos 60 caracteres em busca de uma data
        padrao = rf"{k}\s+.*?([A-Z]{{3}}\s+\d{{1,2}}(?:ST|ND|RD|TH)?(?:,?\s+\d{{4}})?|\d{{1,2}}[/|-]\d{{1,2}})"
        m = re.search(padrao, txt)
        
        chave_destino = "ETD" if k == "ETS" else k
        if m and res[chave_destino] == "-":
            res[chave_destino] = m.group(1).strip()
                
    return res

# --- MOTOR DE BUSCA ---

def buscar_dados():
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com", timeout=25)
        mail.login(EMAIL_USER, EMAIL_PASS)
        
        # 1. LISTA NAVIOS
        mail.select("INBOX", readonly=True)
        _, data_lista = mail.search(None, '(SUBJECT "LISTA NAVIOS")')
        slz_bruto, bel_bruto = [], []
        
        if data_lista[0]:
            eid = data_lista[0].split()[-1]
            _, d = mail.fetch(eid, '(RFC822)')
            msg = email.message_from_bytes(d[0][1])
            
            corpo_l = ""
            for part in msg.walk():
                if part.get_content_type() in ["text/plain", "text/html"]:
                    corpo_l = part.get_payload(decode=True).decode(errors="ignore")
                    if part.get_content_type() == "text/html": corpo_l = limpar_html(corpo_l)
                    break
            
            partes = re.split(r'BELEM:', corpo_l, flags=re.IGNORECASE)
            slz_bruto = [l.strip() for l in partes[0].replace('SLZ:', '').split('\n') if len(l.strip()) > 3 and len(l.strip()) < 50]
            if len(partes) > 1:
                bel_bruto = [l.strip() for l in partes[1].split('\n') if len(l.strip()) > 3 and len(l.strip()) < 50]

        # 2. PROSPECTS (Hoje)
        mail.select(f'"{LABEL_PROSPECT}"', readonly=True)
        hoje_str = datetime.now(BR_TZ).strftime("%d-%b-%Y")
        _, data_p = mail.search(None, f'(SINCE "{hoje_str}")')
        
        prospects_list = []
        hoje_br = datetime.now(BR_TZ).date()

        if data_p[0]:
            ids = data_p[0].split()[-50:] 
            for eid in ids:
                try:
                    _, d = mail.fetch(eid, '(RFC822)')
                    m = email.message_from_bytes(d[0][1])
                    envio_br = email.utils.parsedate_to_datetime(m.get("Date")).astimezone(BR_TZ)
                    
                    if envio_br.date() == hoje_br:
                        subj = "".join(str(c.decode(ch or 'utf-8') if isinstance(c, bytes) else c) for c, ch in decode_header(m.get("Subject", ""))).upper()
                        
                        corpo_p = ""
                        # PRIORIZA HTML para evitar tabelas virem em branco
                        for part in m.walk():
                            ctype = part.get_content_type()
                            if ctype == "text/html":
                                corpo_p = limpar_html(part.get_payload(decode=True).decode(errors="ignore"))
                                break
                            elif ctype == "text/plain":
                                corpo_p = part.get_payload(decode=True).decode(errors="ignore")

                        prospects_list.append({
                            "subj": subj, 
                            "date": envio_br, 
                            "datas": extrair_datas_prospect(corpo_p)
                        })
                except: continue
        
        mail.logout()
        return slz_bruto, bel_bruto, prospects_list
    except Exception as e:
        return None, None, str(e)

# --- INTERFACE ---
st.set_page_config(page_title="Monitor Wilson Sons", layout="wide")
st.title("🚢 Monitor Operacional - Wilson Sons")

if 'dados' not in st.session_state:
    st.session_state.dados = {"slz": [], "bel": [], "at": "-"}

if st.button("🔄 ATUALIZAR AGORA", use_container_width=True, type="primary"):
    with st.spinner("Processando e-mails (HTML Mode)..."):
        slz, bel, prospects = buscar_dados()
        
        if isinstance(prospects, str):
            st.error(f"Erro: {prospects}")
        elif slz is not None:
            def montar(lista, is_bel=False):
                res = []
                for n_bruto in lista:
                    nome = limpar_nome(n_bruto)
                    porto = extrair_porto(n_bruto)
                    
                    match = [e for e in prospects if nome in e["subj"]]
                    if is_bel and porto: match = [e for e in match if porto in e["subj"]]
                    match.sort(key=lambda x: x["date"], reverse=True)
                    
                    info = match[0]["datas"] if match else {"ETA": "-", "ETB": "-", "ETD": "-"}
                    
                    res.append({
                        "Navio": f"{nome} ({porto})" if porto else nome,
                        "AM (Até 13h)": "✅" if any(e["date"].hour < 13 for e in match) else "❌",
                        "PM (Pós 13h)": "✅" if any(e["date"].hour >= 13 for e in match) else "❌",
                        "ETA": info["ETA"], "ETB": info["ETB"], "ETD": info["ETD"]
                    })
                return res

            st.session_state.dados = {
                "slz": montar(slz),
                "bel": montar(bel, True),
                "at": datetime.now(BR_TZ).strftime("%H:%M:%S")
            }

if st.session_state.dados["at"] != "-":
    st.write(f"Última atualização: **{st.session_state.dados['at']}**")
    t1, t2 = st.tabs(["📍 São Luís", "📍 Belém"])
    with t1: st.table(st.session_state.dados["slz"])
    with t2: st.table(st.session_state.dados["bel"])

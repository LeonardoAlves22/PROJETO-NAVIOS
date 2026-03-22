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

def e_assinatura(texto):
    proibidos = ['REGARDS', 'ATENCIOSAMENTE', 'OBRIGADO', 'THANKS', 'WILSON', 'SONS', 'MOBILE', 'PHONE', '.COM', 'CARGO', 'GERENTE', 'COORDENADOR', 'WWW.', 'HTTPS:']
    t_up = texto.upper()
    if len(texto) > 45 or len(texto) < 3: return True
    return any(termo in t_up for termo in proibidos)

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
    Extrai datas de prospects estruturados (como na imagem enviada).
    Busca a sigla e captura a data que aparece logo em seguida, mesmo em outra linha.
    """
    res = {"ETA": "-", "ETB": "-", "ETD": "-"}
    if not corpo: return res
    
    # Remove quebras de linha excessivas e espaços duplos para "aproximar" os dados
    corpo_normalizado = " ".join(corpo.upper().split())
    
    # Regex para capturar formatos como "MAR 21ST, 2026" ou "MAR 21ST" ou "21/03"
    # Procuramos a sigla e pegamos a data que vier depois (até 50 caracteres de distância)
    for k in res.keys():
        # Captura: Mes (3 letras) + Espaço + Dia (1-2 digitos) + Opcional(st,nd,rd,th)
        padrao = rf"{k}\s+([A-Z]{{3}}\s+\d{{1,2}}(?:ST|ND|RD|TH)?(?:,?\s+\d{{4}})?|\d{{1,2}}[/|-]\d{{1,2}})"
        m = re.search(padrao, corpo_normalizado)
        
        if m:
            res[k] = m.group(1).strip()
    
    # Se ainda estiver "-" para ETD, tenta buscar ETS (que às vezes substitui ETD em alguns lineups)
    if res["ETD"] == "-":
        m_ets = re.search(r"ETS\s+([A-Z]{{3}}\s+\d{{1,2}}(?:ST|ND|RD|TH)?(?:,?\s+\d{{4}})?|\d{{1,2}}[/|-]\d{{1,2}})", corpo_normalizado)
        if m_ets: res["ETD"] = m_ets.group(1).strip()

    return res

# --- MOTOR DE BUSCA ---

def buscar_dados():
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com", timeout=20)
        mail.login(EMAIL_USER, EMAIL_PASS)
        
        # 1. LISTA NAVIOS (Inbox)
        mail.select("INBOX", readonly=True)
        _, data_lista = mail.search(None, '(SUBJECT "LISTA NAVIOS")')
        if not data_lista[0]: return None, None, "E-mail 'LISTA NAVIOS' não encontrado."

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

        partes = re.split(r'BELEM:', corpo_lista, flags=re.IGNORECASE)
        slz_bruto = [l.strip() for l in partes[0].replace('SLZ:', '').split('\n') if l.strip() and not e_assinatura(l)]
        bel_bruto = []
        if len(partes) > 1:
            for l in partes[1].split('\n'):
                line = l.strip()
                if line and not e_assinatura(line): bel_bruto.append(line)
                elif line and e_assinatura(line) and len(bel_bruto) > 0: break

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
                        
                        corpo = ""
                        if m.is_multipart():
                            for p in m.walk():
                                if p.get_content_type() == "text/plain": 
                                    corpo = p.get_payload(decode=True).decode(errors="ignore")
                        else: 
                            corpo = m.get_payload(decode=True).decode(errors="ignore")
                        
                        prospects_list.append({
                            "subj": subj, 
                            "date": envio_br, 
                            "datas": extrair_datas_prospect(corpo)
                        })
                except: continue
        
        mail.logout()
        return slz_bruto, bel_bruto, prospects_list

    except Exception as e:
        return None, None, str(e)

# --- INTERFACE ---
st.set_page_config(page_title="Monitor Operacional WS", layout="wide")
st.title("🚢 Monitor Operacional - Wilson Sons")

if 'slz_tab' not in st.session_state: st.session_state.slz_tab = []
if 'bel_tab' not in st.session_state: st.session_state.bel_tab = []
if 'last_up' not in st.session_state: st.session_state.last_up = "-"

if st.button("🔄 ATUALIZAR DADOS", use_container_width=True, type="primary"):
    with st.spinner("Lendo e-mails e extraindo datas..."):
        slz, bel, prospects = buscar_dados()
        
        if isinstance(prospects, str):
            st.error(f"Erro: {prospects}")
        elif slz is not None:
            def montar(lista_navios, is_bel=False):
                res = []
                for navio_bruto in lista_navios:
                    n_limpo = limpar_nome(navio_bruto)
                    p_limpo = extrair_porto(navio_bruto)
                    
                    vessel_emails = [e for e in prospects if n_limpo in e["subj"]]
                    if is_bel and p_limpo:
                        vessel_emails = [e for e in vessel_emails if p_limpo in e["subj"]]
                    
                    vessel_emails.sort(key=lambda x: x["date"], reverse=True)
                    
                    # AM: até 13h | PM: após 13h
                    am_check = any(e["date"].hour < 13 for e in vessel_emails)
                    pm_check = any(e["date"].hour >= 13 for e in vessel_emails)
                    
                    info = vessel_emails[0]["datas"] if vessel_emails else {"ETA": "-", "ETB": "-", "ETD": "-"}
                    
                    res.append({
                        "Navio": f"{n_limpo} ({p_limpo})" if p_limpo else n_limpo,
                        "AM (até 13h)": "✅" if am_check else "❌",
                        "PM (pós 13h)": "✅" if pm_check else "❌",
                        "ETA": info["ETA"], 
                        "ETB": info["ETB"], 
                        "ETD": info["ETD"]
                    })
                return res

            st.session_state.slz_tab = montar(slz)
            st.session_state.bel_tab = montar(bel, True)
            st.session_state.last_up = datetime.now(BR_TZ).strftime("%H:%M:%S")

if st.session_state.slz_tab or st.session_state.bel_tab:
    st.write(f"Última atualização: **{st.session_state.last_up}**")
    t1, t2 = st.tabs(["📍 São Luís", "📍 Belém"])
    with t1: st.table(st.session_state.slz_tab)
    with t2: st.table(st.session_state.bel_tab)
else:
    st.info("Aguardando sincronização inicial.")

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
    texto = re.sub(r'<[^>]+>', ' ', html)
    return " ".join(texto.split())

def formatar_data_br(texto_data, data_referencia):
    if not texto_data or texto_data == "-": return "-"
    meses_en = {
        'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6,
        'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12
    }
    try:
        dia_match = re.search(r'(\d{1,2})', texto_data)
        mes_match = re.search(r'(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)', texto_data.upper())
        if dia_match and mes_match:
            dia = int(dia_match.group(1))
            mes = meses_en[mes_match.group(1)]
            ano = data_referencia.year
            # Double Check de segurança
            data_detectada = datetime(ano, mes, dia)
            if (data_referencia.replace(tzinfo=None) - data_detectada).days > 20:
                return None 
            return f"{dia:02d}/{mes:02d}/{ano}"
    except: pass
    return None

def extrair_datas_prospect(corpo, data_email):
    res = {"ETA": "-", "ETB": "-", "ETD": "-"}
    if not corpo: return res
    # Ignora o Lineup geral no fim do e-mail para não pegar data de outro navio
    corpo_focado = corpo.upper().split("LINEUP DETAILS")[0]
    
    # Busca ETB e ETD/ETS
    for k in ["ETB", "ETD", "ETS"]:
        padrao = rf"{k}\s+.*?([A-Z]{{3,}}\s+\d{{1,2}}(?:ST|ND|RD|TH)?)"
        matches = re.findall(padrao, corpo_focado)
        chave = "ETD" if k == "ETS" else k
        for m in matches:
            dt = formatar_data_br(m, data_email)
            if dt: 
                res[chave] = dt
                break

    # Hierarquia de Chegada
    gatilhos = ["ARRIVAL AT ROADS", "NOTICE OF READINESS", "NOR TENDERED", "ETA"]
    for g in gatilhos:
        padrao = rf"{g}\s+.*?([A-Z]{{3,}}\s+\d{{1,2}}(?:ST|ND|RD|TH)?)"
        matches = re.findall(padrao, corpo_focado)
        for m in matches:
            dt = formatar_data_br(m, data_email)
            if dt:
                res["ETA"] = dt
                break
        if res["ETA"] != "-": break
    return res

# --- MOTOR DE BUSCA ---

def buscar_dados():
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com", timeout=25)
        mail.login(EMAIL_USER, EMAIL_PASS)
        
        # 1. LISTA NAVIOS (Extração de SLZ e Belém)
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
                    p = part.get_payload(decode=True).decode(errors="ignore")
                    corpo_l = limpar_html(p) if part.get_content_type() == "text/html" else p
                    break
            
            # Divisão correta entre SLZ e Belém
            partes = re.split(r'BELEM:', corpo_l, flags=re.IGNORECASE)
            slz_bruto = [l.strip() for l in partes[0].replace('SLZ:', '').split('\n') if 3 < len(l.strip()) < 60]
            if len(partes) > 1:
                # Pega as linhas de Belém até o fim ou até uma assinatura
                bel_bruto = [l.strip() for l in partes[1].split('\n') if 3 < len(l.strip()) < 60]

        # 2. PROSPECTS
        mail.select(f'"{LABEL_PROSPECT}"', readonly=True)
        hoje_str = datetime.now(BR_TZ).strftime("%d-%b-%Y")
        _, data_p = mail.search(None, f'(SINCE "{hoje_str}")')
        prospects_list = []
        if data_p[0]:
            ids = data_p[0].split()[-60:] # Aumentado para 60 para garantir
            for eid in ids:
                try:
                    _, d = mail.fetch(eid, '(RFC822)')
                    m = email.message_from_bytes(d[0][1])
                    envio_br = email.utils.parsedate_to_datetime(m.get("Date")).astimezone(BR_TZ)
                    subj = "".join(str(c.decode(ch or 'utf-8') if isinstance(c, bytes) else c) for c, ch in decode_header(m.get("Subject", ""))).upper()
                    corpo_p = ""
                    for part in m.walk():
                        if part.get_content_type() == "text/html":
                            corpo_p = limpar_html(part.get_payload(decode=True).decode(errors="ignore"))
                            break
                        elif part.get_content_type() == "text/plain":
                            corpo_p = part.get_payload(decode=True).decode(errors="ignore")
                    prospects_list.append({"subj": subj, "date": envio_br, "datas": extrair_datas_prospect(corpo_p, envio_br)})
                except: continue
        mail.logout()
        return slz_bruto, bel_bruto, prospects_list
    except Exception as e: return None, None, str(e)

# --- UI ---
st.set_page_config(page_title="Monitor WS", layout="wide")
st.title("🚢 Monitor Operacional Wilson Sons")

if 'dados' not in st.session_state:
    st.session_state.dados = {"slz": [], "bel": [], "at": "-"}

if st.button("🔄 ATUALIZAR AGORA (SLZ + BELÉM)", use_container_width=True, type="primary"):
    with st.spinner("Sincronizando Portos..."):
        slz, bel, prospects = buscar_dados()
        if slz is not None:
            def montar(lista, porto_filtro=None):
                res = []
                for n_bruto in lista:
                    # Limpeza robusta do nome do navio
                    nome = re.sub(r'^(MV|M/V|MT|M/T)\s+', '', n_bruto.strip(), flags=re.IGNORECASE).split(' - ')[0].split(' (')[0].strip().upper()
                    
                    # Tenta capturar o porto entre parênteses para Belém (ex: Vila do Conde)
                    porto_msg = re.search(r'\((.*?)\)', n_bruto).group(1).strip().upper() if '(' in n_bruto else None
                    
                    # Busca e-mails que contenham o nome do navio no Assunto
                    match = [e for e in prospects if nome in e["subj"]]
                    
                    # Se for Belém e houver e-mails, tenta filtrar pelo porto para ser mais exato
                    if porto_filtro and porto_msg and len(match) > 1:
                        match_porto = [e for e in match if porto_msg in e["subj"]]
                        if match_porto: match = match_porto
                    
                    match.sort(key=lambda x: x["date"], reverse=True)
                    info = match[0]["datas"] if match else {"ETA": "-", "ETB": "-", "ETD": "-"}
                    
                    res.append({
                        "Navio": f"{nome} ({porto_msg})" if porto_msg else nome,
                        "AM": "✅" if any(e["date"].hour < 13 for e in match) else "❌",
                        "PM": "✅" if any(e["date"].hour >= 13 for e in match) else "❌",
                        "ETA/Arrival": info["ETA"], "ETB": info["ETB"], "ETD": info["ETD"]
                    })
                return res

            st.session_state.dados = {
                "slz": montar(slz),
                "bel": montar(bel, porto_filtro="BELEM"),
                "at": datetime.now(BR_TZ).strftime("%H:%M:%S")
            }

if st.session_state.dados["at"] != "-":
    st.write(f"Última atualização: **{st.session_state.dados['at']}**")
    t1, t2 = st.tabs(["📍 São Luís", "📍 Belém"])
    with t1: st.table(st.session_state.dados["slz"])
    with t2: st.table(st.session_state.dados["bel"])

import streamlit as st
import imaplib, email, re, smtplib, sqlite3
from email.header import decode_header
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta, timezone
import pytz

# 1. Configuração da Página
st.set_page_config(page_title="Monitor WS", layout="wide")
BR_TZ = pytz.timezone('America/Sao_Paulo')

# --- CONFIGURAÇÕES ---
EMAIL_USER = "leonardo.alves@wilsonsons.com.br"
EMAIL_PASS = "nlvr vmyv cbcq oexe"
DESTINATARIO = "leonardo.alves@wilsonsons.com.br"

REMETENTES_VALIDOS = ["operation.sluis", "operation.belem", "agencybrazil"]
TERMOS_PROSPECT = ["PROSPECT", "ARRIVAL", "NOR TENDERED", "BERTHING", "BERTH", "DAILY"]

# --- BANCO DE DADOS ---
def init_db():
    try:
        conn = sqlite3.connect('monitor_navios.db', check_same_thread=False)
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS navios 
                     (nome TEXT PRIMARY KEY, eta TEXT, etb TEXT, etd TEXT, clp TEXT, atualizacao TEXT)''')
        conn.commit()
        conn.close()
    except: pass

def ler_banco(nome_id):
    try:
        conn = sqlite3.connect('monitor_navios.db', check_same_thread=False)
        c = conn.cursor()
        c.execute("SELECT eta, etb, etd, clp FROM navios WHERE nome=?", (nome_id,))
        res = c.fetchone()
        conn.close()
        return res if res else ("-", "-", "-", "❌ PENDENTE")
    except: return ("-", "-", "-", "❌ PENDENTE")

def salvar_banco(nome_id, eta, etb, etd, clp):
    try:
        conn = sqlite3.connect('monitor_navios.db', check_same_thread=False)
        c = conn.cursor()
        ex = ler_banco(nome_id)
        eta_f = eta if (eta != "-" and eta is not None) else ex[0]
        etb_f = etb if (etb != "-" and etb is not None) else ex[1]
        etd_f = etd if (etd != "-" and etd is not None) else ex[2]
        c.execute("INSERT OR REPLACE INTO navios VALUES (?,?,?,?,?,?)", 
                  (nome_id, eta_f, etb_f, etd_f, clp, datetime.now(BR_TZ).strftime("%H:%M")))
        conn.commit()
        conn.close()
    except: pass

# --- FUNÇÕES DE APOIO OTIMIZADAS ---
def decodificar_texto(payload, encoding):
    if not payload: return ""
    try: return payload.decode(encoding or 'utf-8', errors='ignore')
    except: return str(payload)

def decodificar_assunto(subj):
    if not subj: return ""
    try:
        decoded = decode_header(subj)
        res = ""
        for part, enc in decoded:
            if isinstance(part, bytes): res += part.decode(enc or 'utf-8', errors='ignore')
            else: res += str(part)
        return res.upper()
    except: return str(subj).upper()

def extrair_datas_prospect(texto_puro, envio):
    res = {"ETA": "-", "ETB": "-", "ETD": "-"}
    if not texto_puro: return res
    txt = re.sub(r'\s+', ' ', texto_puro.upper())
    meses_map = {'JAN':1,'FEB':2,'MAR':3,'APR':4,'MAY':5,'JUN':6,'JUL':7,'AUG':8,'SEP':9,'OCT':10,'NOV':11,'DEC':12}
    hoje = datetime.now(BR_TZ).replace(hour=0, minute=0, second=0, microsecond=0)
    
    def parse_data(s):
        m_mes = re.search(r'(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)', s)
        m_dia = re.search(r'(\d{1,2})', s)
        if m_mes and m_dia:
            dia, mes = int(m_dia.group(1)), meses_map[m_mes.group(1)]
            dt_encontrada = datetime(envio.year, mes, dia, tzinfo=BR_TZ)
            if dt_encontrada < (hoje - timedelta(days=15)): return "-"
            return f"{dia:02d}/{mes:02d}/{envio.year}"
        return "-"

    termos_eta = [
        r"NOTICE OF READINESS\s*[:\-]?\s*([A-Z]{3,}\s+\d{1,2})",
        r"ARRIVAL AT ROADS\s*[:\-]?\s*([A-Z]{3,}\s+\d{1,2})",
        r"ETA AT MOSQUEIRO\s*[:\-]?\s*([A-Z]{3,}\s+\d{1,2})",
        r"ETA AT VILA\s*[:\-]?\s*([A-Z]{3,}\s+\d{1,2})",
        r"ETA\s*[:\-]?\s*([A-Z]{3,}\s+\d{1,2})"
    ]
    for t in termos_eta:
        m = re.search(t, txt)
        if m:
            val = parse_data(m.group(1)); res["ETA"] = val
            if val != "-": break

    for k in ["ETB", "ETD", "ETS"]:
        m = re.search(rf"{k}\s*[:\-]?\s*([A-Z]{{3,}}\s+\d{{1,2}})", txt)
        if m:
            dt = parse_data(m.group(1))
            if dt != "-": res["ETD" if k=="ETS" else k] = dt
    return res

# --- INTERFACE ---
st.title("🚢 Monitor Operacional Wilson Sons")
init_db()

if 'slz' not in st.session_state: st.session_state.slz = []
if 'bel' not in st.session_state: st.session_state.bel = []
if 'at' not in st.session_state: st.session_state.at = "-"

c1, c2 = st.columns(2)
with c1:
    if st.button("🔄 ATUALIZAR AGORA", use_container_width=True, type="primary"):
        try:
            with st.status("🚀 Otimizando leitura do Gmail...", expanded=True) as status:
                mail = imaplib.IMAP4_SSL("imap.gmail.com")
                mail.login(EMAIL_USER, EMAIL_PASS)
                agora = datetime.now(BR_TZ)
                
                # 1. LISTA NAVIOS (INBOX) - Otimizado
                mail.select("INBOX", readonly=True)
                _, d_l = mail.search(None, '(SUBJECT "LISTA NAVIOS")')
                slz_raw, bel_raw = [], []
                if d_l[0]:
                    # Baixa apenas o cabeçalho e o corpo de texto
                    _, d = mail.fetch(d_l[0].split()[-1], '(BODY.PEEK[TEXT])')
                    corpo_lista = decodificar_texto(d[0][1], 'utf-8')
                    linhas = [l.strip() for l in corpo_lista.split('\n') if len(l.strip()) > 1]
                    secao = None
                    for linha in linhas:
                        l_up = linha.upper()
                        if "SLZ" in l_up: secao = "SLZ"; continue
                        if "BELEM" in l_up: secao = "BEL"; continue
                        if secao == "SLZ" and len(linha) > 3: slz_raw.append(linha)
                        elif secao == "BEL" and len(linha) > 3: bel_raw.append(linha)

                # 2. PROSPECTS - Otimização Crítica (BODY.PEEK)
                mail.select("PROSPECT", readonly=True)
                # Busca apenas as últimas 24h para ser mais rápido
                _, d_p = mail.search(None, f'(SINCE "{agora.strftime("%d-%b-%Y")}")')
                prospy = []
                if d_p[0]:
                    for eid in d_p[0].split()[-100:]:
                        # Baixa apenas o Assunto, Data e o Texto do corpo (sem anexos)
                        _, d = mail.fetch(eid, '(BODY.PEEK[HEADER.FIELDS (Subject Date)] BODY.PEEK[TEXT])')
                        m_head = email.message_from_bytes(d[0][1])
                        subj = decodificar_assunto(m_head.get("Subject"))
                        if any(term in subj for term in TERMOS_PROSPECT):
                            envio = email.utils.parsedate_to_datetime(m_head.get("Date")).astimezone(BR_TZ)
                            # d[1][1] contém o corpo do e-mail solicitado no BODY.PEEK[TEXT]
                            corpo_txt = decodificar_texto(d[1][1], 'utf-8')
                            prospy.append({"subj": subj, "date": envio, "datas": extrair_datas_prospect(corpo_txt, envio)})

                # 3. CLP - Otimizado (Apenas Subject)
                mail.select("CLP", readonly=True)
                _, d_c = mail.search(None, "ALL")
                clps_list = []
                if d_c[0]:
                    for eid in d_c[0].split()[-50:]:
                        _, d = mail.fetch(eid, '(BODY.PEEK[HEADER.FIELDS (SUBJECT)])')
                        clps_list.append(decodificar_assunto(email.message_from_bytes(d[0][1]).get("Subject")))
                
                mail.logout()

                def processar(lista, is_bel=False):
                    res = []
                    for n in lista:
                        n_id = re.sub(r'^(MV|M/V|MT|M/T)\s+', '', n.upper()).split(' - ')[0].split(' (')[0].strip()
                        matches = [e for e in prospy if n_id in e["subj"]]
                        matches.sort(key=lambda x: x["date"], reverse=True)
                        p_datas = matches[0]["datas"] if matches else {"ETA":"-","ETB":"-","ETD":"-"}
                        db = ler_banco(n)
                        eta = p_datas["ETA"] if p_datas["ETA"] != "-" else db[0]
                        etb = p_datas["ETB"] if p_datas["ETB"] != "-" else db[1]
                        etd = p_datas["ETD"] if p_datas["ETD"] != "-" else db[2]
                        
                        tem_clp = any(n_id in s for s in clps_list)
                        if tem_clp: st_clp = "✅ EMITIDA"
                        elif eta != "-" and "/" in eta:
                            try:
                                d,m,a = eta.split("/")
                                data_eta = datetime(int(a),int(m),int(d), tzinfo=BR_TZ).replace(hour=0,minute=0,second=0)
                                if (data_eta - agora.replace(hour=0,minute=0,second=0)).days <= 4: st_clp = "⚠️ CRÍTICO"
                                else: st_clp = "❌ PENDENTE"
                            except: st_clp = "❌ PENDENTE"
                        else: st_clp = "❌ PENDENTE"
                        
                        salvar_banco(n, eta, etb, etd, st_clp)
                        res.append({"Navio": n_id if is_bel else n, "Prospect Manhã": "✅" if any(e["date"].hour < 13 and e["date"].date() == agora.date() for e in matches) else "❌", "Prospect Tarde": "✅" if any(e["date"].hour >= 13 and e["date"].date() == agora.date() for e in matches) else "❌", "ETA": eta, "ETB": etb, "ETD": etd, "CLP": st_clp})
                    return res

                st.session_state.slz = processar(slz_raw, False)
                st.session_state.bel = processar(bel_raw, True)
                st.session_state.at = agora.strftime("%H:%M")
                st.rerun()
        except Exception as e: st.error(f"Erro: {e}")

with c2:
    if st.button("📧 ENVIAR POR E-MAIL", use_container_width=True):
        # (Lógica de envio mantida aqui se necessário)
        pass

if st.session_state.at != "-":
    t1, t2 = st.tabs(["📍 São Luís", "📍 Belém"])
    with t1: st.table(st.session_state.slz)
    with t2: st.table(st.session_state.bel)

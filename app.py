import streamlit as st
import imaplib, email, re, smtplib, sqlite3
from email.header import decode_header
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
import pytz
import time

# 1. Configuração da Página
st.set_page_config(page_title="Monitor WS", layout="wide")
BR_TZ = pytz.timezone('America/Sao_Paulo')

# --- CONFIGURAÇÕES ---
EMAIL_USER = "leonardo.alves@wilsonsons.com.br"
EMAIL_PASS = "nlvr vmyv cbcq oexe"
DESTINATARIO = "leonardo.alves@wilsonsons.com.br"
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

# --- APOIO ---
def decodificar_texto(payload):
    if not payload: return ""
    return payload.decode(errors='ignore') if isinstance(payload, bytes) else str(payload)

def decodificar_assunto(m):
    subj = m.get("Subject", "")
    if not subj: return ""
    decoded = decode_header(subj)
    res = ""
    for part, enc in decoded:
        if isinstance(part, bytes): res += part.decode(enc or 'utf-8', errors='ignore')
        else: res += str(part)
    return res.upper().strip()

def limpar_visual_nome(n):
    n = n.upper()
    porto = re.search(r'(\(.*?\))', n)
    p_str = porto.group(1) if porto else ""
    limpo = re.sub(r'^(MV|M/V|MT|M/T)\s+', '', n)
    limpo = limpo.split(' - ')[0].split(' (')[0].strip()
    return f"{limpo} {p_str}".strip()

def extrair_datas_prospect(texto, envio):
    res = {"ETA": "-", "ETB": "-", "ETD": "-"}
    txt = " ".join(texto.upper().split())
    meses_map = {'JAN':1,'FEB':2,'MAR':3,'APR':4,'MAY':5,'JUN':6,'JUL':7,'AUG':8,'SEP':9,'OCT':10,'NOV':11,'DEC':12}
    
    def parse_data(s):
        m_mes = re.search(r'(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)', s)
        m_dia = re.search(r'(\d{1,2})', s)
        if m_mes and m_dia:
            return f"{int(m_dia.group(1)):02d}/{meses_map[m_mes.group(1)]:02d}/{envio.year}"
        return "-"

    m_eta = re.search(r"(NOTICE OF READINESS|ARRIVAL AT ROADS|ETA)\s*[:\-]?\s*([A-Z]{3,}\s+\d{1,2})", txt)
    if m_eta: res["ETA"] = parse_data(m_eta.group(2))
    for k in ["ETB", "ETD", "ETS"]:
        m = re.search(rf"{k}\s*[:\-]?\s*([A-Z]{{3,}}\s+\d{{1,2}})", txt)
        if m: res["ETD" if k=="ETS" else k] = parse_data(m.group(1))
    return res

def enviar_relatorio(dados_slz, dados_bel):
    try:
        msg = MIMEMultipart()
        msg['From'] = EMAIL_USER
        msg['To'] = DESTINATARIO
        msg['Subject'] = f"🚢 Monitor Operacional WS - {datetime.now(BR_TZ).strftime('%d/%m %H:%M')}"
        def gerar_html(titulo, lista):
            h = f"<h3 style='font-family:Arial; background:#f2f2f2; padding:8px;'>{titulo}</h3>"
            h += "<table border='1' style='border-collapse:collapse; width:100%; font-family:Arial; font-size:12px;'>"
            h += "<tr style='background:#004a99; color:white;'><th>Navio</th><th>Prospect Manhã</th><th>Prospect Tarde</th><th>ETA</th><th>ETB</th><th>ETD</th><th>CLP</th></tr>"
            for r in lista:
                c_am = "background:#d4edda;" if r["Prospect Manhã"] == "✅" else "background:#f8d7da;"
                c_pm = "background:#d4edda;" if r["Prospect Tarde"] == "✅" else "background:#f8d7da;"
                bg_clp = "#d4edda" if "EMITIDA" in r['CLP'] else ("#fff3cd" if "CRÍTICO" in r['CLP'] else "#f8d7da")
                h += f"<tr style='text-align:center;'><td>{r['Navio']}</td><td style='{c_am}'>{r['Prospect Manhã']}</td><td style='{c_pm}'>{r['Prospect Tarde']}</td><td>{r['ETA']}</td><td>{r['ETB']}</td><td>{r['ETD']}</td><td style='background:{bg_clp};'>{r['CLP']}</td></tr>"
            return h + "</table><br>"
        corpo = f"<html><body>{gerar_html('📍 São Luís', dados_slz)}{gerar_html('📍 Belém', dados_bel)}</body></html>"
        msg.attach(MIMEText(corpo, 'html'))
        s = smtplib.SMTP('smtp.gmail.com', 587); s.starttls(); s.login(EMAIL_USER, EMAIL_PASS); s.send_message(msg); s.quit()
        return True
    except: return False

# --- INTERFACE ---
st.title("🚢 Monitor Operacional Wilson Sons")
init_db()

if 'slz' not in st.session_state: st.session_state.slz, st.session_state.bel, st.session_state.at = [], [], "-"

c1, c2 = st.columns(2)
with c1:
    if st.button("🔄 ATUALIZAR AGORA", use_container_width=True, type="primary"):
        try:
            progresso = st.progress(0)
            status_txt = st.empty()
            
            with st.status("Sincronizando...", expanded=True) as status:
                mail = imaplib.IMAP4_SSL("imap.gmail.com")
                mail.login(EMAIL_USER, EMAIL_PASS)
                agora = datetime.now(BR_TZ)
                hoje_br = agora.date()
                
                # 1. LISTA NAVIOS
                status_txt.info("Buscando Lista de Navios...")
                mail.select("INBOX", readonly=True)
                _, d_l = mail.search(None, '(SUBJECT "LISTA NAVIOS")')
                slz_raw, bel_raw = [], []
                if d_l[0]:
                    _, d = mail.fetch(d_l[0].split()[-1], '(BODY.PEEK[TEXT])')
                    corpo = decodificar_texto(d[0][1])
                    secao = None
                    for linha in corpo.split('\n'):
                        l = linha.strip().upper()
                        if "SLZ" in l: secao = "SLZ"; continue
                        if "BELEM" in l: secao = "BEL"; continue
                        if secao and len(linha.strip()) > 3:
                            if secao == "SLZ": slz_raw.append(linha.strip())
                            else: bel_raw.append(linha.strip())
                progresso.progress(20)

                # 2. PROSPECTS (DEDUPLICAÇÃO POR ASSUNTO)
                status_txt.info("Lendo Prospects (Deduplicando e-mails)...")
                mail.select("PROSPECT", readonly=True)
                _, d_p = mail.search(None, "ALL")
                prospy = []
                assuntos_vistos = set() # Trava para duplicados

                if d_p[0]:
                    lista_ids = d_p[0].split()[-50:] # Pegamos 80 mas filtramos duplicados
                    total = len(lista_ids)
                    for i, eid in enumerate(reversed(lista_ids)): # Lê do mais novo para o mais antigo
                        progresso.progress(20 + int((i/total)*50))
                        
                        # Primeiro pega só o HEADER para checar o assunto
                        _, h_data = mail.fetch(eid, '(BODY.PEEK[HEADER.FIELDS (Subject Date)])')
                        msg_h = email.message_from_bytes(h_data[0][1])
                        subj = decodificar_assunto(msg_h)
                        envio = email.utils.parsedate_to_datetime(msg_h.get("Date")).astimezone(BR_TZ)
                        
                        # CHAVE DE DEDUPLICAÇÃO: (Assunto + Dia)
                        chave = f"{subj}_{envio.date()}"
                        
                        if chave in assuntos_vistos:
                            continue # Já processou esse e-mail hoje, pula!
                        
                        if any(term in subj for term in TERMOS_PROSPECT) and envio.date() >= (hoje_br - timedelta(days=1)):
                            # Só agora baixa o corpo do texto (Ganha muita velocidade)
                            _, b_data = mail.fetch(eid, '(BODY.PEEK[TEXT])')
                            body = decodificar_texto(b_data[0][1])
                            prospy.append({"subj": subj, "date": envio, "datas": extrair_datas_prospect(body, envio)})
                            assuntos_vistos.add(chave)
                            
                        if len(assuntos_vistos) > 40: break # Limite de 40 e-mails ÚNICOS

                progresso.progress(70)

                # 3. CLP
                status_txt.info("Verificando Marcador CLP...")
                mail.select("CLP", readonly=True)
                _, d_c = mail.search(None, "ALL")
                clps_hoje = []
                if d_c[0]:
                    lista_ids_c = d_c[0].split()[-40:]
                    for e in lista_ids_c:
                        _, d = mail.fetch(e, '(BODY.PEEK[HEADER.FIELDS (Subject)])')
                        clps_hoje.append(decodificar_assunto(email.message_from_bytes(d[0][1])))
                
                mail.logout()
                progresso.progress(90)

                # 4. PROCESSAMENTO
                def processar(lista, belem=False):
                    res = []
                    for n in lista:
                        n_id = re.sub(r'^(MV|M/V|MT|M/T)\s+', '', n.upper()).split(' - ')[0].strip()
                        matches = sorted([e for e in prospy if n_id in e["subj"]], key=lambda x: x["date"], reverse=True)
                        p_datas = matches[0]["datas"] if matches else {"ETA":"-","ETB":"-","ETD":"-"}
                        db = ler_banco(n)
                        eta = p_datas["ETA"] if p_datas["ETA"] != "-" else db[0]
                        etb = p_datas["ETB"] if p_datas["ETB"] != "-" else db[1]
                        etd = p_datas["ETD"] if p_datas["ETD"] != "-" else db[2]
                        st_clp = "✅ EMITIDA" if any(n_id in s for s in clps_hoje) else db[3]
                        if st_clp != "✅ EMITIDA" and eta != "-" and "/" in eta:
                            try:
                                d,m,a = eta.split("/"); diff = (datetime(int(a),int(m),int(d)).date() - hoje_br).days
                                if diff <= 4: st_clp = "⚠️ CRÍTICO"
                            except: pass
                        salvar_banco(n, eta, etb, etd, st_clp)
                        res.append({"Navio": n_id if belem else n, "Prospect Manhã": "✅" if any(e["date"].hour < 13 and e["date"].date() == hoje_br for e in matches) else "❌", "Prospect Tarde": "✅" if any(e["date"].hour >= 13 and e["date"].date() == hoje_br for e in matches) else "❌", "ETA": eta, "ETB": etb, "ETD": etd, "CLP": st_clp})
                    return res

                st.session_state.slz = processar(slz_raw, False)
                st.session_state.bel = processar(bel_raw, True)
                st.session_state.at = agora.strftime("%H:%M")
                progresso.progress(100)
                st.rerun()
        except Exception as e: st.error(f"Erro: {e}")

# (Restante do código de exibição igual)
if st.session_state.at != "-":
    st.write(f"⏱️ Última atualização: {st.session_state.at}")
    t1, t2 = st.tabs(["📍 São Luís", "📍 Belém"])
    with t1: st.table(st.session_state.slz)
    with t2: st.table(st.session_state.bel)

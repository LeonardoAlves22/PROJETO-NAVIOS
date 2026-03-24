import streamlit as st
import imaplib, email, re, smtplib, sqlite3
from email.header import decode_header
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import pytz

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

# --- FUNÇÕES DE APOIO ---
def decodificar_texto_limpo(payload):
    if not payload: return ""
    txt = payload.decode(errors='ignore') if isinstance(payload, bytes) else str(payload)
    txt = re.sub(r'<(br|div|p|/tr|tr)[^>]*>', '\n', txt, flags=re.IGNORECASE)
    txt = re.sub(r'<[^>]+>', '', txt)
    return txt

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
    txt = " ".join(texto_puro.upper().split())
    meses_map = {'JAN':1,'FEB':2,'MAR':3,'APR':4,'MAY':5,'JUN':6,'JUL':7,'AUG':8,'SEP':9,'OCT':10,'NOV':11,'DEC':12}
    def parse_data(s):
        m_mes = re.search(r'(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)', s)
        m_dia = re.search(r'(\d{1,2})', s)
        if m_mes and m_dia:
            return f"{int(m_dia.group(1)):02d}/{meses_map[m_mes.group(1)]:02d}/{envio.year}"
        return "-"
    for k in ["ETA", "ETB", "ETD"]:
        m = re.search(rf"{k}\s*[:\-]?\s*([A-Z]{{3,}}\s+\d{{1,2}})", txt)
        if m: res[k] = parse_data(m.group(1))
    return res

def enviar_relatorio(dados_slz, dados_bel):
    try:
        msg = MIMEMultipart()
        msg['From'] = EMAIL_USER
        msg['To'] = DESTINATARIO
        msg['Subject'] = f"🚢 Relatório Monitor WS - {datetime.now(BR_TZ).strftime('%d/%m %H:%M')}"
        
        def gerar_tabela(titulo, lista):
            html = f"<h3>{titulo}</h3><table border='1' style='border-collapse:collapse; width:100%; font-family:Arial;'>"
            html += "<tr style='background:#eee;'><th>Navio</th><th>Manhã</th><th>Tarde</th><th>ETA</th><th>ETB</th><th>ETD</th><th>CLP</th></tr>"
            for r in lista:
                html += f"<tr><td>{r['Navio']}</td><td align='center'>{r['Prospect Manhã']}</td><td align='center'>{r['Prospect Tarde']}</td><td>{r['ETA']}</td><td>{r['ETB']}</td><td>{r['ETD']}</td><td>{r['CLP']}</td></tr>"
            return html + "</table>"
            
        corpo = f"<html><body>{gerar_tabela('São Luís', dados_slz)}{gerar_tabela('Belém', dados_bel)}</body></html>"
        msg.attach(MIMEText(corpo, 'html'))
        with smtplib.SMTP('smtp.gmail.com', 587) as s:
            s.starttls(); s.login(EMAIL_USER, EMAIL_PASS); s.send_message(msg)
        return True
    except: return False

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
            with st.status("🔍 Buscando Marcadores...", expanded=True):
                mail = imaplib.IMAP4_SSL("imap.gmail.com")
                mail.login(EMAIL_USER, EMAIL_PASS)
                hoje_br = datetime.now(BR_TZ).date()

                # 1. LISTA NAVIOS (INBOX)
                mail.select("INBOX", readonly=True)
                _, msg_count = mail.select("INBOX", readonly=True)
                total = int(msg_count[0])
                slz_raw, bel_raw = [], []
                # Busca nas últimas 15 mensagens da Caixa de Entrada
                for i in range(total, max(0, total-15), -1):
                    _, d = mail.fetch(str(i), '(BODY.PEEK[HEADER.FIELDS (Subject Date)] BODY.PEEK[TEXT])')
                    msg_h = email.message_from_bytes(d[0][1])
                    if "LISTA NAVIOS" in decodificar_assunto(msg_h.get("Subject")):
                        corpo = decodificar_texto_limpo(d[1][1])
                        secao, vistos = None, set()
                        for linha in corpo.split('\n'):
                            l = linha.strip()
                            if "SLZ" in l.upper(): secao = "SLZ"; continue
                            if "BELEM" in l.upper(): secao = "BEL"; continue
                            if secao and len(l) > 3 and l.upper() not in vistos:
                                if secao == "SLZ": slz_raw.append(l)
                                else: bel_raw.append(l)
                                vistos.add(l.upper())
                        break

                # 2. PROSPECTS (DIRETO NO MARCADOR PROSPECT)
                prospy = []
                status_p, count_p = mail.select("PROSPECT", readonly=True)
                if status_p == 'OK':
                    total_p = int(count_p[0])
                    # Verifica os últimos 50 e-mails do marcador
                    for i in range(total_p, max(0, total_p-50), -1):
                        _, d = mail.fetch(str(i), '(BODY.PEEK[HEADER.FIELDS (Subject Date)] BODY.PEEK[TEXT])')
                        msg_h = email.message_from_bytes(d[0][1])
                        data_envio = email.utils.parsedate_to_datetime(msg_h.get("Date")).astimezone(BR_TZ)
                        if data_envio.date() == hoje_br:
                            subj = decodificar_assunto(msg_h.get("Subject"))
                            if any(t in subj for t in TERMOS_PROSPECT):
                                corpo_txt = d[1][1].decode(errors='ignore') if len(d)>1 else ""
                                prospy.append({"subj": subj, "date": data_envio, "datas": extrair_datas_prospect(corpo_txt, data_envio)})

                # 3. CLP (DIRETO NO MARCADOR CLP)
                clps_hoje = []
                status_c, count_c = mail.select("CLP", readonly=True)
                if status_c == 'OK':
                    total_c = int(count_c[0])
                    for i in range(total_c, max(0, total_c-30), -1):
                        _, d = mail.fetch(str(i), '(BODY.PEEK[HEADER.FIELDS (Subject Date)])')
                        msg_h = email.message_from_bytes(d[0][1])
                        data_envio = email.utils.parsedate_to_datetime(msg_h.get("Date")).astimezone(BR_TZ).date()
                        if data_envio == hoje_br:
                            clps_hoje.append(decodificar_assunto(msg_h.get("Subject")))

                mail.logout()

                def processar(lista, belem=False):
                    res = []
                    for n in lista:
                        n_id = re.sub(r'^(MV|M/V|MT|M/T)\s+', '', n.upper()).split(' - ')[0].strip()
                        matches = [e for e in prospy if n_id in e["subj"]]
                        matches.sort(key=lambda x: x["date"], reverse=True)
                        p_datas = matches[0]["datas"] if matches else {"ETA":"-","ETB":"-","ETD":"-"}
                        db = ler_banco(n)
                        eta, etb, etd = p_datas["ETA"], p_datas["ETB"], p_datas["ETD"]
                        st_clp = "✅ EMITIDA" if any(n_id in c for c in clps_hoje) else db[3]
                        
                        salvar_banco(n, eta, etb, etd, st_clp)
                        res.append({
                            "Navio": n_id if belem else n,
                            "Prospect Manhã": "✅" if any(e["date"].hour < 13 for e in matches) else "❌",
                            "Prospect Tarde": "✅" if any(e["date"].hour >= 13 for e in matches) else "❌",
                            "ETA": eta if eta != "-" else db[0], 
                            "ETB": etb if etb != "-" else db[1], 
                            "ETD": etd if etd != "-" else db[2], 
                            "CLP": st_clp
                        })
                    return res

                st.session_state.slz = processar(slz_raw, False)
                st.session_state.bel = processar(bel_raw, True)
                st.session_state.at = datetime.now(BR_TZ).strftime("%H:%M")
                st.rerun()
        except Exception as e: st.error(f"Erro: {e}")

with c2:
    if st.button("📧 ENVIAR RELATÓRIO", use_container_width=True):
        if st.session_state.slz:
            if enviar_relatorio(st.session_state.slz, st.session_state.bel):
                st.success("E-mail enviado para Leonardo!")
            else: st.error("Erro ao enviar e-mail.")
        else: st.warning("Primeiro clique em 'Atualizar Agora'.")

if st.session_state.at != "-":
    st.write(f"⏱️ Atualizado em: {st.session_state.at}")
    t1, t2 = st.tabs(["📍 São Luís", "📍 Belém"])
    with t1: st.table(st.session_state.slz)
    with t2: st.table(st.session_state.bel)

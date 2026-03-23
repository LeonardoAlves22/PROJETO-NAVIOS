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

# Remetentes permitidos para Prospect
REMETENTES_VALIDOS = ["operation.sluis", "operation.belem", "agencybrazil"]

# Palavras-chave de assunto para Prospect
ASSUNTOS_PROSPECT = [
    "ARRIVAL NOTICE", "NOR TENDERED", "BERTHING PROSPECTS", 
    "BERTHING PROSPECT", "BERTH NOTICE", "DAILY REPORT", "DAILY NOTICE"
]

def init_db():
    try:
        conn = sqlite3.connect('monitor_navios.db', check_same_thread=False)
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS navios 
                     (nome TEXT PRIMARY KEY, eta TEXT, etb TEXT, etd TEXT, clp TEXT, atualizacao TEXT)''')
        try: c.execute("ALTER TABLE navios ADD COLUMN clp TEXT")
        except: pass
        conn.commit()
        conn.close()
    except: pass

def ler_banco(nome):
    try:
        conn = sqlite3.connect('monitor_navios.db', check_same_thread=False)
        c = conn.cursor()
        c.execute("SELECT eta, etb, etd, clp FROM navios WHERE nome=?", (nome,))
        res = c.fetchone()
        conn.close()
        return res if res else ("-", "-", "-", "❌ PENDENTE")
    except: return ("-", "-", "-", "❌ PENDENTE")

def salvar_banco(nome, eta, etb, etd, clp):
    try:
        conn = sqlite3.connect('monitor_navios.db', check_same_thread=False)
        c = conn.cursor()
        ex = ler_banco(nome)
        eta_f = eta if eta != "-" else ex[0]
        etb_f = etb if etb != "-" else ex[1]
        etd_f = etd if etd != "-" else ex[2]
        c.execute("INSERT OR REPLACE INTO navios VALUES (?,?,?,?,?,?)", 
                  (nome, eta_f, etb_f, etd_f, clp, datetime.now(BR_TZ).strftime("%H:%M")))
        conn.commit()
        conn.close()
    except: pass

# --- FUNÇÕES DE APOIO ---
def decodificar_cabecalho(msg, campo):
    try:
        val = msg.get(campo)
        if val is None: return ""
        partes = decode_header(val)
        res = ""
        for t, c in partes:
            if isinstance(t, bytes): res += t.decode(c or 'utf-8', errors='ignore')
            else: res += str(t)
        return res.upper().strip()
    except: return str(msg.get(campo) or "").upper().strip()

def extrair_corpo_email(msg):
    corpo = ""
    try:
        if msg.is_multipart():
            for parte in msg.walk():
                if parte.get_content_type() == 'text/plain':
                    corpo = parte.get_payload(decode=True).decode(errors='ignore')
                    break
        else:
            corpo = msg.get_payload(decode=True).decode(errors='ignore')
    except: pass
    return corpo

def formatar_data_br(texto, ref):
    if not texto or texto == "-": return "-"
    meses = {'JAN':1,'FEB':2,'MAR':3,'APR':4,'MAY':5,'JUN':6,'JUL':7,'AUG':8,'SEP':9,'OCT':10,'NOV':11,'DEC':12}
    try:
        d = re.search(r'(\d{1,2})', texto)
        m = re.search(r'(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)', texto.upper())
        if d and m:
            return f"{int(d.group(1)):02d}/{meses[m.group(1)]:02d}/{ref.year}"
    except: pass
    return "-"

def extrair_datas_prospect(corpo, envio):
    res = {"ETA": "-", "ETB": "-", "ETD": "-"}
    if not corpo: return res
    txt = re.sub(r'<[^>]+>', ' ', corpo.upper().split("LINEUP DETAILS")[0])
    for k in ["ETB", "ETD", "ETS"]:
        m = re.search(rf"{k}\s+.*?([A-Z]{{3,}}\s+\d{{1,2}})", txt)
        if m:
            dt = formatar_data_br(m.group(1).strip(), envio)
            if dt != "-": res["ETD" if k=="ETS" else k] = dt
    for g in ["ARRIVAL AT ROADS", "NOTICE OF READINESS", "ETA"]:
        m = re.search(rf"{g}\s+.*?([A-Z]{{3,}}\s+\d{{1,2}})", txt)
        if m:
            dt = formatar_data_br(m.group(1).strip(), envio)
            if dt != "-": res["ETA"] = dt; break
    return res

# --- RELATÓRIO E-MAIL ---
def enviar_relatorio(dados_slz, dados_bel):
    try:
        msg = MIMEMultipart()
        msg['From'] = EMAIL_USER
        msg['To'] = DESTINATARIO
        msg['Subject'] = f"🚢 Monitor Operacional WS - {datetime.now(BR_TZ).strftime('%d/%m %H:%M')}"
        def gerar_html(titulo, lista):
            h = f"<h3 style='font-family:Arial; background:#f2f2f2; padding:8px;'>{titulo}</h3><table border='1' style='border-collapse:collapse; width:100%; font-family:Arial; font-size:12px;'>"
            h += "<tr style='background:#004a99; color:white;'><th>Navio</th><th>Prospect Manhã</th><th>Prospect Tarde</th><th>ETA</th><th>ETB</th><th>ETD</th><th>CLP</th></tr>"
            for r in lista:
                c_am = "background:#d4edda;" if r["Prospect Manhã"] == "✅" else "background:#f8d7da;"
                c_pm = "background:#d4edda;" if r["Prospect Tarde"] == "✅" else "background:#f8d7da;"
                bg = "#d4edda;" if "EMITIDA" in r['CLP'] else ("#fff3cd;" if "CRÍTICO" in r['CLP'] else "#f8d7da;")
                h += f"<tr style='text-align:center;'><td>{r['Navio']}</td><td style='{c_am}'>{r['Prospect Manhã']}</td><td style='{c_pm}'>{r['Prospect Tarde']}</td><td>{r['ETA']}</td><td>{r['ETB']}</td><td>{r['ETD']}</td><td style='background:{bg}'>{r['CLP']}</td></tr>"
            return h + "</table><br>"
        corpo = f"<html><body>{gerar_html('📍 São Luís', dados_slz)}{gerar_html('📍 Belém', dados_bel)}</body></html>"
        msg.attach(MIMEText(corpo, 'html'))
        s = smtplib.SMTP('smtp.gmail.com', 587); s.starttls(); s.login(EMAIL_USER, EMAIL_PASS); s.send_message(msg); s.quit()
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
            with st.status("Sincronizando...", expanded=True) as status:
                mail = imaplib.IMAP4_SSL("imap.gmail.com")
                mail.login(EMAIL_USER, EMAIL_PASS)
                agora = datetime.now(BR_TZ)

                # 1. LISTA NAVIOS
                mail.select("INBOX", readonly=True)
                _, d_l = mail.search(None, '(SUBJECT "LISTA NAVIOS")')
                slz_raw, bel_raw = [], []
                if d_l[0]:
                    _, d = mail.fetch(d_l[0].split()[-1], '(RFC822)')
                    conteudo = extrair_corpo_email(email.message_from_bytes(d[0][1]))
                    pts = re.split(r'BELEM:', conteudo, flags=re.IGNORECASE)
                    slz_raw = [l.strip() for l in pts[0].replace('SLZ:', '').split('\n') if len(l.strip()) > 5]
                    if len(pts) > 1: bel_raw = [l.strip() for l in pts[1].split('\n') if len(l.strip()) > 5]

                # 2. PROSPECTS (Busca e-mails dos últimos 2 dias)
                mail.select("PROSPECT", readonly=True)
                _, d_p = mail.search(None, f'(SINCE "{(agora - timedelta(days=1)).strftime("%d-%b-%Y")}")')
                prospy = []
                if d_p[0]:
                    for eid in d_p[0].split()[-60:]:
                        _, d = mail.fetch(eid, '(RFC822)')
                        m = email.message_from_bytes(d[0][1])
                        assunto = decodificar_cabecalho(m, "Subject")
                        remetente = decodificar_cabecalho(m, "From").lower()
                        envio = email.utils.parsedate_to_datetime(m.get("Date")).astimezone(BR_TZ)
                        
                        # Verifica se o e-mail é de um remetente oficial e se o assunto é um dos tipos de Prospect
                        is_valid_sender = any(ref in remetente for ref in REMETENTES_VALIDOS)
                        is_valid_subject = any(term in assunto for term in ASSUNTOS_PROSPECT)
                        
                        if is_valid_sender and is_valid_subject:
                            prospy.append({"subj": assunto, "date": envio, "datas": extrair_datas_prospect(extrair_corpo_email(m), envio)})

                # 3. CLP
                mail.select("CLP", readonly=True)
                _, d_c = mail.search(None, "ALL")
                clps_l = [decodificar_cabecalho(email.message_from_bytes(mail.fetch(e, '(BODY[HEADER.FIELDS (SUBJECT)])')[1][0][1]), "Subject") for e in d_c[0].split()[-50:]] if d_c[0] else []
                
                mail.logout()

                def processar(lista):
                    final = []
                    for n in lista:
                        nm_l = re.sub(r'^(MV|M/V|MT|M/T)\s+', '', n.strip(), flags=re.IGNORECASE).split(' - ')[0].split(' (')[0].strip().upper()
                        all_matches = [e for e in prospy if nm_l in e["subj"]]
                        all_matches.sort(key=lambda x: x["date"], reverse=True)
                        
                        p_datas = all_matches[0]["datas"] if all_matches else {"ETA":"-","ETB":"-","ETD":"-"}
                        db = ler_banco(nm_l)
                        
                        eta = p_datas["ETA"] if p_datas["ETA"] != "-" else db[0]
                        etb = p_datas["ETB"] if p_datas["ETB"] != "-" else db[1]
                        etd = p_datas["ETD"] if p_datas["ETD"] != "-" else db[2]
                        
                        tem_clp = any(nm_l in s for s in clps_l)
                        st_clp = "✅ EMITIDA" if tem_clp else "❌ PENDENTE"
                        if not tem_clp and eta != "-" and "/" in eta:
                            try:
                                d,m,a = eta.split("/"); d_eta = datetime(int(a),int(m),int(d), tzinfo=BR_TZ)
                                if (d_eta - agora).days <= 4: st_clp = "⚠️ CRÍTICO"
                            except: pass
                        
                        salvar_banco(nm_l, eta, etb, etd, st_clp)
                        # ✅ apenas para e-mails de HOJE
                        today_matches = [e for e in all_matches if e["date"].date() == agora.date()]
                        final.append({"Navio": n, "Prospect Manhã": "✅" if any(e["date"].hour < 13 for e in today_matches) else "❌", "Prospect Tarde": "✅" if any(e["date"].hour >= 13 for e in today_matches) else "❌", "ETA": eta, "ETB": etb, "ETD": etd, "CLP": st_clp})
                    return final

                st.session_state.slz = processar(slz_raw); st.session_state.bel = processar(bel_raw); st.session_state.at = agora.strftime("%H:%M"); st.rerun()
        except Exception as e: st.error(f"Erro: {e}")

with c2:
    if st.button("📧 ENVIAR POR E-MAIL", use_container_width=True):
        if st.session_state.slz and enviar_relatorio(st.session_state.slz, st.session_state.bel):
            st.success("E-mail enviado!")

if st.session_state.at != "-":
    st.write(f"Sincronizado em: **{st.session_state.at}**")
    t1, t2 = st.tabs(["📍 São Luís", "📍 Belém"])
    with t1: st.table(st.session_state.slz)
    with t2: st.table(st.session_state.bel)

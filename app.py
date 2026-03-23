import streamlit as st
import imaplib, email, re, smtplib, sqlite3
from email.header import decode_header
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta, timezone

st.set_page_config(page_title="Monitor WS", layout="wide")

# --- CONFIGURAÇÕES ---
EMAIL_USER = "leonardo.alves@wilsonsons.com.br"
EMAIL_PASS = "nlvr vmyv cbcq oexe"
DESTINATARIO = "leonardo.alves@wilsonsons.com.br"

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
        e_f = eta if eta != "-" else ex[0]
        b_f = etb if etb != "-" else ex[1]
        d_f = etd if etd != "-" else ex[2]
        c.execute("INSERT OR REPLACE INTO navios VALUES (?,?,?,?,?,?)", 
                  (nome, e_f, b_f, d_f, clp, datetime.now(timezone(timedelta(hours=-3))).strftime("%H:%M")))
        conn.commit()
        conn.close()
    except: pass

# --- FUNÇÃO DE DECODIFICAÇÃO ULTRA-SEGURA ---
def get_subject_safe(msg):
    try:
        subject = msg.get("Subject")
        if subject is None: return "SEM ASSUNTO"
        decoded = decode_header(subject)
        parts = []
        for content, codec in decoded:
            if isinstance(content, bytes):
                parts.append(content.decode(codec or 'utf-8', errors='ignore'))
            else:
                parts.append(str(content))
        return "".join(parts).upper()
    except:
        return str(msg.get("Subject") or "ERRO NA LEITURA").upper()

# --- RELATÓRIO E-MAIL ---
def enviar_relatorio(dados_slz, dados_bel):
    try:
        msg = MIMEMultipart()
        msg['From'] = EMAIL_USER
        msg['To'] = DESTINATARIO
        msg['Subject'] = f"🚢 Monitor Operacional WS - {datetime.now(timezone(timedelta(hours=-3))).strftime('%d/%m %H:%M')}"
        def gerar_html(titulo, lista):
            h = f"<h3 style='font-family:Arial;'>{titulo}</h3><table border='1' style='border-collapse:collapse;width:100%;font-family:Arial;font-size:12px;'>"
            h += "<tr style='background:#004a99;color:white;'><th>Navio</th><th>Manhã</th><th>Tarde</th><th>ETA</th><th>CLP</th></tr>"
            for r in lista:
                bg = "#d4edda" if "EMITIDA" in r['CLP'] else ("#fff3cd" if "CRÍTICO" in r['CLP'] else "#f8d7da")
                h += f"<tr><td>{r['Navio']}</td><td>{r['Prospect Manhã']}</td><td>{r['Prospect Tarde']}</td><td>{r['ETA']}</td><td style='background:{bg}'>{r['CLP']}</td></tr>"
            return h + "</table><br>"
        corpo = f"<html><body>{gerar_html('📍 São Luís', dados_slz)}{gerar_html('📍 Belém', dados_bel)}</body></html>"
        msg.attach(MIMEText(corpo, 'html'))
        s = smtplib.SMTP('smtp.gmail.com', 587); s.starttls(); s.login(EMAIL_USER, EMAIL_PASS); s.send_message(msg); s.quit()
        return True
    except Exception as e: st.error(f"Erro e-mail: {e}"); return False

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
                agora = datetime.now(timezone(timedelta(hours=-3)))

                # 1. LISTA
                mail.select("INBOX", readonly=True)
                _, d_l = mail.search(None, '(SUBJECT "LISTA NAVIOS")')
                slz_r, bel_r = [], []
                if d_l[0]:
                    _, d = mail.fetch(d_l[0].split()[-1], '(RFC822)')
                    raw = email.message_from_bytes(d[0][1]).get_payload(decode=True).decode(errors='ignore')
                    pts = re.split(r'BELEM:', raw, flags=re.IGNORECASE)
                    slz_r = [l.strip() for l in pts[0].replace('SLZ:', '').split('\n') if 3 < len(l.strip()) < 60]
                    bel_r = [l.strip() for l in pts[1].split('\n') if 3 < len(l.strip()) < 60] if len(pts)>1 else []

                # 2. PROSPECTS E CLP
                mail.select("PROSPECT", readonly=True)
                _, d_p = mail.search(None, f'(SINCE "{agora.strftime("%d-%b-%Y")}")')
                prospy = []
                if d_p[0]:
                    for eid in d_p[0].split()[-40:]:
                        _, d = mail.fetch(eid, '(RFC822)')
                        m = email.message_from_bytes(d[0][1])
                        prospy.append({"subj": get_subject_safe(m), "date": email.utils.parsedate_to_datetime(m.get("Date")).astimezone(timezone(timedelta(hours=-3)))})

                mail.select("CLP", readonly=True)
                _, d_c = mail.search(None, "ALL")
                clps_list = []
                if d_c[0]:
                    for eid in d_c[0].split()[-50:]:
                        _, d = mail.fetch(eid, '(BODY[HEADER.FIELDS (SUBJECT)])')
                        clps_list.append(get_subject_safe(email.message_from_bytes(d[0][1])))
                
                mail.logout()

                def processar(lista):
                    final = []
                    for n in lista:
                        nm = re.sub(r'^(MV|M/V|MT|M/T)\s+', '', n.strip(), flags=re.IGNORECASE).split(' - ')[0].split(' (')[0].strip().upper()
                        match = [e for e in prospy if nm in e["subj"]]
                        db = ler_banco(nm)
                        tem_clp = any(nm in s for s in clps_list)
                        st_clp = "✅ EMITIDA" if tem_clp else "❌ PENDENTE"
                        
                        # Lógica Crítico (4 dias)
                        if not tem_clp and db[0] != "-" and "/" in db[0]:
                            try:
                                d,m,a = db[0].split("/"); d_eta = datetime(int(a),int(m),int(d), tzinfo=timezone(timedelta(hours=-3)))
                                if (d_eta - agora).days <= 4: st_clp = "⚠️ CRÍTICO"
                            except: pass
                        
                        salvar_banco(nm, "-", "-", "-", st_clp)
                        final.append({"Navio": n, "Prospect Manhã": "✅" if any(e["date"].hour < 13 for e in match) else "❌", "Prospect Tarde": "✅" if any(e["date"].hour >= 13 for e in match) else "❌", "ETA": db[0], "CLP": st_clp})
                    return final

                st.session_state.slz = processar(slz_r); st.session_state.bel = processar(bel_r); st.session_state.at = agora.strftime("%H:%M"); st.rerun()
        except Exception as e: st.error(f"Erro: {e}")

with c2:
    if st.button("📧 ENVIAR POR E-MAIL", use_container_width=True):
        if st.session_state.slz and enviar_relatorio(st.session_state.slz, st.session_state.bel):
            st.success("E-mail enviado!")

if st.session_state.at != "-":
    t1, t2 = st.tabs(["📍 São Luís", "📍 Belém"])
    with t1: st.table(st.session_state.slz)
    with t2: st.table(st.session_state.bel)

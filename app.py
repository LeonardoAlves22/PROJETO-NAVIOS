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

def decodificar_cabecalho(msg, campo):
    try:
        val = msg.get(campo)
        if val is None: return ""
        partes = decode_header(val)
        res = ""
        for t, c in partes:
            if isinstance(t, bytes): res += t.decode(c or 'utf-8', errors='ignore')
            else: res += str(t)
        return res.upper()
    except: return str(msg.get(campo) or "").upper()

# --- NOVA FUNÇÃO PARA LER O CORPO DO E-MAIL (CORRIGE O "EM BRANCO") ---
def extrair_corpo_email(msg):
    corpo = ""
    if msg.is_multipart():
        for parte in msg.walk():
            tipo = parte.get_content_type()
            dispo = str(parte.get('Content-Disposition'))
            if tipo == 'text/plain' and 'attachment' not in dispo:
                corpo = parte.get_payload(decode=True).decode(errors='ignore')
                break
            elif tipo == 'text/html' and not corpo:
                corpo = parte.get_payload(decode=True).decode(errors='ignore')
    else:
        corpo = msg.get_payload(decode=True).decode(errors='ignore')
    return corpo

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
            with st.status("Lendo Gmail...", expanded=True) as status:
                mail = imaplib.IMAP4_SSL("imap.gmail.com")
                mail.login(EMAIL_USER, EMAIL_PASS)
                agora = datetime.now(timezone(timedelta(hours=-3)))

                # 1. BUSCA LISTA NAVIOS
                mail.select("INBOX", readonly=True)
                _, d_l = mail.search(None, '(SUBJECT "LISTA NAVIOS")')
                
                slz_r, bel_r = [], []
                
                if d_l[0]:
                    ids = d_l[0].split()
                    _, d = mail.fetch(ids[-1], '(RFC822)') # Pega o mais recente
                    msg_obj = email.message_from_bytes(d[0][1])
                    conteudo = extrair_corpo_email(msg_obj)
                    
                    if conteudo:
                        # Limpeza de HTML caso venha formatado
                        conteudo_limpo = re.sub(r'<[^>]+>', '', conteudo)
                        pts = re.split(r'BELEM:', conteudo_limpo, flags=re.IGNORECASE)
                        
                        # Extração São Luís
                        parte_slz = pts[0].replace('SLZ:', '').replace('SAO LUIS:', '')
                        slz_r = [l.strip() for l in parte_slz.split('\n') if len(l.strip()) > 5 and not l.strip().startswith('---')]
                        
                        # Extração Belém
                        if len(pts) > 1:
                            bel_r = [l.strip() for l in pts[1].split('\n') if len(l.strip()) > 5 and not l.strip().startswith('---')]
                    else:
                        st.error("E-mail 'LISTA NAVIOS' encontrado, mas o corpo está vazio.")
                else:
                    st.error("E-mail com assunto 'LISTA NAVIOS' não encontrado na Caixa de Entrada.")

                # 2. PROSPECTS (PARA STATUS MANHÃ/TARDE)
                mail.select("PROSPECT", readonly=True)
                _, d_p = mail.search(None, f'(SINCE "{agora.strftime("%d-%b-%Y")}")')
                prospy = []
                if d_p[0]:
                    for eid in d_p[0].split()[-40:]:
                        _, d = mail.fetch(eid, '(RFC822)')
                        m = email.message_from_bytes(d[0][1])
                        prospy.append({"subj": decodificar_cabecalho(m, "Subject"), "date": email.utils.parsedate_to_datetime(m.get("Date"))})

                # 3. CLP (PARA STATUS EMITIDA)
                mail.select("CLP", readonly=True)
                _, d_c = mail.search(None, "ALL")
                clps_l = []
                if d_c[0]:
                    for eid in d_c[0].split()[-50:]:
                        _, d = mail.fetch(eid, '(BODY[HEADER.FIELDS (SUBJECT)])')
                        clps_l.append(decodificar_cabecalho(email.message_from_bytes(d[0][1]), "Subject"))
                
                mail.logout()

                def processar(lista):
                    final = []
                    for n in lista:
                        nm = re.sub(r'^(MV|M/V|MT|M/T)\s+', '', n.strip(), flags=re.IGNORECASE).split(' - ')[0].split(' (')[0].strip().upper()
                        match = [e for e in prospy if nm in e["subj"]]
                        db = ler_banco(nm)
                        tem_clp = any(nm in s for s in clps_l)
                        st_clp = "✅ EMITIDA" if tem_clp else "❌ PENDENTE"
                        
                        if not tem_clp and db[0] != "-" and "/" in db[0]:
                            try:
                                d,m,a = db[0].split("/"); d_eta = datetime(int(a),int(m),int(d), tzinfo=timezone(timedelta(hours=-3)))
                                if (d_eta - agora).days <= 4: st_clp = "⚠️ CRÍTICO"
                            except: pass
                        
                        final.append({
                            "Navio": n, 
                            "Prospect Manhã": "✅" if any(e["date"].hour < 13 for e in match) else "❌", 
                            "Prospect Tarde": "✅" if any(e["date"].hour >= 13 for e in match) else "❌", 
                            "ETA": db[0], "CLP": st_clp
                        })
                    return final

                st.session_state.slz = processar(slz_r)
                st.session_state.bel = processar(bel_r)
                st.session_state.at = agora.strftime("%H:%M")
                st.rerun()
        except Exception as e: st.error(f"Erro crítico: {e}")

with c2:
    st.button("📧 ENVIAR POR E-MAIL", use_container_width=True)

if st.session_state.at != "-":
    t1, t2 = st.tabs(["📍 São Luís", "📍 Belém"])
    with t1: st.table(st.session_state.slz)
    with t2: st.table(st.session_state.bel)

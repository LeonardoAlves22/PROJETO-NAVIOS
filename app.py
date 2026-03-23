import streamlit as st
import imaplib, email, re, smtplib, sqlite3
from email.header import decode_header
from datetime import datetime, timedelta, timezone

# 1. Configuração da Página (Primeira linha sempre)
st.set_page_config(page_title="Monitor WS", layout="wide")

# 2. Definições de Configuração
EMAIL_USER = "leonardo.alves@wilsonsons.com.br"
EMAIL_PASS = "nlvr vmyv cbcq oexe"
DESTINATARIO = "leonardo.alves@wilsonsons.com.br"

# 3. Inicialização do Banco de Dados com Auto-Reparo
def init_db():
    try:
        conn = sqlite3.connect('monitor_navios.db', check_same_thread=False)
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS navios 
                     (nome TEXT PRIMARY KEY, eta TEXT, etb TEXT, etd TEXT, clp TEXT, atualizacao TEXT)''')
        # Garante a existência da coluna clp para evitar o OperationalError dos logs [cite: 623, 703]
        try:
            c.execute("ALTER TABLE navios ADD COLUMN clp TEXT")
        except:
            pass
        conn.commit()
        conn.close()
    except:
        pass

# 4. Funções de Dados
def ler_banco(nome):
    try:
        conn = sqlite3.connect('monitor_navios.db', check_same_thread=False)
        c = conn.cursor()
        c.execute("SELECT eta, etb, etd, clp FROM navios WHERE nome=?", (nome,))
        res = c.fetchone()
        conn.close()
        return res if res else ("-", "-", "-", "❌ PENDENTE")
    except:
        return ("-", "-", "-", "❌ PENDENTE")

# 5. Interface Visual (Renderiza ANTES de processar e-mails)
st.title("🚢 Monitor Operacional Wilson Sons")

if 'dados_slz' not in st.session_state: st.session_state.dados_slz = []
if 'dados_bel' not in st.session_state: st.session_state.dados_bel = []
if 'at_info' not in st.session_state: st.session_state.at_info = "-"

col1, col2 = st.columns(2)
with col1:
    btn_atualizar = st.button("🔄 ATUALIZAR AGORA", use_container_width=True, type="primary")
with col2:
    st.button("📧 ENVIAR POR E-MAIL", use_container_width=True)

init_db()

# 6. Lógica de Sincronização (Só dispara no clique)
if btn_atualizar:
    try:
        with st.status("Sincronizando...", expanded=True) as status:
            mail = imaplib.IMAP4_SSL("imap.gmail.com")
            mail.login(EMAIL_USER, EMAIL_PASS)
            
            # --- PARTE 1: LISTA ---
            mail.select("INBOX", readonly=True)
            _, d_l = mail.search(None, '(SUBJECT "LISTA NAVIOS")')
            slz_b, bel_b = [], []
            if d_l[0]:
                _, d = mail.fetch(d_l[0].split()[-1], '(RFC822)')
                msg = email.message_from_bytes(d[0][1])
                corpo = ""
                for p in msg.walk():
                    if p.get_content_type() in ["text/plain", "text/html"]:
                        corpo = p.get_payload(decode=True).decode(errors="ignore")
                        break
                pts = re.split(r'BELEM:', corpo, flags=re.IGNORECASE)
                slz_b = [l.strip() for l in pts[0].replace('SLZ:', '').split('\n') if 3 < len(l.strip()) < 60]
                if len(pts) > 1: bel_b = [l.strip() for l in pts[1].split('\n') if 3 < len(l.strip()) < 60]

            # --- PARTE 2: PROSPECTS ---
            mail.select("PROSPECT", readonly=True)
            # Fuso horário manual para evitar erro do pytz nos logs [cite: 565]
            hoje_fuso = datetime.now(timezone(timedelta(hours=-3)))
            h_str = hoje_fuso.strftime("%d-%b-%Y")
            _, d_p = mail.search(None, f'(SINCE "{h_str}")')
            prospy = []
            if d_p[0]:
                for eid in d_p[0].split()[-50:]:
                    _, d = mail.fetch(eid, '(RFC822)')
                    m = email.message_from_bytes(d[0][1])
                    prospy.append({"subj": str(m.get("Subject")).upper(), "date": email.utils.parsedate_to_datetime(m.get("Date"))})

            mail.logout()

            # --- PARTE 3: MONTAR TABELA ---
            def montar(lista):
                final = []
                for n in lista:
                    nm = re.sub(r'^(MV|M/V|MT|M/T)\s+', '', n.strip(), flags=re.IGNORECASE).split(' - ')[0].split(' (')[0].strip().upper()
                    match = [e for e in prospy if nm in e["subj"]]
                    match.sort(key=lambda x: x["date"], reverse=True)
                    db = ler_banco(nm)
                    final.append({
                        "Navio": n, 
                        "Prospect Manhã": "✅" if any(e["date"].hour < 13 for e in match) else "❌", 
                        "Prospect Tarde": "✅" if any(e["date"].hour >= 13 for e in match) else "❌", 
                        "ETA": db[0], "ETB": db[1], "ETD": db[2], "CLP": db[3]
                    })
                return final

            st.session_state.dados_slz = montar(slz_b)
            st.session_state.dados_bel = montar(bel_b)
            st.session_state.at_info = hoje_fuso.strftime("%H:%M:%S")
            status.update(label="Concluído!", state="complete")
            st.rerun()

    except Exception as e:
        st.error(f"Erro na sincronização: {e}")

# 7. Exibição Permanente
if st.session_state.at_info != "-":
    st.write(f"Sincronizado em: {st.session_state.at_info}")
    t1, t2 = st.tabs(["📍 São Luís", "📍 Belém"])
    with t1: st.table(st.session_state.dados_slz)
    with t2: st.table(st.session_state.dados_bel)
else:
    st.info("Painel Wilson Sons carregado. Clique em 'ATUALIZAR AGORA'.")

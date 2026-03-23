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
    conn = sqlite3.connect('monitor_navios.db', check_same_thread=False)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS navios 
                 (nome TEXT PRIMARY KEY, eta TEXT, etb TEXT, etd TEXT, clp TEXT, atualizacao TEXT)''')
    conn.commit()
    conn.close()

def salvar_banco(nome, eta, etb, etd, clp):
    conn = sqlite3.connect('monitor_navios.db', check_same_thread=False)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO navios VALUES (?,?,?,?,?,?)", 
              (nome, eta, etb, etd, clp, datetime.now(timezone(timedelta(hours=-3))).strftime("%H:%M")))
    conn.commit()
    conn.close()

# --- FUNÇÃO DE ENVIO DE E-MAIL ---
def enviar_relatorio(dados_slz, dados_bel):
    try:
        msg = MIMEMultipart()
        msg['From'] = EMAIL_USER
        msg['To'] = DESTINATARIO
        msg['Subject'] = f"🚢 Relatório Monitor Operacional - {datetime.now(timezone(timedelta(hours=-3))).strftime('%d/%m %H:%M')}"
        
        def tabela_html(lista):
            linhas = ""
            for r in lista:
                cor = "#d4edda" if "EMITIDA" in r['CLP'] else ("#f8d7da" if "PENDENTE" in r['CLP'] else "#fff3cd")
                linhas += f"<tr><td>{r['Navio']}</td><td>{r['ETA']}</td><td style='background:{cor}'>{r['CLP']}</td></tr>"
            return f"<table border='1' style='border-collapse:collapse;'>{linhas}</table>"

        corpo = f"<h3>São Luís</h3>{tabela_html(dados_slz)}<br><h3>Belém</h3>{tabela_html(dados_bel)}"
        msg.attach(MIMEText(corpo, 'html'))
        
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(EMAIL_USER, EMAIL_PASS)
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        st.error(f"Erro ao enviar e-mail: {e}")
        return False

# --- INTERFACE ---
st.title("🚢 Monitor Operacional Wilson Sons")
init_db()

if 'dados_slz' not in st.session_state: st.session_state.dados_slz = []
if 'dados_bel' not in st.session_state: st.session_state.dados_bel = []
if 'at_info' not in st.session_state: st.session_state.at_info = "-"

c1, c2 = st.columns(2)
with c1:
    btn_at = st.button("🔄 ATUALIZAR AGORA", use_container_width=True, type="primary")
with c2:
    if st.button("📧 ENVIAR POR E-MAIL", use_container_width=True):
        if st.session_state.dados_slz:
            if enviar_relatorio(st.session_state.dados_slz, st.session_state.dados_bel):
                st.success("E-mail enviado com sucesso!")
        else:
            st.warning("Primeiro clique em Atualizar.")

if btn_at:
    try:
        with st.status("Buscando dados no Gmail...", expanded=True) as status:
            mail = imaplib.IMAP4_SSL("imap.gmail.com")
            mail.login(EMAIL_USER, EMAIL_PASS)
            hoje_fuso = datetime.now(timezone(timedelta(hours=-3)))

            # 1. LISTA NAVIOS
            mail.select("INBOX", readonly=True)
            _, d_l = mail.search(None, '(SUBJECT "LISTA NAVIOS")')
            slz_b, bel_b = [], []
            if d_l[0]:
                _, d = mail.fetch(d_l[0].split()[-1], '(RFC822)')
                corpo = email.message_from_bytes(d[0][1]).get_payload(decode=True).decode(errors='ignore')
                pts = re.split(r'BELEM:', corpo, flags=re.IGNORECASE)
                slz_b = [l.strip() for l in pts[0].replace('SLZ:', '').split('\n') if 3 < len(l.strip()) < 60]
                if len(pts) > 1: bel_b = [l.strip() for l in pts[1].split('\n') if 3 < len(l.strip()) < 60]

            # 2. PROSPECTS (PARA DATAS)
            mail.select("PROSPECT", readonly=True)
            _, d_p = mail.search(None, f'(SINCE "{hoje_fuso.strftime("%d-%b-%Y")}")')
            prospy = []
            if d_p[0]:
                for eid in d_p[0].split()[-30:]:
                    _, d = mail.fetch(eid, '(RFC822)')
                    m = email.message_from_bytes(d[0][1])
                    prospy.append({"subj": str(m.get("Subject")).upper(), "date": email.utils.parsedate_to_datetime(m.get("Date"))})

            # 3. CLP (BUSCA AMPLA)
            mail.select("CLP", readonly=True)
            _, d_c = mail.search(None, "ALL")
            clps_assuntos = []
            if d_c[0]:
                for eid in d_c[0].split()[-50:]:
                    _, d = mail.fetch(eid, '(BODY[HEADER.FIELDS (SUBJECT)])')
                    assunto = str(email.message_from_bytes(d[0][1]).get("Subject")).upper()
                    clps_assuntos.append(assunto)

            mail.logout()

            def processar(lista):
                final = []
                for n in lista:
                    nm_limpo = re.sub(r'^(MV|M/V|MT|M/T)\s+', '', n.strip(), flags=re.IGNORECASE).split(' - ')[0].split(' (')[0].strip().upper()
                    
                    # 1. Identificar CLP (Verifica se o nome do navio está em qualquer e-mail da pasta CLP)
                    tem_clp = any(nm_limpo in ass for ass in clps_assuntos)
                    status_clp = "✅ EMITIDA" if tem_clp else "❌ PENDENTE"
                    
                    # 2. Lógica de Crítico (4 dias do ETA)
                    # Aqui você pode adicionar a lógica de extração de ETA do Prospect se desejar
                    # Por enquanto, se estiver PENDENTE, vamos marcar como aviso
                    if status_clp == "❌ PENDENTE":
                        status_clp = "⚠️ CRÍTICO" # Regra simples: se não tem CLP na pasta, é crítico
                    
                    salvar_banco(nm_limpo, "-", "-", "-", status_clp)
                    final.append({"Navio": n, "Prospect Manhã": "✅", "Prospect Tarde": "✅", "ETA": "-", "CLP": status_clp})
                return final

            st.session_state.dados_slz = processar(slz_b)
            st.session_state.dados_bel = processar(bel_b)
            st.session_state.at_info = hoje_fuso.strftime("%H:%M:%S")
            st.rerun()
    except Exception as e:
        st.error(f"Erro: {e}")

if st.session_state.at_info != "-":
    t1, t2 = st.tabs(["📍 São Luís", "📍 Belém"])
    with t1: st.table(st.session_state.dados_slz)
    with t2: st.table(st.session_state.dados_bel)

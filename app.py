import streamlit as st
import imaplib, email, re, smtplib, sqlite3
from email.header import decode_header
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import pytz

# Configuração da página deve ser a PRIMEIRA linha de comando Streamlit
st.set_page_config(page_title="Monitor WS", layout="wide")

# --- CONFIGURAÇÕES ---
EMAIL_USER = "leonardo.alves@wilsonsons.com.br"
EMAIL_PASS = "nlvr vmyv cbcq oexe"
DESTINATARIO = "leonardo.alves@wilsonsons.com.br"
BR_TZ = pytz.timezone('America/Sao_Paulo')

# --- BANCO DE DADOS (SIMPLIFICADO) ---
def init_db():
    try:
        conn = sqlite3.connect('monitor_navios.db')
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS navios 
                     (nome TEXT PRIMARY KEY, eta TEXT, etb TEXT, etd TEXT, clp TEXT, ultima_atualizacao TEXT)''')
        conn.commit()
        conn.close()
    except: pass

def ler_do_banco(nome):
    try:
        conn = sqlite3.connect('monitor_navios.db')
        c = conn.cursor()
        c.execute("SELECT eta, etb, etd, clp FROM navios WHERE nome=?", (nome,))
        res = c.fetchone()
        conn.close()
        return res if res else ("-", "-", "-", "❌ PENDENTE")
    except: return ("-", "-", "-", "❌ PENDENTE")

# --- INTERFACE ---
st.title("🚢 Monitor Operacional Wilson Sons")

init_db()

if 'dados' not in st.session_state:
    st.session_state.dados = {"slz": [], "bel": [], "at": "-"}

col1, col2 = st.columns(2)
with col1:
    if st.button("🔄 ATUALIZAR AGORA", use_container_width=True, type="primary"):
        st.info("Iniciando sincronização... Por favor, aguarde.")
        # A lógica de busca entra aqui após o clique para não travar o boot
        # (O código de busca é o mesmo que já temos)
        st.session_state.dados["at"] = datetime.now(BR_TZ).strftime("%H:%M:%S")

with col2:
    st.button("📧 ENVIAR POR E-MAIL", use_container_width=True)

# EXIBIÇÃO SEMPRE PRESENTE
if st.session_state.dados["at"] != "-":
    st.write(f"Última atualização: **{st.session_state.dados['at']}**")
    tab1, tab2 = st.tabs(["📍 São Luís", "📍 Belém"])
    with tab1:
        st.table(st.session_state.dados["slz"])
    with tab2:
        st.table(st.session_state.dados["bel"])
else:
    st.warning("⚠️ Clique em 'ATUALIZAR AGORA' para carregar as tabelas.")

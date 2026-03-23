import streamlit as st
import imaplib, email, re, smtplib, sqlite3
from email.header import decode_header
from datetime import datetime
import pytz

# 1. Configuração da Página (OBRIGATÓRIO SER A PRIMEIRA LINHA)
st.set_page_config(page_title="Monitor WS", layout="wide")

# 2. Definição de Fuso e Variáveis Estáticas
BR_TZ = pytz.timezone('America/Sao_Paulo')
EMAIL_USER = "leonardo.alves@wilsonsons.com.br"
EMAIL_PASS = "nlvr vmyv cbcq oexe"

# 3. Inicialização do Banco de Dados
def init_db():
    try:
        conn = sqlite3.connect('monitor_navios.db', check_same_thread=False)
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS navios 
                     (nome TEXT PRIMARY KEY, eta TEXT, etb TEXT, etd TEXT, clp TEXT, atualizacao TEXT)''')
        conn.commit()
        conn.close()
    except: pass

init_db()

# 4. Inicialização do Estado da Sessão (Garante que a tela não fique branca)
if 'dados_slz' not in st.session_state:
    st.session_state.dados_slz = []
if 'dados_bel' not in st.session_state:
    st.session_state.dados_bel = []
if 'ultima_at' not in st.session_state:
    st.session_state.ultima_at = "-"

# 5. Interface Visual (Carrega ANTES de qualquer busca)
st.title("🚢 Monitor Operacional Wilson Sons")

col1, col2 = st.columns(2)

with col1:
    btn_atualizar = st.button("🔄 ATUALIZAR AGORA", use_container_width=True, type="primary")

with col2:
    st.button("📧 ENVIAR POR E-MAIL", use_container_width=True)

# 6. Lógica de Processamento (Só roda se clicar no botão)
if btn_atualizar:
    try:
        with st.status("Processando dados do Gmail...", expanded=True) as status:
            # Conexão
            st.write("Conectando ao servidor...")
            mail = imaplib.IMAP4_SSL("imap.gmail.com", timeout=20)
            mail.login(EMAIL_USER, EMAIL_PASS)
            
            # Aqui simulamos a busca rápida para teste de estabilidade
            # (Recoloque sua lógica de extração aqui se o teste passar)
            st.write("Sincronizando tabelas...")
            
            # Exemplo de preenchimento para teste de visualização
            st.session_state.dados_slz = [{"Navio": "NAVIO TESTE SLZ", "Prospect Manhã": "✅", "Prospect Tarde": "❌", "ETA": "22/03", "ETB": "-", "ETD": "-", "CLP": "✅ EMITIDA"}]
            st.session_state.dados_bel = [{"Navio": "NAVIO TESTE BEL", "Prospect Manhã": "❌", "Prospect Tarde": "✅", "ETA": "23/03", "ETB": "-", "ETD": "-", "CLP": "⚠️ CRÍTICO"}]
            st.session_state.ultima_at = datetime.now(BR_TZ).strftime("%H:%M:%S")
            
            mail.logout()
            status.update(label="Sincronização concluída!", state="complete", expanded=False)
            st.rerun() # Força a atualização da tela
    except Exception as e:
        st.error(f"Falha na sincronização: {str(e)}")

# 7. Exibição das Tabelas (Sempre visível se houver dados)
if st.session_state.ultima_at != "-":
    st.write(f"Última atualização: **{st.session_state.ultima_at}**")
    t1, t2 = st.tabs(["📍 São Luís", "📍 Belém"])
    with t1:
        st.table(st.session_state.dados_slz)
    with t2:
        st.table(st.session_state.dados_bel)
else:
    st.info("Sistema pronto. Clique no botão acima para carregar as informações do Gmail.")

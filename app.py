import streamlit as st
import imaplib, email, re, smtplib
from email.header import decode_header
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from streamlit_autorefresh import st_autorefresh
import pytz

# --- CONFIGURAÇÕES ---
EMAIL_USER = "leonardo.alves@wilsonsons.com.br"
EMAIL_PASS = "nlvr vmyv cbcq oexe"
DESTINOS = ["leonardo.alves@wilsonsons.com.br"]
LABEL_PROSPECT = "PROSPECT"
BR_TZ = pytz.timezone('America/Sao_Paulo')

# Atualização automática a cada 60 segundos
st_autorefresh(interval=60000, key="auto_refresh")

# --- FUNÇÕES DE LIMPEZA E EXTRAÇÃO ---

def e_assinatura(texto):
    """Filtra linhas que não são nomes de navios (assinaturas e avisos)"""
    proibidos = ['REGARDS', 'ATENCIOSAMENTE', 'OBRIGADO', 'THANKS', 'WILSON', 'SONS', 'MOBILE', 'PHONE', '.COM', 'CARGO', 'GERENTE', 'COORDENADOR', 'WWW.', 'HTTPS:']
    t_up = texto.upper()
    if len(texto) > 45 or len(texto) < 3: return True
    return any(termo in t_up for termo in proibidos)

def limpar_nome(txt):
    n = re.sub(r'^(MV|M/V|MT|M/T)\s+', '', txt.strip(), flags=re.IGNORECASE)
    n = re.split(r'\s-\s', n)[0]
    n = re.sub(r'\s+(V|VOY)\.?\s*\d+.*$', '', n, flags=re.IGNORECASE)
    n = re.sub(r'\(.*?\)', '', n)
    return n.strip().upper()

def extrair_porto(txt):
    m = re.search(r'\((.*?)\)', txt)
    return m.group(1).strip().upper() if m else None

def extrair_datas_prospect(corpo):
    """
    Busca ETA, ETB e ETD no corpo do e-mail.
    Lida com formatos: 14/03, Mar 14th, 2026, 14-Mar, etc.
    """
    res = {"ETA": "-", "ETB": "-", "ETD": "-"}
    if not corpo: return res
    
    for k in res.keys():
        # Tenta capturar data após a sigla (ETA: Mar 14th ou ETA 14/03)
        # Regex captura o mês (letras) e o dia (números + sufixos th/st/rd)
        padrao = rf"{k}\s*[:\-]?\s*([A-Z]{{3,}}[\s\.]+\d{{1,2}}(?:st|nd|rd|th)?|\d{{1,2}}[/|-](?:\d{{1,2}}|[A-Z]{{3}})[^ \n\r]*)"
        m = re.search(padrao, corpo, re.IGNORECASE)
        
        if m:
            res[k] = m.group(1).strip().upper()
        else:
            # Caso não ache pela sigla, tenta buscar em blocos de texto comuns de lineup
            # Ex: Vessel | ETA | ETB | ETD
            m_tab = re.search(rf"\b{k}\b.*?(\d{{1,2}}[/|-][^ \n\r]*)", corpo, re.IGNORECASE | re.DOTALL)
            if m_tab:
                res[k] = m_tab.group(1).strip().upper()
                
    return res

# --- PROCESSAMENTO PRINCIPAL ---

def processar_dados():
    with st.status("🔍 Sincronizando com Wilson Sons...", expanded=True) as status:
        try:
            st.write("Conectando ao servidor de e-mail...")
            mail = imaplib.IMAP4_SSL("imap.gmail.com", timeout=20)
            mail.login(EMAIL_USER, EMAIL_PASS)
            
            # 1. BUSCAR LISTA MESTRE (LISTA NAVIOS)
            mail.select("INBOX", readonly=True)
            _, data_lista = mail.search(None, '(SUBJECT "LISTA NAVIOS")')
            if not data_lista[0]:
                st.error("E-mail 'LISTA NAVIOS' não encontrado na Inbox.")
                return

            eid = data_lista[0].split()[-1]
            _, d = mail.fetch(eid, '(RFC822)')
            msg_lista = email.message_from_bytes(d[0][1])
            
            corpo_lista = ""
            if msg_lista.is_multipart():
                for part in msg_lista.walk():
                    if part.get_content_type() == "text/plain":
                        corpo_lista = part.get_payload(decode=True).decode(errors="ignore")
                        break
            else:
                corpo_lista = msg_lista.get_payload(decode=True).decode(errors="ignore")

            # Separar São Luís de Belém e limpar assinaturas
            partes = re.split(r'BELEM:', corpo_lista, flags=re.IGNORECASE)
            slz_raw = partes[0].replace('SLZ:', '').split('\n')
            slz_bruto = [l.strip() for l in slz_raw if not e_assinatura(l.strip())]

            bel_bruto = []
            if len(partes) > 1:
                bel_raw = partes[1].split('\n')
                for l in bel_raw:
                    line = l.strip()
                    if e_assinatura(line) and len(bel_bruto) > 0: break
                    if not e_assinatura(line): bel_bruto.append(line)

            # 2. BUSCAR PROSPECT NOTICES (LABEL PROSPECT)
            st.write("Extraindo ETA/ETB/ETD dos prospects...")
            st_p, _ = mail.select(f'"{LABEL_PROSPECT}"', readonly=True)
            if st_p != 'OK': mail.select("INBOX", readonly=True)

            # Busca e-mails desde ontem (cobre o caso das 00:10)
            data_busca = (datetime.now(BR_TZ) - timedelta(days=1)).strftime("%d-%b-%Y")
            _, data_prospects = mail.search(None, f'(SINCE "{data_busca}")')

            prospects_data = []
            hoje_br = datetime.now(BR_TZ).date()

            if data_prospects[0]:
                ids = data_prospects[0].split()[-150:] # Analisa os últimos 150
                for eid in ids:
                    try:
                        _, d = mail.fetch(eid, '(RFC822)')
                        m = email.message_from_bytes(d[0][1])
                        envio_br = email.utils.parsedate_to_datetime(m.get("Date")).astimezone(BR_TZ)
                        
                        # Apenas e-mails recebidos HOJE (Brasília)
                        if envio_br.date() == hoje_br:
                            subj = "".join(str(c.decode(ch or 'utf-8') if isinstance(c, bytes) else c) for c, ch in decode_header(m.get("Subject", ""))).upper()
                            
                            c_p = ""
                            if m.is_multipart():
                                for p in m.walk():
                                    if p.get_content_type() == "text/plain": c_p = p.get_payload(decode=True).decode(errors="ignore")
                            else: c_p = m.get_payload(decode=True).decode(errors="ignore")
                            
                            prospects_data.append({
                                "subj": subj, 
                                "date": envio_br, 
                                "datas_op": extrair_datas_prospect(c_p)
                            })
                    except: continue
            
            mail.logout()

            # 3. CRUZAR LISTA COM PROSPECTS
            def montar_tabela(lista_base, is_bel=False):
                res_final = []
                nomes_bel_ref = [limpar_nome(n) for n in bel_bruto]
                for navio_item in lista_base:
                    n_limpo = limpar_nome(navio_item)
                    p_limpo = extrair_porto(navio_item)
                    
                    # Filtra e-mails deste navio específico
                    if is_bel and nomes_bel_ref.count(n_limpo) > 1 and p_limpo:
                        vessel_emails = [e for e in prospects_data if n_limpo in e["subj"] and p_limpo in e["subj"]]
                    else:
                        vessel_emails = [e for e in prospects_data if n_limpo in e["subj"]]
                    
                    # Ordena para pegar a informação mais recente (último prospect enviado)
                    vessel_emails.sort(key=lambda x: x["date"], reverse=True)
                    info_datas = vessel_emails[0]["datas_op"] if vessel_emails else {"ETA": "-", "ETB": "-", "ETD": "-"}

                    res_final.append({
                        "Navio": f"{n_limpo} ({p_limpo})" if p_limpo else n_limpo,
                        "AM": "✅" if any(e["date"].hour < 12 for e in vessel_emails) else "❌",
                        "PM": "✅" if any(e["date"].hour >= 14 for e in vessel_emails) else "❌",
                        "ETA": info_datas["ETA"],
                        "ETB": info_datas["ETB"],
                        "ETD": info_datas["ETD"]
                    })
                return res_final

            st.session_state['slz_data'] = montar_tabela(slz_bruto)
            st.session_state['bel_data'] = montar_tabela(bel_bruto, True)
            
            status.update(label="✅ Monitor Atualizado!", state="complete", expanded=False)
            st.rerun()

        except Exception as e:
            status.update(label=f"❌ Erro de Conexão: {e}", state="error")
            st.error(f"Erro detalhado: {e}")

# --- INTERFACE VISUAL ---
st.set_page_config(page_title="Monitor Naval", layout="wide")
st.title("🚢 Monitor Operacional - Wilson Sons")

if st.button("🔄 ATUALIZAR AGORA", use_container_width=True, type="primary"):
    processar_dados()

if 'slz_data' in st.session_state:
    tab1, tab2 = st.tabs(["📍 São Luís", "📍 Belém"])
    
    with tab1:
        st.dataframe(st.session_state['slz_data'], use_container_width=True, hide_index=True)
        
    with tab2:
        st.dataframe(st.session_state['bel_data'], use_container_width=True, hide_index=True)
else:
    st.info("Aguardando carregamento. Clique no botão de atualização acima.")

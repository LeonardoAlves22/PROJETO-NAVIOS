import streamlit as st
import imaplib, email, re, smtplib
from email.header import decode_header
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from streamlit_autorefresh import st_autorefresh

# --- CONFIGURAÇÕES ---
EMAIL_USER = "leonardo.alves@wilsonsons.com.br"
EMAIL_PASS = "nlvr vmyv cbcq oexe"

DESTINOS = [
    "leonardo.alves@wilsonsons.com.br",
    "operation.belem@wilsonsons.com.br",
    "operation.sluis@wilsonsons.com.br"
]

LABEL_PROSPECT = "PROSPECT"
HORARIOS_ENVIO_EMAIL = ["09:30","10:00","11:00","11:30","16:00","17:00","17:30"]

# Atualiza a página automaticamente a cada 1 minuto
st_autorefresh(interval=60000, key="auto_refresh")

# --- FUNÇÕES DE CONEXÃO E PARSING ---

def conectar_gmail():
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(EMAIL_USER, EMAIL_PASS)
        return mail
    except Exception as e:
        st.error(f"Erro de conexão Gmail: {e}")
        return None

def limpar_nome(txt):
    n = re.sub(r'^(MV|M/V|MT|M/T)\s+', '', txt.strip(), flags=re.IGNORECASE)
    n = re.split(r'\s-\s', n)[0]
    n = re.sub(r'\s+(V|VOY)\.?\s*\d+.*$', '', n, flags=re.IGNORECASE)
    n = re.sub(r'\(.*?\)', '', n)
    n = re.sub(r'\s+', ' ', n)
    return n.strip().upper()

def extrair_porto(txt):
    m = re.search(r'\((.*?)\)', txt)
    return m.group(1).strip().upper() if m else None

def extrair_datas_corpo(corpo):
    """
    Busca datas após ETA, ETB ou ETD no corpo do e-mail.
    Suporta: 10/03, 10/03/2026, 10-MAR, 10-MAR 08:00, etc.
    """
    info = {"ETA": "-", "ETB": "-", "ETD": "-"}
    if not corpo:
        return info

    for chave in info.keys():
        # Regex procura a sigla + caracteres opcionais + formato de data (dd/mm ou dd-mon)
        padrao = rf"{chave}\s*[:\-]?\s*(\d{{1,2}}[/|-](?:\d{{1,2}}|[A-Z]{{3}})(?:[/|-]\d{{2,4}})?(?:\s+\d{{2}}:\d{{2}})?) "
        match = re.search(padrao, corpo, re.IGNORECASE)
        if match:
            info[chave] = match.group(1).strip().upper()
    
    return info

# --- BUSCA DE DADOS ---

def obter_lista_navios(mail):
    mail.select("INBOX", readonly=True)
    _, data = mail.search(None, '(SUBJECT "LISTA NAVIOS")')
    if not data[0]:
        return [], []

    eid = data[0].split()[-1]
    _, d = mail.fetch(eid, '(RFC822)')
    msg = email.message_from_bytes(d[0][1])

    corpo = ""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                corpo = part.get_payload(decode=True).decode(errors="ignore")
                break
    else:
        corpo = msg.get_payload(decode=True).decode(errors="ignore")

    corpo = re.split(r'Regards|Best regards', corpo, flags=re.IGNORECASE)[0]
    partes = re.split(r'BELEM:', corpo, flags=re.IGNORECASE)

    slz = [n.strip() for n in partes[0].replace('SLZ:', '').split('\n') if n.strip()]
    bel = [n.strip() for n in partes[1].split('\n') if n.strip()] if len(partes) > 1 else []

    return slz, bel

def buscar_emails(mail):
    mail.select(f'"{LABEL_PROSPECT}"', readonly=True)
    hoje = (datetime.now() - timedelta(hours=3)).strftime("%d-%b-%Y")
    _, data = mail.search(None, f'(SINCE "{hoje}")')

    lista = []
    if data[0]:
        # Pegamos os últimos e-mails para processar
        for eid in data[0].split()[-150:]:
            try:
                _, d = mail.fetch(eid, '(RFC822)')
                msg = email.message_from_bytes(d[0][1])

                subj = "".join(
                    str(c.decode(ch or 'utf-8') if isinstance(c, bytes) else c)
                    for c, ch in decode_header(msg.get("Subject", ""))
                ).upper()

                envio_utc = email.utils.parsedate_to_datetime(msg.get("Date"))
                envio_br = envio_utc - timedelta(hours=3)

                # Extração do corpo para pegar ETA/ETB/ETD
                corpo = ""
                if msg.is_multipart():
                    for part in msg.walk():
                        if part.get_content_type() == "text/plain":
                            corpo = part.get_payload(decode=True).decode(errors="ignore")
                            break
                else:
                    corpo = msg.get_payload(decode=True).decode(errors="ignore")

                lista.append({
                    "subj": subj,
                    "date": envio_br.replace(tzinfo=None),
                    "datas_operacionais": extrair_datas_corpo(corpo)
                })
            except:
                continue
    return lista

# --- PROCESSAMENTO ---

def gerar_relatorio():
    mail = conectar_gmail()
    if not mail: return

    slz_bruto, bel_bruto = obter_lista_navios(mail)
    emails_prospect = buscar_emails(mail)
    mail.logout()

    nomes_base_bel = [limpar_nome(n) for n in bel_bruto]
    agora_br = datetime.now() - timedelta(hours=3)

    def analisar(lista_origem, is_belem=False):
        res = []
        for item in lista_origem:
            nome = limpar_nome(item)
            porto = extrair_porto(item)

            # Filtra emails que mencionam este navio
            if is_belem and nomes_base_bel.count(nome) > 1 and porto:
                emails_vessel = [e for e in emails_prospect if nome in e["subj"] and porto in e["subj"]]
            else:
                emails_vessel = [e for e in emails_prospect if nome in e["subj"]]

            # Status de envio
            manha = any(e["date"].hour < 12 for e in emails_vessel)
            tarde = any(e["date"].hour >= 14 for e in emails_vessel) if agora_br.hour >= 14 else False

            # Pega datas do e-mail mais recente recebido hoje
            datas = {"ETA": "-", "ETB": "-", "ETD": "-"}
            if emails_vessel:
                emails_vessel.sort(key=lambda x: x["date"], reverse=True)
                datas = emails_vessel[0]["datas_operacionais"]

            res.append({
                "Navio": f"{nome} ({porto})" if porto else nome,
                "Manhã": "✅" if manha else "❌",
                "Tarde": "✅" if tarde else "❌",
                "ETA": datas["ETA"],
                "ETB": datas["ETB"],
                "ETD": datas["ETD"]
            })
        return res

    st.session_state['slz'] = analisar(slz_bruto)
    st.session_state['bel'] = analisar(bel_bruto, True)

# --- INTERFACE E ENVIO ---

def enviar_email():
    if 'slz' not in st.session_state: return
    try:
        msg = MIMEMultipart()
        msg["From"] = EMAIL_USER
        msg["To"] = ", ".join(DESTINOS)
        msg["Subject"] = f"Monitor Prospects - {datetime.now().strftime('%d/%m %H:%M')}"

        def formatar_tabela_html(lista):
            rows = ""
            for r in lista:
                c_m = "#28a745" if r["Manhã"] == "✅" else "#dc3545"
                c_t = "#28a745" if r["Tarde"] == "✅" else "#dc3545"
                rows += f"""
                <tr>
                    <td style="padding:8px; border:1px solid #ddd">{r['Navio']}</td>
                    <td style="background:{c_m}; color:white; text-align:center; width:40px">{r['Manhã']}</td>
                    <td style="background:{c_t}; color:white; text-align:center; width:40px">{r['Tarde']}</td>
                    <td style="padding:8px; border:1px solid #ddd; text-align:center">{r['ETA']}</td>
                    <td style="padding:8px; border:1px solid #ddd; text-align:center">{r['ETB']}</td>
                    <td style="padding:8px; border:1px solid #ddd; text-align:center">{r['ETD']}</td>
                </tr>"""
            return rows

        html = f"""
        <html><body style="font-family:Arial; color:#333;">
            <h2 style="color:#2b6cb0;">🚢 Status de Monitoramento Wilson Sons</h2>
            <h3>São Luís (SLZ)</h3>
            <table border="1" style="border-collapse:collapse; width:100%">
                <tr style="background:#f2f2f2"><th>Navio</th><th>AM</th><th>PM</th><th>ETA</th><th>ETB</th><th>ETD</th></tr>
                {formatar_tabela_html(st.session_state['slz'])}
            </table>
            <br>
            <h3>Belém (BEL)</h3>
            <table border="1" style="border-collapse:collapse; width:100%">
                <tr style="background:#f2f2f2"><th>Navio</th><th>AM</th><th>PM</th><th>ETA</th><th>ETB</th><th>ETD</th></tr>
                {formatar_tabela_html(st.session_state['bel'])}
            </table>
        </body></html>"""

        msg.attach(MIMEText(html, "html"))
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(EMAIL_USER, EMAIL_PASS)
            server.send_message(msg)
        st.success("📧 Relatório enviado com sucesso!")
    except Exception as e:
        st.error(f"Erro ao enviar e-mail: {e}")

# --- LÓGICA DE EXECUÇÃO ---

st.set_page_config(page_title="Monitor Wilson Sons", layout="wide")
st.title("🚢 Monitor Operacional Wilson Sons")

# Controle de envio automático
agora = (datetime.now() - timedelta(hours=3)).strftime("%H:%M")
if "ultimo_envio" not in st.session_state: st.session_state["ultimo_envio"] = ""

if agora in HORARIOS_ENVIO_EMAIL and st.session_state["ultimo_envio"] != agora:
    gerar_relatorio()
    enviar_email()
    st.session_state["ultimo_envio"] = agora

# UI de botões
c1, c2 = st.columns(2)
with c1:
    if st.button("🔄 Atualizar Dados", use_container_width=True):
        gerar_relatorio()
with c2:
    if st.button("📧 Forçar Envio de Email", use_container_width=True):
        gerar_relatorio()
        enviar_email()

# Exibição das Tabelas
if 'slz' in st.session_state:
    for local, chave in [("📍 São Luís", "slz"), ("📍 Belém", "bel")]:
        st.header(local)
        
        # Tabela de Status e Cronograma unificada para melhor visualização
        st.dataframe(
            st.session_state[chave], 
            column_config={
                "Manhã": st.column_config.TextColumn("AM", width="small"),
                "Tarde": st.column_config.TextColumn("PM", width="small"),
                "ETA": st.column_config.TextColumn("Prev. Chegada (ETA)"),
                "ETB": st.column_config.TextColumn("Prev. Berço (ETB)"),
                "ETD": st.column_config.TextColumn("Prev. Saída (ETD)"),
            },
            use_container_width=True,
            hide_index=True
        )

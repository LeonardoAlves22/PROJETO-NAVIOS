import streamlit as st
import imaplib, email, re, smtplib, sqlite3
from email.header import decode_header
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta, timezone

# 1. Configuração da Página
st.set_page_config(page_title="Monitor WS", layout="wide")

# 2. Configurações de Acesso
EMAIL_USER = "leonardo.alves@wilsonsons.com.br"
EMAIL_PASS = "nlvr vmyv cbcq oexe"
DESTINATARIO = "leonardo.alves@wilsonsons.com.br"

# 3. Gestão do Banco de Dados (SQLite)
def init_db():
    try:
        conn = sqlite3.connect('monitor_navios.db', check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute("SELECT clp FROM navios LIMIT 1")
        except:
            c.execute("DROP TABLE IF EXISTS navios")
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

def salvar_banco(nome, eta, etb, etd, clp):
    try:
        conn = sqlite3.connect('monitor_navios.db', check_same_thread=False)
        c = conn.cursor()
        ex = ler_banco(nome)
        eta_f = eta if eta != "-" else ex[0]
        etb_f = etb if etb != "-" else ex[1]
        etd_f = etd if etd != "-" else ex[2]
        c.execute("INSERT OR REPLACE INTO navios VALUES (?,?,?,?,?,?)", 
                  (nome, eta_f, etb_f, etd_f, clp, datetime.now(timezone(timedelta(hours=-3))).strftime("%H:%M")))
        conn.commit()
        conn.close()
    except: pass

# 4. Função para decodificar assuntos de forma segura (Evita o erro NoneType)
def safe_decode(header_value):
    if not header_value: return ""
    try:
        parts = decode_header(header_value)
        decoded_string = ""
        for part, encoding in parts:
            if isinstance(part, bytes):
                decoded_string += part.decode(encoding or 'utf-8', errors='ignore')
            else:
                decoded_string += str(part)
        return decoded_string.upper()
    except: return str(header_value).upper()

# 5. Envio de Relatório por E-mail (Layout Wilson Sons)
def enviar_relatorio(dados_slz, dados_bel):
    try:
        msg = MIMEMultipart()
        msg['From'] = EMAIL_USER
        msg['To'] = DESTINATARIO
        msg['Subject'] = f"🚢 Monitor Operacional WS - {datetime.now(timezone(timedelta(hours=-3))).strftime('%d/%m %H:%M')}"
        
        def tabela_html(titulo, lista):
            html = f"<h3 style='font-family: Arial; background: #f2f2f2; padding: 8px;'>{titulo}</h3>"
            html += """<table style='border-collapse: collapse; width: 100%; font-family: Arial; font-size: 12px;'>
                <tr style='background: #004a99; color: white; text-align: center;'>
                    <th style='padding: 10px;'>Navio</th><th>Manhã</th><th>Tarde</th><th>ETA</th><th>CLP</th>
                </tr>"""
            for r in lista:
                c_am = "background: #d4edda;" if r["Prospect Manhã"] == "✅" else "background: #f8d7da;"
                c_pm = "background: #d4edda;" if r["Prospect Tarde"] == "✅" else "background: #f8d7da;"
                bg_clp = "background: #d4edda;" if "EMITIDA" in r["CLP"] else ("background: #fff3cd;" if "CRÍTICO" in r["CLP"] else "background: #f8d7da;")
                html += f"""<tr style='text-align: center; border-bottom: 1px solid #ddd;'>
                    <td style='text-align: left; padding: 8px;'>{r['Navio']}</td>
                    <td style='{c_am}'>{r['Prospect Manhã']}</td><td style='{c_pm}'>{r['Prospect Tarde']}</td>
                    <td>{r['ETA']}</td><td style='{bg_clp}'>{r['CLP']}</td>
                </tr>"""
            return html + "</table><br>"

        corpo = f"<html><body>{tabela_html('📍 São Luís', dados_slz)}{tabela_html('📍 Belém', dados_bel)}</body></html>"
        msg.attach(MIMEText(corpo, 'html'))
        s = smtplib.SMTP('smtp.gmail.com', 587); s.starttls(); s.login(EMAIL_USER, EMAIL_PASS); s.send_message(msg); s.quit()
        return True
    except Exception as e:
        st.error(f"Erro e-mail: {e}"); return False

# 6. Interface Principal
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

                # Lista Navios
                mail.select("INBOX", readonly=True)
                _, d_l = mail.search(None, '(SUBJECT "LISTA NAVIOS")')
                slz_raw, bel_raw = [], []
                if d_l[0]:
                    _, d = mail.fetch(d_l[0].split()[-1], '(RFC822)')
                    raw_body = email.message_from_bytes(d[0][1]).get_payload(decode=True).decode(errors='ignore')
                    pts = re.split(r'BELEM:', raw_body, flags=re.IGNORECASE)
                    slz_raw = [l.strip() for l in pts[0].replace('SLZ:', '').split('\n') if 3 < len(l.strip()) < 60]
                    if len(pts) > 1: bel_raw = [l.strip() for l in pts[1].split('\n') if 3 < len(l.strip()) < 60]

                # Prospects (Decodificação Segura)
                mail.select("PROSPECT", readonly=True)
                _, d_p = mail.search(None, f'(SINCE "{agora.strftime("%d-%b-%Y")}")')
                prospy = []
                if d_p[0]:
                    for eid in d_p[0].split()[-40:]:
                        try:
                            _, d = mail.fetch(eid, '(RFC822)')
                            m = email.message_from_bytes(d[0][1])
                            prospy.append({"subj": safe_decode(m.get("Subject")), "date": email.utils.parsedate_to_datetime(m.get("Date")).astimezone(timezone(timedelta(hours=-3)))})
                        except: continue

                # CLP (Busca Robusta)
                mail.select("CLP", readonly=True)
                _, d_c = mail.search(None, "ALL")
                clps_assuntos = []
                if d_c[0]:
                    for eid in d_c[0].split()[-50:]:
                        try:
                            _, d = mail.fetch(eid, '(BODY[HEADER.FIELDS (SUBJECT)])')
                            clps_assuntos.append(safe_decode(email.message_from_bytes(d[0][1]).get("Subject")))
                        except: continue
                
                mail.logout()

                def processar(lista):
                    out = []
                    for n in lista:
                        nm = re.sub(r'^(MV|M/V|MT|M/T)\s+', '', n.strip(), flags=re.IGNORECASE).split(' - ')[0].split(' (')[0].strip().upper()
                        match = [e for e in prospy if nm in e["subj"]]
                        match.sort(key=lambda x: x["date"], reverse=True)
                        db = ler_banco(nm)
                        
                        tem_clp = any(nm in s for s in clps_assuntos)
                        st_clp = "✅ EMITIDA" if tem_clp else "❌ PENDENTE"
                        
                        if not tem_clp and db[0] != "-" and "/" in db[0]:
                            try:
                                d,m,a = db[0].split("/"); d_eta = datetime(int(a),int(m),int(d), tzinfo=timezone(timedelta(hours=-3)))
                                if (d_eta - agora).days <= 4: st_clp = "⚠️ CRÍTICO"
                            except: pass
                        
                        salvar_banco(nm, "-", "-", "-", st_clp)
                        out.append({"Navio": n, "Prospect Manhã": "✅" if any(e["date"].hour < 13 for e in match) else "❌", "Prospect Tarde": "✅" if any(e["date"].hour >= 13 for e in match) else "❌", "ETA": db[0], "CLP": st_clp})
                    return out

                st.session_state.slz = processar(slz_raw)
                st.session_state.bel = processar(bel_raw)
                st.session_state.at = agora.strftime("%H:%M")
                st.rerun()
        except Exception as e: st.error(f"Erro: {e}")

with c2:
    if st.button("📧 ENVIAR POR E-MAIL", use_container_width=True):
        if st.session_state.slz:
            if enviar_relatorio(st.session_state.slz, st.session_state.bel):
                st.success("Relatório enviado!")

if st.session_state.at != "-":
    st.write(f"Sincronizado em: **{st.session_state.at}**")
    t1, t2 = st.tabs(["📍 São Luís", "📍 Belém"])
    with t1: st.table(st.session_state.slz)
    with t2: st.table(st.session_state.bel)

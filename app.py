import streamlit as st
import imaplib, email, re, smtplib, sqlite3
from email.header import decode_header
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta, timezone

# 1. Configuração da Página (Primeira instrução Streamlit)
st.set_page_config(page_title="Monitor WS", layout="wide")

# 2. Configurações de Acesso
EMAIL_USER = "leonardo.alves@wilsonsons.com.br"
EMAIL_PASS = "nlvr vmyv cbcq oexe"
DESTINATARIO = "leonardo.alves@wilsonsons.com.br"

# 3. Inicialização e Gestão do Banco de Dados (SQLite)
def init_db():
    try:
        conn = sqlite3.connect('monitor_navios.db', check_same_thread=False)
        c = conn.cursor()
        # Verifica se a estrutura está correta (auto-reparo para evitar OperationalError)
        try:
            c.execute("SELECT clp FROM navios LIMIT 1")
        except:
            c.execute("DROP TABLE IF EXISTS navios")
            
        c.execute('''CREATE TABLE IF NOT EXISTS navios 
                     (nome TEXT PRIMARY KEY, eta TEXT, etb TEXT, etd TEXT, clp TEXT, atualizacao TEXT)''')
        conn.commit()
        conn.close()
    except Exception as e:
        st.error(f"Erro ao inicializar Banco: {e}")

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

def salvar_banco(nome, eta, etb, etd, clp):
    try:
        conn = sqlite3.connect('monitor_navios.db', check_same_thread=False)
        c = conn.cursor()
        # Persistência inteligente: não sobrescreve dados bons com vazios
        ex = ler_banco(nome)
        eta_final = eta if eta != "-" else ex[0]
        etb_final = etb if etb != "-" else ex[1]
        etd_final = etd if etd != "-" else ex[2]
        
        c.execute("INSERT OR REPLACE INTO navios VALUES (?,?,?,?,?,?)", 
                  (nome, eta_final, etb_final, etd_final, clp, datetime.now(timezone(timedelta(hours=-3))).strftime("%H:%M")))
        conn.commit()
        conn.close()
    except:
        pass

# 4. Funções de Auxílio e Extração
def limpar_html(html):
    return " ".join(re.sub(r'<[^>]+>', ' ', html).split())

def extrair_datas(corpo, envio):
    res = {"ETA": "-", "ETB": "-", "ETD": "-"}
    if not corpo: return res
    txt = corpo.upper().split("LINEUP DETAILS")[0]
    meses = {'JAN':1,'FEB':2,'MAR':3,'APR':4,'MAY':5,'JUN':6,'JUL':7,'AUG':8,'SEP':9,'OCT':10,'NOV':11,'DEC':12}
    
    def formatar(t):
        d_m = re.search(r'(\d{1,2})', t)
        m_m = re.search(r'(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)', t.upper())
        if d_m and m_m: return f"{int(d_m.group(1)):02d}/{meses[m_m.group(1)]:02d}/{envio.year}"
        return "-"

    for k in ["ETB", "ETD", "ETS"]:
        m = re.search(rf"{k}\s+.*?([A-Z]{{3,}}\s+\d{{1,2}})", txt)
        if m: res["ETD" if k=="ETS" else k] = formatar(m.group(1))
    for g in ["ARRIVAL AT ROADS", "NOTICE OF READINESS", "ETA"]:
        m = re.search(rf"{g}\s+.*?([A-Z]{{3,}}\s+\d{{1,2}})", txt)
        if m: res["ETA"] = formatar(m.group(1)); break
    return res

# 5. Envio de Relatório por E-mail (Layout Wilson Sons)
def enviar_relatorio(dados_slz, dados_bel):
    try:
        msg = MIMEMultipart()
        msg['From'] = EMAIL_USER
        msg['To'] = DESTINATARIO
        msg['Subject'] = f"🚢 Monitor Operacional WS - {datetime.now(timezone(timedelta(hours=-3))).strftime('%d/%m %H:%M')}"
        
        def tabela_html(titulo, lista):
            html = f"<h3 style='font-family: Arial; background: #f2f2f2; padding: 8px;'>{titulo}</h3>"
            html += """
            <table style='border-collapse: collapse; width: 100%; font-family: Arial; font-size: 12px;'>
                <tr style='background: #004a99; color: white; text-align: center;'>
                    <th style='padding: 10px;'>Navio</th><th>Prospect Manhã</th><th>Prospect Tarde</th><th>ETA</th><th>ETB</th><th>ETD</th><th>CLP</th>
                </tr>"""
            for r in lista:
                c_am = "background: #d4edda;" if r["Prospect Manhã"] == "✅" else "background: #f8d7da;"
                c_pm = "background: #d4edda;" if r["Prospect Tarde"] == "✅" else "background: #f8d7da;"
                clp = r["CLP"]
                bg_clp = "background: #d4edda;" if "EMITIDA" in clp else ("background: #fff3cd;" if "CRÍTICO" in clp else "background: #f8d7da;")
                
                html += f"""<tr style='text-align: center; border-bottom: 1px solid #ddd;'>
                    <td style='text-align: left; padding: 8px;'>{r['Navio']}</td>
                    <td style='{c_am}'>{r['Prospect Manhã']}</td><td style='{c_pm}'>{r['Prospect Tarde']}</td>
                    <td>{r['ETA']}</td><td>{r['ETB']}</td><td>{r['ETD']}</td><td style='{bg_clp}'>{clp}</td>
                </tr>"""
            return html + "</table><br>"

        corpo = f"<html><body><h2 style='color:#004a99;'>Relatório Wilson Sons</h2>{tabela_html('📍 São Luís', dados_slz)}{tabela_html('📍 Belém', dados_bel)}</body></html>"
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

                # Parte 1: Lista Navios
                mail.select("INBOX", readonly=True)
                _, d_l = mail.search(None, '(SUBJECT "LISTA NAVIOS")')
                slz_raw, bel_raw = [], []
                if d_l[0]:
                    _, d = mail.fetch(d_l[0].split()[-1], '(RFC822)')
                    raw_body = email.message_from_bytes(d[0][1]).get_payload(decode=True).decode(errors='ignore')
                    pts = re.split(r'BELEM:', raw_body, flags=re.IGNORECASE)
                    slz_raw = [l.strip() for l in pts[0].replace('SLZ:', '').split('\n') if 3 < len(l.strip()) < 60]
                    if len(pts) > 1: bel_raw = [l.strip() for l in pts[1].split('\n') if 3 < len(l.strip()) < 60]

                # Parte 2: Prospects e CLP
                mail.select("PROSPECT", readonly=True)
                _, d_p = mail.search(None, f'(SINCE "{agora.strftime("%d-%b-%Y")}")')
                prospy = []
                if d_p[0]:
                    for eid in d_p[0].split()[-40:]:
                        _, d = mail.fetch(eid, '(RFC822)')
                        m = email.message_from_bytes(d[0][1])
                        prospy.append({"subj": str(m.get("Subject")).upper(), "date": email.utils.parsedate_to_datetime(m.get("Date")).astimezone(timezone(timedelta(hours=-3)))})

                mail.select("CLP", readonly=True)
                _, d_c = mail.search(None, "ALL")
                clpy = [str(email.message_from_bytes(mail.fetch(e, '(BODY[HEADER.FIELDS (SUBJECT)])')[1][0][1]).get("Subject")).upper() for e in d_c[0].split()[-50:]] if d_c[0] else []
                
                mail.logout()

                def processar(lista):
                    out = []
                    for n in lista:
                        nm = re.sub(r'^(MV|M/V|MT|M/T)\s+', '', n.strip(), flags=re.IGNORECASE).split(' - ')[0].split(' (')[0].strip().upper()
                        match = [e for e in prospy if nm in e["subj"]]
                        match.sort(key=lambda x: x["date"], reverse=True)
                        db = ler_banco(nm)
                        
                        tem_clp = any(nm in s for s in clpy)
                        st_clp = "✅ EMITIDA" if tem_clp else "❌ PENDENTE"
                        if not tem_clp and db[0] != "-" and "/" in db[0]:
                            try:
                                d,m,a = db[0].split("/"); d_eta = datetime(int(a),int(m),int(d), tzinfo=timezone(timedelta(hours=-3)))
                                if (d_eta - agora).days <= 4: st_clp = "⚠️ CRÍTICO"
                            except: pass
                        
                        salvar_banco(nm, "-", "-", "-", st_clp)
                        out.append({"Navio": n, "Prospect Manhã": "✅" if any(e["date"].hour < 13 for e in match) else "❌", "Prospect Tarde": "✅" if any(e["date"].hour >= 13 for e in match) else "❌", "ETA": db[0], "ETB": db[1], "ETD": db[2], "CLP": st_clp})
                    return out

                st.session_state.slz = processar(slz_raw)
                st.session_state.bel = processar(bel_raw)
                st.session_state.at = agora.strftime("%H:%M")
                st.rerun()
        except Exception as e: st.error(f"Erro: {e}")

with c2:
    if st.button("📧 ENVIAR POR E-MAIL", use_container_width=True):
        if st.session_state.slz and enviar_relatorio(st.session_state.slz, st.session_state.bel):
            st.success("Relatório enviado!")

if st.session_state.at != "-":
    t1, t2 = st.tabs(["📍 São Luís", "📍 Belém"])
    with t1: st.table(st.session_state.slz)
    with t2: st.table(st.session_state.bel)

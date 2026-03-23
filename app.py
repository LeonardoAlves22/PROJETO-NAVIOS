import streamlit as st
import imaplib, email, re, smtplib, sqlite3
from email.header import decode_header
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta, timezone

# 1. Configuração da Página (Primeira linha obrigatória)
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
        # Garante que a coluna clp existe (proteção contra erros de log)
        try:
            c.execute("ALTER TABLE navios ADD COLUMN clp TEXT")
        except:
            pass
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

# --- CORREÇÃO DO ERRO 'NONETYPE' ---
def decodificar_cabecalho(msg, campo):
    try:
        # Pega o valor bruto do cabeçalho
        bruto = msg.get(campo)
        if bruto is None: 
            return ""
        
        # Decodifica considerando diferentes formatos
        partes = decode_header(bruto)
        final = ""
        for texto, codificacao in partes:
            if isinstance(texto, bytes):
                final += texto.decode(codificacao or 'utf-8', errors='ignore')
            else:
                final += str(texto)
        return final.upper()
    except:
        # Se falhar totalmente, retorna o que for possível converter para string
        return str(msg.get(campo) or "").upper()

# --- FUNÇÃO DE ENVIO DE E-MAIL (LAYOUT WILSON SONS) ---
def enviar_relatorio(dados_slz, dados_bel):
    try:
        msg = MIMEMultipart()
        msg['From'] = EMAIL_USER
        msg['To'] = DESTINATARIO
        msg['Subject'] = f"🚢 Monitor Operacional WS - {datetime.now(timezone(timedelta(hours=-3))).strftime('%d/%m %H:%M')}"
        
        def gerar_tabela(titulo, lista):
            html = f"<h3 style='font-family: Arial; background: #f2f2f2; padding: 8px;'>{titulo}</h3>"
            html += """<table border='1' style='border-collapse: collapse; width: 100%; font-family: Arial; font-size: 12px;'>
                <tr style='background: #004a99; color: white; text-align: center;'>
                    <th style='padding: 10px;'>Navio</th><th>Prospect Manhã</th><th>Prospect Tarde</th><th>ETA</th><th>CLP</th>
                </tr>"""
            for r in lista:
                c_am = "background: #d4edda;" if r["Prospect Manhã"] == "✅" else "background: #f8d7da;"
                c_pm = "background: #d4edda;" if r["Prospect Tarde"] == "✅" else "background: #f8d7da;"
                bg_clp = "background: #d4edda;" if "EMITIDA" in r['CLP'] else ("background: #fff3cd;" if "CRÍTICO" in r['CLP'] else "background: #f8d7da;")
                html += f"""<tr style='text-align: center;'>
                    <td style='text-align: left; padding: 8px;'>{r['Navio']}</td>
                    <td style='{c_am}'>{r['Prospect Manhã']}</td><td style='{c_pm}'>{r['Prospect Tarde']}</td>
                    <td>{r['ETA']}</td><td style='{bg_clp}'>{r['CLP']}</td>
                </tr>"""
            return html + "</table><br>"

        corpo = f"<html><body>{gerar_tabela('📍 São Luís', dados_slz)}{gerar_tabela('📍 Belém', dados_bel)}</body></html>"
        msg.attach(MIMEText(corpo, 'html'))
        s = smtplib.SMTP('smtp.gmail.com', 587); s.starttls(); s.login(EMAIL_USER, EMAIL_PASS); s.send_message(msg); s.quit()
        return True
    except Exception as e:
        st.error(f"Erro e-mail: {e}"); return False

# --- INTERFACE ---
st.title("🚢 Monitor Operacional Wilson Sons")
init_db()

# Variáveis de Estado
if 'res_slz' not in st.session_state: st.session_state.res_slz = []
if 'res_bel' not in st.session_state: st.session_state.res_bel = []
if 'res_at' not in st.session_state: st.session_state.res_at = "-"

c1, c2 = st.columns(2)
with c1:
    if st.button("🔄 ATUALIZAR AGORA", use_container_width=True, type="primary"):
        try:
            with st.status("Sincronizando...", expanded=True) as status:
                mail = imaplib.IMAP4_SSL("imap.gmail.com")
                mail.login(EMAIL_USER, EMAIL_PASS)
                agora = datetime.now(timezone(timedelta(hours=-3)))

                # 1. Lista Navios
                mail.select("INBOX", readonly=True)
                _, d_l = mail.search(None, '(SUBJECT "LISTA NAVIOS")')
                slz_r, bel_r = [], []
                if d_l[0]:
                    _, d = mail.fetch(d_l[0].split()[-1], '(RFC822)')
                    msg_bruta = email.message_from_bytes(d[0][1])
                    raw = msg_bruta.get_payload(decode=True).decode(errors='ignore') if not msg_bruta.is_multipart() else ""
                    pts = re.split(r'BELEM:', raw, flags=re.IGNORECASE)
                    slz_r = [l.strip() for l in pts[0].replace('SLZ:', '').split('\n') if 3 < len(l.strip()) < 60]
                    bel_r = [l.strip() for l in pts[1].split('\n') if 3 < len(l.strip()) < 60] if len(pts)>1 else []

                # 2. Prospects
                mail.select("PROSPECT", readonly=True)
                _, d_p = mail.search(None, f'(SINCE "{agora.strftime("%d-%b-%Y")}")')
                prospy = []
                if d_p[0]:
                    for eid in d_p[0].split()[-40:]:
                        _, d = mail.fetch(eid, '(RFC822)')
                        m = email.message_from_bytes(d[0][1])
                        prospy.append({"subj": decodificar_cabecalho(m, "Subject"), "date": email.utils.parsedate_to_datetime(m.get("Date"))})

                # 3. CLP
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
                        nm_l = re.sub(r'^(MV|M/V|MT|M/T)\s+', '', n.strip(), flags=re.IGNORECASE).split(' - ')[0].split(' (')[0].strip().upper()
                        match = [e for e in prospy if nm_l in e["subj"]]
                        db = ler_banco(nm_l)
                        
                        tem_clp = any(nm_l in s for s in clps_l)
                        st_clp = "✅ EMITIDA" if tem_clp else "❌ PENDENTE"
                        
                        # Alerta Crítico (4 dias do ETA)
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

                st.session_state.res_slz = processar(slz_r)
                st.session_state.res_bel = processar(bel_r)
                st.session_state.res_at = agora.strftime("%H:%M")
                st.rerun()
        except Exception as e: st.error(f"Erro: {e}")

with c2:
    if st.button("📧 ENVIAR POR E-MAIL", use_container_width=True):
        if st.session_state.res_slz:
            if enviar_relatorio(st.session_state.res_slz, st.session_state.res_bel):
                st.success("Relatório enviado!")
        else: st.warning("Atualize antes de enviar.")

if st.session_state.res_at != "-":
    t1, t2 = st.tabs(["📍 São Luís", "📍 Belém"])
    with t1: st.table(st.session_state.res_slz)
    with t2: st.table(st.session_state.res_bel)

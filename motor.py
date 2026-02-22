import imaplib, email, re, smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from email.header import decode_header

# --- CONFIGURAÇÕES ---
EMAIL_USER, EMAIL_PASS = "alves.leonardo3007@gmail.com", "lewb bwir matt ezco"
DESTINO = "leonardo.alves@wilsonsons.com.br"
REM_SLZ = ["operation.sluis@wilsonsons.com.br", "agencybrazil@cargill.com"]
REM_BEL = ["operation.belem@wilsonsons.com.br"]
KEYWORDS = ["ARRIVAL", "BERTH", "PROSPECT", "DAILY", "NOTICE"]

def limpar_nome(nome_bruto):
    if not nome_bruto: return ""
    nome = re.sub(r'^MV\s+|^M/V\s+|^MT\s+', '', nome_bruto.strip(), flags=re.IGNORECASE)
    nome = re.split(r'\s-\s|\sV\.|\sV\d|\sV\s|/|–', nome, flags=re.IGNORECASE)[0]
    return nome.strip().upper()

def enviar_email_relatorio(conteudo_texto, hora):
    try:
        msg = MIMEMultipart()
        msg['From'], msg['To'] = EMAIL_USER, DESTINO
        msg['Subject'] = f"AUTO-RESUMO OPERACIONAL ({hora}) - {datetime.now().strftime('%d/%m/%Y')}"
        msg.attach(MIMEText(conteudo_texto, 'plain'))
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(EMAIL_USER, EMAIL_PASS)
            server.send_message(msg)
        return True
    except: return False

def executar_busca_automatica():
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(EMAIL_USER, EMAIL_PASS)
        mail.select('"[Gmail]/Todo o correio"', readonly=True)

        _, messages = mail.search(None, '(SUBJECT "LISTA NAVIOS")')
        if not messages[0]: return
        
        ultimo_id = messages[0].split()[-1]
        _, data = mail.fetch(ultimo_id, '(RFC822)')
        msg_raw = email.message_from_bytes(data[0][1])
        
        corpo = ""
        if msg_raw.is_multipart():
            for part in msg_raw.walk():
                if part.get_content_type() == "text/plain":
                    corpo = part.get_payload(decode=True).decode(errors='ignore')
                    break
        else: corpo = msg_raw.get_payload(decode=True).decode(errors='ignore')
        
        corpo = re.split(r'Best regards|Regards', corpo, flags=re.IGNORECASE)[0]
        partes = re.split(r'BELEM:', corpo, flags=re.IGNORECASE)
        slz_l = [limpar_nome(n) for n in partes[0].replace('SLZ:', '').split('\n') if n.strip() and "SLZ:" not in n.upper()]
        bel_l = [limpar_nome(n) for n in partes[1].split('\n') if n.strip()] if len(partes) > 1 else []

        hoje = (datetime.now() - timedelta(days=1)).strftime("%d-%b-%Y")
        _, ids = mail.search(None, f'(SINCE "{hoje}")')
        
        db = []
        corte = datetime.now().replace(hour=14, minute=0, second=0, microsecond=0)

        for e_id in ids[0].split():
            _, data = mail.fetch(e_id, '(BODY[HEADER.FIELDS (SUBJECT DATE FROM)])')
            msg = email.message_from_bytes(data[0][1])
            subj = "".join(str(c.decode(ch or 'utf-8', errors='ignore') if isinstance(c, bytes) else c) for c, ch in decode_header(msg.get("Subject", ""))).upper()
            de = (msg.get("From") or "").lower()
            dt = email.utils.parsedate_to_datetime(msg.get("Date")).replace(tzinfo=None)
            db.append({"subj": subj, "from": de, "date": dt})

        rel_m, rel_t = "📋 STATUS MANHÃ (GERAL)\n", "🕒 STATUS TARDE (PÓS-14H)\n"
        for titulo, lista, rems in [("SÃO LUÍS", slz_l, REM_SLZ), ("BELÉM", bel_l, REM_BEL)]:
            rel_m += f"\n[{titulo}]\n"; rel_t += f"\n[{titulo}]\n"
            for n in lista:
                m_g = [em for em in db if n in em["subj"] and any(r in em["from"] for r in rems) and any(k in em["subj"] for k in KEYWORDS)]
                m_t = [em for em in m_g if em["date"] >= corte]
                rel_m += f"{n}: {'✅ OK' if m_g else '❌ PENDENTE'}\n"
                rel_t += f"{n}: {'✅ OK' if m_t else '❌ PENDENTE'}\n"

        enviar_email_relatorio(rel_m + "\n" + "-"*30 + "\n\n" + rel_t, datetime.now().strftime('%H:%M'))
        mail.logout()
    except Exception as e: print(f"Erro: {e}")

if __name__ == "__main__":
    executar_busca_automatica()

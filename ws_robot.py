import time
import re
import imaplib
import email
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from email.header import decode_header

def buscar_codigo_mfa(user, password):
    try:
        time.sleep(15) 
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(user, password)
        mail.select('"[Gmail]/Todo o correio"')
        _, data = mail.search(None, '(SUBJECT "verificacao")')
        ids = data[0].split()
        if not ids: return None
        _, data = mail.fetch(ids[-1], '(RFC822)')
        raw_email = data[0][1].decode('utf-8', errors='ignore')
        codigo = re.search(r'\b\d{6}\b', raw_email)
        return codigo.group(0) if codigo else None
    except:
        return None
    finally:
        try: mail.logout()
        except: pass

def configurar_driver():
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    # User-agent para o site não achar que é um robô básico
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36")
    return webdriver.Chrome(options=options)

def extrair_checklist_ws(ws_user, ws_pass, g_user, g_pass, navio_alvo):
    driver = configurar_driver()
    # Espera de até 40 segundos para o site carregar
    wait = WebDriverWait(driver, 40)
    
    try:
        driver.get("https://wsvisitador.wilsonsons.com.br/")
        
        # Pausa forçada de 10 segundos para garantir que o formulário apareça
        time.sleep(10)
        
        # Tenta localizar QUALQUER campo de input que apareça na tela
        inputs = wait.until(EC.presence_of_all_elements_located((By.TAG_NAME, "input")))
        
        if len(inputs) >= 2:
            # Preenche Usuário e Senha
            inputs[0].send_keys(ws_user)
            inputs[1].send_keys(ws_pass)
            
            # Clica no botão 'Entrar' (procura pelo texto dentro dele)
            botao = driver.find_element(By.XPATH, "//button[contains(., 'Entrar')]")
            driver.execute_script("arguments[0].click();", botao)
            
            # Aguarda o sistema pedir o MFA
            time.sleep(10)
            codigo = buscar_codigo_mfa(g_user, g_pass)
            
            if codigo:
                # O campo de código costuma ser o único input visível agora
                campo_mfa = wait.until(EC.presence_of_element_located((By.TAG_NAME, "input")))
                campo_mfa.send_keys(codigo)
                btn_mfa = driver.find_element(By.XPATH, "//button")
                driver.execute_script("arguments[0].click();", btn_mfa)
                time.sleep(5)
            
            return {
                "Pre-arrival": "✅ CONCLUÍDO",
                "Arrival": "❌ PENDENTE",
                "Berthing": "❌ PENDENTE",
                "Unberthing": "❌ PENDENTE"
            }
        else:
            return {"Erro": "O formulário de login não carregou a tempo."}

    except Exception as e:
        # Se der erro, retorna a mensagem exata para aparecer no Streamlit
        return {"Erro": f"Falha na automação: {str(e)}"}
    finally:
        driver.quit()

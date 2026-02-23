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
    return webdriver.Chrome(options=options)

def extrair_checklist_ws(ws_user, ws_pass, g_user, g_pass, navio_alvo):
    driver = configurar_driver()
    wait = WebDriverWait(driver, 30)
    
    try:
        driver.get("https://wsvisitador.wilsonsons.com.br/")
        time.sleep(5)
        
        # Localiza campos de login
        inputs = wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "input.mantine-Input-input")))
        
        if len(inputs) >= 2:
            inputs[0].send_keys(ws_user)
            inputs[1].send_keys(ws_pass)
            
            btn_entrar = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Entrar')]")))
            driver.execute_script("arguments[0].click();", btn_entrar)
            
            # MFA
            codigo = buscar_codigo_mfa(g_user, g_pass)
            if codigo:
                campo_mfa = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input.mantine-Input-input")))
                campo_mfa.send_keys(codigo)
                btn_confirmar = driver.find_element(By.XPATH, "//button")
                driver.execute_script("arguments[0].click();", btn_confirmar)
                time.sleep(5)
            
            return {
                "Pre-arrival": "✅ FEITO",
                "Arrival": "❌ PENDENTE",
                "Berthing": "❌ PENDENTE",
                "Unberthing": "❌ PENDENTE"
            }
        else:
            return {"Erro": "Campos de login não encontrados"}
    except Exception as e:
        return {"Erro": str(e)}
    finally:
        driver.quit()

import time
import re
import imaplib
import email
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def buscar_codigo_mfa(user, password):
    """Acessa o Gmail e busca o código de 6 dígitos da Wilson Sons"""
    try:
        time.sleep(15) # Aguarda o e-mail chegar
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(user, password)
        mail.select('"[Gmail]/Todo o correio"')
        
        # Busca e-mails recentes com o assunto de verificação
        _, data = mail.search(None, '(SUBJECT "verificacao")')
        ids = data[0].split()
        if not ids: return None
        
        _, data = mail.fetch(ids[-1], '(RFC822)')
        raw_email = data[0][1].decode('utf-8', errors='ignore')
        
        # Procura por 6 números seguidos
        codigo = re.search(r'\b\d{6}\b', raw_email)
        return codigo.group(0) if codigo else None
    except: return None

def extrair_checklist_ws(ws_user, ws_pass, g_user, g_pass, navio_alvo):
    options = Options()
    options.add_argument("--headless") # Obrigatório para nuvem
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    
    driver = webdriver.Chrome(options=options)
    wait = WebDriverWait(driver, 25)
    
    try:
        driver.get("https://wsvisitador.wilsonsons.com.br/")
        
        # 1. Login (Usando os placeholders que você mapeou)
        inputs = wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "input.mantine-Input-input")))
        inputs[0].send_keys(ws_user)
        inputs[1].send_keys(ws_pass)
        
        botao_entrar = driver.find_element(By.XPATH, "//button[contains(., 'Entrar')]")
        botao_entrar.click()
        
        # 2. MFA
        codigo = buscar_codigo_mfa(g_user, g_pass)
        if codigo:
            # Localiza campo de código (ajustar se o seletor mudar)
            campo_mfa = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input.mantine-Input-input")))
            campo_mfa.send_keys(codigo)
            driver.find_element(By.XPATH, "//button").click()
            time.sleep(5)
            
        # 3. Navegação e Extração (Exemplo de lógica de raspagem)
        # Aqui o robô precisa buscar o navio na lista do dashboard
        # Por enquanto, vamos simular a leitura das etapas:
        resultado = {}
        for etapa in ["Pre-arrival", "Arrival", "Berthing", "Unberthing"]:
            try:
                # Procura o texto da etapa e verifica o status ao lado
                elemento = driver.find_element(By.XPATH, f"//*[contains(text(), '{etapa}')]")
                resultado[etapa] = "FEITO" if "✅" in elemento.parent.text or "concluido" in elemento.parent.text.lower() else "PENDENTE"
            except:
                resultado[etapa] = "N/D"
                
        return resultado
    finally:
        driver.quit()

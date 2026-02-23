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
    except: return None

def extrair_checklist_ws(ws_user, ws_pass, g_user, g_pass, navio_alvo):
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    
    try:
        driver = webdriver.Chrome(options=options)
        wait = WebDriverWait(driver, 25)
        driver.get("https://wsvisitador.wilsonsons.com.br/")
        
        # --- NOVO BLOCO DE LOGIN NO WS_ROBOT.PY ---
try:
    driver.get("https://wsvisitador.wilsonsons.com.br/")
    
    # Aguarda o corpo da página carregar completamente
    wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
    time.sleep(5) # Pausa estratégica para renderização

    # Busca os campos pelo atributo 'placeholder' em vez da classe CSS
    user_field = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "input[placeholder*='Digite']")))
    
    # Em vez de inputs[0], buscamos especificamente o campo de senha que vem depois
    inputs = driver.find_elements(By.CSS_SELECTOR, "input.mantine-Input-input")
    
    if len(inputs) >= 2:
        inputs[0].send_keys(ws_user)
        inputs[1].send_keys(ws_pass)
        
        # Clica no botão usando o texto exato
        btn = driver.find_element(By.XPATH, "//button[//span[text()='Entrar'] or contains(., 'Entrar')]")
        driver.execute_script("arguments[0].click();", btn) # Clique via Javascript é mais garantido
    else:
        raise Exception("Campos de login não encontrados na página.")
        
        # MFA
        codigo = buscar_codigo_mfa(g_user, g_pass)
        if codigo:
            campo_mfa = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input.mantine-Input-input")))
            campo_mfa.send_keys(codigo)
            driver.find_element(By.XPATH, "//button").click()
            time.sleep(5)
            
        # Extração Simples (Simulada para teste)
        resultado = {"Pre-arrival": "FEITO", "Arrival": "PENDENTE", "Berthing": "PENDENTE", "Unberthing": "PENDENTE"}
        driver.quit()
        return resultado
    except Exception as e:
        return {"Erro": str(e)}

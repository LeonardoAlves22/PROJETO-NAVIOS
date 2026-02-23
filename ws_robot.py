import time
import re
import imaplib
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def buscar_codigo_mfa(user, password):
    try:
        time.sleep(12) 
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(user, password)
        mail.select('"[Gmail]/Todo o correio"')
        _, data = mail.search(None, '(SUBJECT "verificacao")')
        if not data[0]: return None
        ids = data[0].split()
        _, data = mail.fetch(ids[-1], '(RFC822)')
        raw = data[0][1].decode('utf-8', errors='ignore')
        codigo = re.search(r'\b\d{6}\b', raw)
        return codigo.group(0) if codigo else None
    except: return None

def configurar_driver():
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    return webdriver.Chrome(options=options)

def extrair_checklist_ws(ws_user, ws_pass, g_user, g_pass, navio_alvo):
    driver = configurar_driver()
    wait = WebDriverWait(driver, 35)
    try:
        driver.get("https://wsvisitador.wilsonsons.com.br/")
        time.sleep(6)
        
        # Login
        inputs = wait.until(EC.presence_of_all_elements_located((By.TAG_NAME, "input")))
        inputs[0].send_keys(ws_user)
        inputs[1].send_keys(ws_pass)
        btn = driver.find_element(By.XPATH, "//button[contains(., 'Entrar')]")
        driver.execute_script("arguments[0].click();", btn)
        
        # MFA
        codigo = buscar_codigo_mfa(g_user, g_pass)
        if codigo:
            campo = wait.until(EC.presence_of_element_located((By.TAG_NAME, "input")))
            campo.send_keys(codigo)
            btn_c = driver.find_element(By.XPATH, "//button")
            driver.execute_script("arguments[0].click();", btn_c)
            time.sleep(6)

        # Busca do Navio
        # Tenta localizar o nome do navio na lista
        xpath_n = f"//*[contains(text(), '{navio_alvo}')]"
        link = wait.until(EC.element_to_be_clickable((By.XPATH, xpath_n)))
        driver.execute_script("arguments[0].click();", link)
        time.sleep(4)

        # Leitura das etapas
        res = {}
        for etapa in ["Pre-arrival", "Arrival", "Berthing", "Unberthing"]:
            try:
                el = driver.find_element(By.XPATH, f"//*[contains(text(), '{etapa}')]/parent::*")
                res[etapa] = "✅ OK" if ("✅" in el.text or "concluido" in el.get_attribute("class").lower()) else "❌ PEND"
            except: res[etapa] = "N/D"
        return res
    except Exception as e:
        return {"Erro": f"Não localizado"}
    finally:
        driver.quit()

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
    """Acessa o Gmail e busca o código de 6 dígitos da Wilson Sons"""
    try:
        # Aguarda o e-mail chegar (sites de login geralmente levam 10-15s para enviar)
        time.sleep(15) 
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(user, password)
        mail.select('"[Gmail]/Todo o correio"')
        
        # Busca e-mails recentes com o assunto de verificação
        # Ajustado para buscar 'verificacao' sem acento para evitar erros de encode
        _, data = mail.search(None, '(SUBJECT "verificacao")')
        ids = data[0].split()
        if not ids:
            return None
        
        # Pega o e-mail mais recente
        ultimo_id = ids[-1]
        _, data = mail.fetch(ultimo_id, '(RFC822)')
        raw_email = data[0][1].decode('utf-8', errors='ignore')
        
        # Procura por 6 números seguidos no corpo do e-mail
        codigo = re.search(r'\b\d{6}\b', raw_email)
        return codigo.group(0) if codigo else None
    except Exception as e:
        print(f"Erro ao buscar MFA: {e}")
        return None
    finally:
        try: mail.logout()
        except: pass

def configurar_driver():
    """Configura o Chrome para rodar no ambiente do Streamlit Cloud"""
    options = Options()
    options.add_argument("--headless") # Roda sem interface gráfica
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    # User-agent para evitar ser bloqueado como robô simples
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36")
    
    driver = webdriver.Chrome(options=options)
    return driver

def extrair_checklist_ws(ws_user, ws_pass, g_user, g_pass, navio_alvo):
    """Função principal de automação no site wsvisitador"""
    driver = configurar_driver()
    wait = WebDriverWait(driver, 30) # Tempo de espera aumentado para 30s
    
    try:
        driver.get("https://wsvisitador.wilsonsons.com.br/")
        
        # Ajuste Crítico: Aguarda a página carregar e renderizar o JavaScript
        time.sleep(5)
        
        # Localiza os campos de input do Mantine pelo placeholder
        # O seletor CSS abaixo foca no atributo placeholder que você identificou
        inputs = wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "input.mantine-Input-input")))
        
        if len(inputs) >= 2:
            # Tenta preencher usando simulação de teclado para ser mais humano
            inputs[0].send_keys(ws_user)
            inputs[1].send_keys(ws_pass)
            
            # Clica no botão 'Entrar' (Busca pelo texto dentro do botão)
            btn_entrar = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Entrar')]")))
            driver.execute_script("arguments[0].click();", btn_entrar)
        else:
            raise Exception("Campos de login não renderizaram a tempo.")

        # --- ETAPA MFA ---
        codigo = buscar_codigo_mfa(g_user, g_pass)
        if codigo:
            # Aguarda o campo do código MFA aparecer
            campo_mfa = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input.mantine-Input-input")))
            campo_mfa.send_keys(codigo)
            
            btn_confirmar = driver.find_element(By.XPATH, "//button")
            driver.execute_script("arguments[0].click();", btn_confirmar)
            time.sleep(5)
            
        # --- EXTRAÇÃO DO CHECKLIST ---
        # Aqui simulamos a navegação. No site real, você precisaria clicar no navio.
        # Por enquanto, retornamos um dicionário padrão para testar a comunicação com o app.py
        resultado = {
            "Pre-arrival": "FEITO",
            "Arrival": "PENDENTE",
            "Berthing": "PENDENTE",
            "Unberthing": "PENDENTE"
        }
        
        return resultado

    except Exception as e:
        return {"Erro": f"Falha na automação: {str(e)}"}
    finally:
        driver.quit()

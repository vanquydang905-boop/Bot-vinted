from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options
import time
import os

options = Options()
options.debugger_address = "127.0.0.1:44231"

try:
    # Disable SSL verification for webdriver_manager if needed
    os.environ['WDM_SSL_VERIFY'] = '0'
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    print("Selenium connecté!")
    
    # Ouvrir Drive
    driver.switch_to.new_window('tab')
    driver.get("https://drive.google.com")
    time.sleep(2)
    print("Nouvel onglet Drive ouvert:", driver.current_url)
    
except Exception as e:
    print("Erreur Selenium:", e)

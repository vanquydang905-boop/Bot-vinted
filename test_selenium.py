from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import time

options = Options()
options.debugger_address = "127.0.0.1:44231"

try:
    driver = webdriver.Chrome(options=options)
    print("Selenium connecté!")
    print("Pages ouvertes :", len(driver.window_handles))
    
    # Ouvrir un nouvel onglet
    driver.switch_to.new_window('tab')
    driver.get("https://drive.google.com")
    time.sleep(2)
    print("Nouvel onglet Drive ouvert:", driver.current_url)
    
except Exception as e:
    print("Erreur Selenium:", e)

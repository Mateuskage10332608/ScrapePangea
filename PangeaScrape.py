# pangea_scrape.py
# Coleta todos os precedentes do Pangea (BNP) em Excel.
# Requer: selenium, webdriver-manager, pandas

import argparse, re, time
from typing import Dict, List
import pandas as pd

from shutil import which
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException, StaleElementReferenceException

# ---------- util ----------

def wait_clickable(wait: WebDriverWait, by: By, sel: str):
    return wait.until(EC.element_to_be_clickable((by, sel)))

def js_click(driver, el):
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
    time.sleep(0.1)
    try:
        el.click()
    except Exception:
        driver.execute_script("arguments[0].click();", el)

def get_cards(driver):
    # cartões dos resultados (layout real do site)
    cards = driver.find_elements(By.CSS_SELECTOR, "app-resultados > div.card.card-body")
    if not cards:
        # fallback genérico
        cards = driver.find_elements(By.CSS_SELECTOR, "div.card.card-body")
    return cards

def page_label_text(driver) -> str:
    # texto "X de N" da paginação
    try:
        span = driver.find_element(
            By.XPATH,
            "//ngb-pagination//ul[contains(@class,'pagination')]"
            "/*[contains(@class,'ngb-custom-pages-item')]//span"
        )
        return span.text.strip()
    except NoSuchElementException:
        return ""

def current_page(driver) -> int:
    txt = page_label_text(driver)
    m = re.search(r"(\d+)\s+de\s+\d+", txt)
    return int(m.group(1)) if m else 1

def total_pages(driver) -> int:
    txt = page_label_text(driver)
    m = re.search(r"\d+\s+de\s+(\d+)", txt)
    return int(m.group(1)) if m else 1

def next_li(driver):
    # LI do botão Next
    return driver.find_element(
        By.XPATH,
        "//ngb-pagination//ul[contains(@class,'pagination')]/li[a[@aria-label='Next']]"
    )

def next_disabled(li) -> bool:
    cls = li.get_attribute("class") or ""
    return "disabled" in cls

def extract_card_data(card) -> Dict[str, str]:
    txt = card.text.strip()
    lines = [l.strip() for l in txt.split("\n") if l.strip()]
    court = lines[0] if lines else ""
    title = lines[1] if len(lines) > 1 else ""
    last_update = ""
    for l in lines:
        if "Última Atualização" in l:
            parts = l.split(":")
            if len(parts) >= 2:
                last_update = parts[1].strip()
            break

    body = "\n".join(lines[2:]) if len(lines) > 2 else ""

    def sec(h):
        i = body.lower().find(h.lower() + ":")
        if i == -1: return ""
        after = body[i + len(h) + 1:].strip()
        for other in ["Questão", "Tese", "Situação"]:
            if other.lower() != h.lower():
                j = after.lower().find(other.lower() + ":")
                if j != -1: return after[:j].strip()
        return after.strip()

    return {
        "court": court,
        "title": title,
        "question": sec("Questão"),
        "thesis": sec("Tese"),
        "situation": sec("Situação"),
        "last_update": last_update,
    }

# ---------- main scrape ----------

def scrape(output_file: str, headed: bool = False):
    opts = webdriver.ChromeOptions()
    if not headed:
        opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")

    svc = Service(which("chromedriver") or ChromeDriverManager().install())
    driver = webdriver.Chrome(service=svc, options=opts)
    wait = WebDriverWait(driver, 25)

    results: List[Dict[str, str]] = []
    try:
        driver.get("https://pangeabnp.pdpj.jus.br/pesquisa")

        # dispara busca (enter no campo; o botão varia entre builds)
        try:
            campo = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='text']")))
            campo.send_keys("\n")
        except TimeoutException:
            pass

        # espera primeiro card aparecer
        wait.until(lambda d: len(get_cards(d)) > 0)

        # define 100 por página (aria-label real)
        try:
            sel = wait_clickable(
                wait, By.CSS_SELECTOR,
                "select[aria-label='Selecione o número de resultados por página']"
            )
            Select(sel).select_by_value("100")
            # aguarda recarregar a página 1 com 100 itens
            wait.until(lambda d: len(get_cards(d)) > 0)
            time.sleep(0.4)
        except TimeoutException:
            # segue com o que tiver
            pass

        # páginas
        pg = current_page(driver)
        total = total_pages(driver)
        print(f"[página {pg} de {total}] iniciando…")

        while True:
            # coleta todos os cartões visíveis desta página
            cards = get_cards(driver)
            for c in cards:
                try:
                    results.append(extract_card_data(c))
                except StaleElementReferenceException:
                    # se o Angular re-renderizou, refaz o find desse card
                    pass

            print(f"[página {pg}] coletados {len(results)} no total")

            # tenta avançar
            try:
                li = next_li(driver)
            except NoSuchElementException:
                break
            if next_disabled(li):
                break

            a = li.find_element(By.TAG_NAME, "a")
            old_pg = pg
            js_click(driver, a)

            # espera número da página mudar
            try:
                wait.until(lambda d: current_page(d) > old_pg)
            except TimeoutException:
                # tenta clicar com JS de novo e aguarda um pouco
                js_click(driver, a)
                time.sleep(0.6)
                if current_page(driver) <= old_pg:
                    # não avançou: encerra para não loopar
                    break

            # garante que a nova página tem cartões
            wait.until(lambda d: len(get_cards(d)) > 0)
            pg = current_page(driver)

        # exporta
        df = pd.DataFrame(results)
        df.to_excel(output_file, index=False)
        print(f"OK: {len(results)} registros salvos em {output_file}")

    finally:
        driver.quit()

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", default="pangea_results.xlsx")
    ap.add_argument("--headed", action="store_true", help="Exibir o navegador")
    args = ap.parse_args()
    scrape(args.output, headed=args.headed)

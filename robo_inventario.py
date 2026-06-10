# ====================================================================================
# SCRIPT DE AUTOMAÇÃO (v53 - Versão Automática para Agendador)
# ====================================================================================

# --- 1. IMPORTAÇÃO DAS BIBLIOTECAS ---
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.common.exceptions import TimeoutException, StaleElementReferenceException
from webdriver_manager.chrome import ChromeDriverManager
import pandas as pd
from io import StringIO
from datetime import datetime
import time
import re
import os
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore

print(">>> INICIANDO SCRIPT DE AUTOMAÇÃO (MODO CLOUD/FIREBASE) <<<")

# Função de limpeza de números
def limpar_valor_numerico(valor):
    try:
        valor_str = str(valor).strip()
        if 'R$' in valor_str:
            valor_str = valor_str.replace('R$', '').strip()
        if ',' in valor_str and valor_str.find(',') > valor_str.find('.'):
            valor_str = valor_str.replace('.', '').replace(',', '.')
        else:
            valor_str = valor_str.replace(',', '')
        return float(valor_str)
    except (ValueError, TypeError):
        return 0.0

navegador = None
try:
    URL_PRINCIPAL = 'https://sipac.rn.gov.br/sipac/portal/principal.jsf'

    # --- 2. CONFIGURAÇÃO E LOGIN ---
   print("Configurando o navegador...")

    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_argument('--headless=new')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--window-size=1920,1080')
    chrome_options.add_argument('--disable-extensions')
    chrome_options.add_argument('--blink-settings=imagesEnabled=false')
    chrome_options.add_argument('--disable-blink-features=AutomationControlled')  # <- esconde que é bot
    chrome_options.add_argument('--disable-infobars')
    chrome_options.add_argument('--ignore-certificate-errors')                    # <- ignora erros SSL
    chrome_options.add_argument('--allow-running-insecure-content')
    chrome_options.add_argument('--disable-web-security')
    chrome_options.add_experimental_option('excludeSwitches', ['enable-automation'])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36")

    print("Baixando ChromeDriver compatível...")
    servico = ChromeService(ChromeDriverManager().install())
    navegador = webdriver.Chrome(service=servico, options=chrome_options)
    
    # Esconde propriedades que identificam o Selenium
    navegador.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
        'source': "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    })
    
    navegador.set_page_load_timeout(120)
    navegador.implicitly_wait(20)
    wait = WebDriverWait(navegador, 60)

    print("Acessando a página de login...")
    navegador.get('https://sipac.rn.gov.br/sipac/?modo=classico')

    usuario = os.environ.get('SIPAC_USER')
    senha = os.environ.get('SIPAC_PASSWORD')

    if not usuario or not senha:
        raise ValueError("ERRO: Variáveis de ambiente SIPAC_USER ou SIPAC_PASSWORD não configuradas.")

    print("Credenciais obtidas das variáveis de ambiente.")

    xpath_usuario = '//*[@id="conteudo"]/div[3]/form/table/tbody/tr[1]/td/input'
    xpath_senha = '//*[@id="conteudo"]/div[3]/form/table/tbody/tr[2]/td/input'
    xpath_acessar = '//*[@id="conteudo"]/div[3]/form/table/tfoot/tr/td/input'

    print("Iniciando login...")
    campo_usuario_element = wait.until(EC.presence_of_element_located((By.XPATH, xpath_usuario)))
    campo_usuario_element.send_keys(usuario)

    campo_senha_element = wait.until(EC.presence_of_element_located((By.XPATH, xpath_senha)))
    campo_senha_element.send_keys(senha)

    navegador.find_element(By.XPATH, xpath_acessar).click()
    print("Login realizado com sucesso!")
    time.sleep(2)

    def click_insistente(xpath_do_elemento, tentativas=3):
        for tentativa in range(tentativas):
            try:
                elemento = wait.until(EC.element_to_be_clickable((By.XPATH, xpath_do_elemento)))
                navegador.execute_script("arguments[0].scrollIntoView({block: 'center', inline: 'center'});", elemento)
                time.sleep(0.5)
                elemento.click()
                return
            except StaleElementReferenceException:
                print(f"  - Elemento 'velho' detectado. Tentando novamente...")
                time.sleep(1)
        raise Exception(f"Erro ao clicar no elemento: {xpath_do_elemento}")

    # --- 3. DEFINIÇÃO DOS CAMINHOS E PREPARAÇÃO DO LOOP ---
    xpath_abrir_selecao_unidade = '//*[@id="info-usuario"]/p[3]/a/img'
    xpath_caixa_selecao_unidade = '//*[@id="conteudo"]/form/table/tbody/tr/td[2]/select'
    xpath_botao_voltar_do_relatorio = '//*[@id="relatorio-rodape"]/p/table/tbody/tr/td[1]/a'

    print("Iniciando a busca por unidades...")
    click_insistente(xpath_abrir_selecao_unidade)
    caixa_selecao_element = wait.until(EC.presence_of_element_located((By.XPATH, xpath_caixa_selecao_unidade)))
    select_object = Select(caixa_selecao_element)
    nomes_das_unidades = [option.text for option in select_object.options]
    print(f"Encontradas {len(nomes_das_unidades)} unidades no total.")
    dados_por_unidade = {}
    total_a_processar = len(nomes_das_unidades)

    # --- INÍCIO DO LOOP PRINCIPAL ---
    for i in range(total_a_processar):
        unidade_atual = nomes_das_unidades[i]

        if "SUBSECRETARIA" in unidade_atual.upper():
            print(f">>> IGNORANDO UNIDADE DUPLICADA: {unidade_atual} <<<")
            continue

        try:
            print("-" * 30)
            print(f"Processando: {unidade_atual}")

            caixa_selecao_element = wait.until(EC.presence_of_element_located((By.XPATH, xpath_caixa_selecao_unidade)))
            select_object = Select(caixa_selecao_element)
            select_object.select_by_index(i)

            xpath_botao_alterar_unidade = '//*[@id="conteudo"]/form/table/tfoot/tr/td/input[2]'
            navegador.find_element(By.XPATH, xpath_botao_alterar_unidade).click()

            xpath_menu_modulos = '//*[@id="show-modulos-sipac"]'
            xpath_modulo_almoxarifado = '//*[@id="modulos"]/ul[1]/li[3]/a'
            xpath_menu_consultas = '//*[@id="elgen-14"]'
            xpath_relatorio_inventario = '//*[@id="relatorios-menualmoxarifado"]/ul/li[2]/ul/li[5]/a'
            click_insistente(xpath_menu_modulos)
            click_insistente(xpath_modulo_almoxarifado)
            click_insistente(xpath_menu_consultas)
            click_insistente(xpath_relatorio_inventario)

            xpath_gerar_relatorio = '//*[@id="conteudo"]/form/table[2]/tfoot/tr/td/input[1]'
            click_insistente(xpath_gerar_relatorio)

            df_final = None
            try:
                wait_curto = WebDriverWait(navegador, 10)
                xpath_tabela_de_dados = "//table[.//th[contains(text(), 'Código')]]"
                tabela_element = wait_curto.until(EC.presence_of_element_located((By.XPATH, xpath_tabela_de_dados)))

                html_da_tabela_correta = tabela_element.get_attribute('outerHTML')
                df_bruto = pd.read_html(StringIO(html_da_tabela_correta), header=0)[0]

                df_bruto.dropna(subset=['Código'], inplace=True)
                colunas_desejadas = ['Código', 'Denominação', 'Unid. Medida', 'Saldo', 'Preço*', 'Total']
                df_final = df_bruto[colunas_desejadas].copy()

                df_final['Saldo'] = df_final['Saldo'].apply(limpar_valor_numerico)
                df_final['Preço*'] = df_final['Preço*'].apply(limpar_valor_numerico)
                df_final['Total'] = df_final['Total'].apply(limpar_valor_numerico)

            except TimeoutException:
                print("Relatório vazio. Criando zerado.")
                dados_vazios = {'Código': [0], 'Denominação': ['SEM MATERIAL'], 'Unid. Medida': ['-'], 'Saldo': [0.0], 'Preço*': [0.0], 'Total': [0.0]}
                df_final = pd.DataFrame(dados_vazios)

            if df_final is not None:
                dados_por_unidade[unidade_atual] = df_final

            click_insistente(xpath_botao_voltar_do_relatorio)
            click_insistente(xpath_abrir_selecao_unidade)
            time.sleep(1)

        except Exception as loop_error:
            print(f"Erro na unidade: {loop_error}. Tentando recuperar...")
            try:
                navegador.get(URL_PRINCIPAL)
                time.sleep(3)
                click_insistente(xpath_abrir_selecao_unidade)
            except Exception:
                break
            continue

    # --- 5. SALVANDO OS DADOS NO FIREBASE ---
    if dados_por_unidade:
        print("Consolidando dados...")
        lista_de_dfs = []
        for nome_unidade, df in dados_por_unidade.items():
            nome_coluna_limpo = re.sub(r'[\(\)]', '', nome_unidade).strip()
            df['Unidade'] = nome_coluna_limpo
            lista_de_dfs.append(df)

        df_completo = pd.concat(lista_de_dfs, ignore_index=True)
        registros = df_completo.to_dict(orient='records')

        print("Conectando ao Firebase Firestore...")
        cred = credentials.Certificate('firebase_key.json')
        if not firebase_admin._apps:
            firebase_admin.initialize_app(cred)

        db = firestore.client()
        print(f"Enviando {len(registros)} registros para o Firebase...")

        batch = db.batch()
        colecao_ref = db.collection('inventario')

        contador = 0
        for item in registros:
            doc_id = f"{item['Código']}_{item['Unidade']}".replace(" ", "_").replace("/", "-")
            doc_ref = colecao_ref.document(str(doc_id))
            item['ultima_atualizacao'] = datetime.now().isoformat()
            batch.set(doc_ref, item, merge=True)
            contador += 1

            if contador % 400 == 0:
                batch.commit()
                batch = db.batch()

        if contador % 400 != 0:
            batch.commit()

        print(f"\n>>> SUCESSO! {contador} itens salvos/atualizados no Firebase! <<<")

except Exception as e:
    print(f"\n>>> OCORREU UM ERRO: {e} <<<")

finally:
    if navegador:
        navegador.quit()

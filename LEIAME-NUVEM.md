# Sistema LTCAT — versão nuvem (simples)

Cópia do Sistema LTCAT preparada para rodar na internet (Streamlit Cloud).
O app original no OneDrive continua intacto — nada nele mudou.

## Como funciona
- **Sem banco de dados.** Você abre o app, preenche o laudo e **baixa o PDF**.
- **Empresas e signatário** já vêm embutidos (pasta `dados\`, versionada no
  GitHub) para não precisar redigitar toda vez. Se editar na nuvem, a mudança
  vale só durante aquela sessão (não fica salva — o app é "sem memória").
- **Laudos** não são guardados: cria → gera PDF → baixa no computador.
- **Sem chave da Anthropic:** os botões de IA ficam desabilitados; todo o resto
  (criar/editar laudo, gerar PDF, empresas, signatário) funciona.

## Passo a passo para publicar

### 1. Subir o código no GitHub
1. https://github.com → **New repository** (pode ser privado). Ex.: `ltcat-vmp`.
2. Suba **todos os arquivos desta pasta**. A pasta `dados\laudos` e `dados\saida`
   são ignoradas pelo `.gitignore` (tudo bem). Precisam ir:
   `app.py`, `engine.py`, `extractor.py`, `leitura_local.py`, `montador.py`,
   `store.py`, `requirements.txt`, a pasta `imagens\` (logos) e
   `dados\empresas\*.json` + `dados\signatario.json`.

### 2. Publicar no Streamlit Cloud
1. https://share.streamlit.io → **New app** → escolha o repositório.
2. **Main file path:** `app.py` → **Deploy**.
3. Em 1–2 min fica no ar num link `https://....streamlit.app`.

### 3. Ligar o botão no SMA System
No `index.html`, trocar a constante:
```
var LTCAT_URL='https://SEU-APP.streamlit.app';
```
Pronto — o botão "🔗 Sistema LTCAT" abre de qualquer lugar.

## Observação
Como não há login, qualquer pessoa com o link acessa o app. Como ele não guarda
dados (só gera PDF na hora), o risco é baixo, mas se quiser dá para colocar uma
senha simples depois.

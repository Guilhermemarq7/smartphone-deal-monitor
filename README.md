# Radar de Smartphones — 10/10 + GitHub Actions + Telegram

Monitor de preços de smartphones no Brasil com histórico próprio em SQLite, detecção de falso desconto, score de oportunidade, descoberta de modelos fora da lista e alertas automáticos por Telegram.

Esta versão foi preparada para dois modos:

1. **Local/Windows** — `python main.py` ou `python main.py --watch`.
2. **Cloud grátis com GitHub Actions** — o GitHub acorda periodicamente, restaura o SQLite, executa uma coleta, envia Telegram se necessário, salva o histórico novamente e encerra.

## O que já vem configurado

- Galaxy S25 FE 256 GB
- Galaxy S25 256 GB
- Motorola Edge 70 Pro 256 GB
- Motorola Edge 60 Pro 512 GB
- Xiaomi 15T 256 GB
- POCO F7 512 GB
- iPhone 15 128 GB
- Galaxy S26 256 GB
- Galaxy S24 Ultra 256 GB
- iPhone 16 128 GB

A pesquisa inicial está em `data/bootstrap/radar_celulares_10-10_2026.md` e serve apenas de bootstrap. O peso real passa progressivamente para o histórico coletado pelo próprio programa.

## Fontes implementadas

- Mercado Livre API, com fallback para busca pública HTML quando necessário.
- Magalu via busca pública.
- Páginas oficiais Samsung/Motorola configuradas em `config.yaml`.

Nenhuma fonte inexistente é simulada. Quando uma fonte falha, as demais continuam.

---

# PARTE A — Usar localmente no Windows

## 1. Requisitos

- Windows 10/11
- Python 3.11+ (recomendado 3.13)
- Internet

Não é necessário Chrome, Selenium, Playwright, Node, Docker ou banco externo.

## 2. Extrair o ZIP e abrir PowerShell na pasta

Depois de extrair, entre na pasta que contém `main.py`.

## 3. Criar ambiente virtual

```powershell
python -m venv .venv
.venv\Scripts\activate
```

## 4. Instalar dependências

```powershell
python -m pip install -r requirements.txt
```

## 5. Validar

```powershell
python main.py --validate
pytest -q
```

## 6. Rodar uma vez

```powershell
python main.py
```

## 7. Rodar continuamente no PC

```powershell
python main.py --watch
```

Ou a cada 10 minutos:

```powershell
python main.py --watch --interval-minutes 10
```

---

# PARTE B — Criar o bot do Telegram

Você **não precisa criar grupo**. O bot pode mandar as mensagens direto na conversa privada com você.

## 1. Criar o bot

1. Abra o Telegram.
2. Pesquise por `@BotFather` e confirme que é o BotFather oficial.
3. Envie `/newbot`.
4. Escolha um nome, por exemplo `Radar Celulares`.
5. Escolha um username terminando em `bot`, por exemplo `meu_radar_celulares_bot`.
6. O BotFather entregará um token parecido com `123456789:AA...`.
7. **Trate esse token como senha. Não envie para outras pessoas e não publique no GitHub.**

## 2. Criar `.env` local

No PowerShell, dentro do projeto:

```powershell
copy .env.example .env
```

Abra `.env` e coloque somente o token:

```env
TELEGRAM_BOT_TOKEN=COLE_AQUI_O_TOKEN_DO_BOTFATHER
TELEGRAM_CHAT_ID=
```

## 3. Iniciar conversa com seu bot

1. No Telegram, abra o bot que você acabou de criar.
2. Toque em **Start/Iniciar** ou envie `/start`.
3. Volte ao PowerShell logo depois.

## 4. Descobrir o CHAT_ID automaticamente

Com o ambiente virtual ativo:

```powershell
python tools/telegram_setup.py
```

O script:

- valida o token;
- identifica o bot;
- procura a conversa privada mais recente;
- mostra seu `CHAT_ID`;
- grava `TELEGRAM_CHAT_ID` no `.env` local;
- envia uma mensagem de teste.

Se você receber a mensagem `Radar de celulares conectado ao Telegram`, a integração local está pronta.

Para testar novamente:

```powershell
python tools/telegram_test.py
```

---

# PARTE C — Colocar no GitHub Actions

## 1. Criar uma conta/repositório

Entre no GitHub e crie um repositório novo, por exemplo:

`smartphone-deal-monitor`

### Público ou privado?

- **Público:** runners padrão do GitHub Actions não consomem minutos pagos. Não coloque segredos no código; eles ficarão em GitHub Secrets.
- **Privado:** funciona também, mas usa a cota mensal de minutos do seu plano GitHub.

Para garantir custo zero de execução, o caminho mais simples é um repositório público **desde que você esteja confortável em deixar apenas o código/configuração públicos**. Seus tokens não entram no repositório.

## 2. Subir o projeto

Você pode usar a interface web do GitHub ou Git. Pela interface web:

1. Abra o repositório.
2. Clique em **Add file** > **Upload files**.
3. Envie o conteúdo da pasta do projeto mantendo a estrutura, inclusive a pasta `.github/workflows/`.
4. Faça o commit.

Não envie `.env`, `data/radar.db`, logs nem arquivos gerados. O `.gitignore` já protege esses arquivos quando você usa Git.

## 3. Criar os GitHub Secrets

No repositório:

1. Abra **Settings**.
2. Entre em **Secrets and variables**.
3. Clique em **Actions**.
4. Clique em **New repository secret**.

Crie exatamente estes dois secrets:

### Secret 1

Nome:

`TELEGRAM_BOT_TOKEN`

Valor: o token fornecido pelo BotFather.

### Secret 2

Nome:

`TELEGRAM_CHAT_ID`

Valor: o número mostrado por `python tools/telegram_setup.py`.

### Opcional — Mercado Livre

Se futuramente você tiver um token oficial do Mercado Livre, pode criar também:

`ML_ACCESS_TOKEN`

O monitor não depende obrigatoriamente dele porque possui fallback público.

## 4. Confirmar que Actions está habilitado

1. Abra a aba **Actions** do repositório.
2. Localize o workflow **Radar de celulares**.
3. Se o GitHub pedir para habilitar workflows, habilite.

O arquivo responsável é:

`.github/workflows/radar.yml`

## 5. Fazer o primeiro teste manual

Na aba **Actions**:

1. Clique em **Radar de celulares**.
2. Clique em **Run workflow**.
3. Marque `Enviar mensagem de teste do Telegram antes da coleta`.
4. Clique em **Run workflow**.
5. Abra a execução que aparecer.

A ordem deverá ser aproximadamente:

- Baixar projeto
- Configurar Python
- Restaurar histórico SQLite
- Instalar dependências
- Validar configuração cloud
- Testar Telegram
- Executar radar
- Mostrar relatório

Você deverá receber no Telegram uma mensagem de teste. Se o radar encontrar uma oferta que cumpra as regras, receberá também o alerta da oferta.

## 6. Agendamento automático já configurado

O workflow já vem configurado em horário `America/Sao_Paulo`.

### Dias normais

Executa aproximadamente a cada 30 minutos, nos minutos `07` e `37`.

### No dia 10 de outubro

Executa a cada 10 minutos.

Não é necessário deixar seu computador ligado.

> GitHub Actions não garante execução no segundo exato do cron; um job agendado pode atrasar em momentos de alta carga.

---

# PARTE D — Como o histórico sobrevive no GitHub Actions

Cada execução do GitHub usa uma máquina temporária. Para não perder o SQLite, o workflow usa o cache do GitHub Actions.

Fluxo:

```text
GitHub inicia runner
        ↓
restaura data/radar.db mais recente
        ↓
executa coleta
        ↓
calcula score usando histórico anterior
        ↓
grava novas observações
        ↓
envia alertas
        ↓
fecha/checkpoint do SQLite
        ↓
GitHub salva novo cache
        ↓
runner é destruído
```

A chave de cache é nova a cada execução e `restore-keys` recupera o estado mais recente disponível.

O cache é uma conveniência de persistência, não um banco gerenciado com garantia de durabilidade infinita. Se ele desaparecer, o programa continua funcionando e volta a usar o bootstrap do Markdown, mas perde o histórico próprio acumulado até então.

Para manter o arquivo pequeno e evitar crescimento indefinido, observações próprias antigas são podadas por padrão após 120 dias; runs e fingerprints de alerta usam retenções menores. Esses valores ficam em `config.yaml`.

---

# PARTE E — Deduplicação dos alertas

O Telegram não dispara a mesma oferta a cada 30 minutos.

O fingerprint leva em conta, entre outros:

- modelo;
- loja;
- seller;
- URL;
- preço;
- cashback;
- cupom;
- classificação;
- condições especiais.

Exemplo:

```text
10:00  S25 = R$ 3.099  → envia
10:30  S25 = R$ 3.099  → não envia
11:00  S25 = R$ 3.099  → não envia
11:30  S25 = R$ 2.949  → envia novamente
```

Por padrão, a mesma condição exata pode voltar a ser avisada depois de 24 horas. Ajuste em `config.yaml`:

```yaml
alerts:
  repeat_after_hours: 24
```

---

# PARTE F — Outliers suspeitos

Preços extremamente baixos são tratados de forma diferente.

Se um preço cair abaixo de aproximadamente 60% da mediana, o score é limitado e a classificação vira:

`OUTLIER — VERIFICAR`

Entretanto, nesta versão cloud, o outlier **pode disparar Telegram mesmo com o score capado**, para que uma possível promoção absurda não passe despercebida.

Isso é controlado por:

```yaml
alerts:
  alert_outliers: true
```

O alerta pede para conferir:

- variante;
- vendedor;
- condição;
- cupom;
- erro de preço;
- troca obrigatória;
- pagamento especial.

---

# PARTE G — Alterar o nível de alerta

Em `config.yaml`:

```yaml
alerts:
  min_score: 76
```

Quanto menor, mais mensagens. Quanto maior, mais seletivo.

Os thresholds individuais ficam em cada aparelho:

```yaml
alert_below: 3350
strong_buy_below: 3200
dream_price: 3000
```

---

# PARTE H — Segurança

Nunca faça commit de:

- `.env`
- token do Telegram
- senha
- cookie pessoal
- token do Mercado Livre

No GitHub, use sempre **Secrets and variables > Actions**.

Se o token do Telegram vazar, abra o BotFather e revogue/gere um novo token.

---

# PARTE I — Arquivos importantes

```text
main.py
config.yaml
.env.example
requirements.txt
.github/workflows/radar.yml
src/
tools/telegram_setup.py
tools/telegram_test.py
tools/cloud_preflight.py
data/bootstrap/
tests/
```

Saídas locais:

```text
data/radar.db
output/latest_prices.csv
output/best_deals.csv
output/report.md
logs/radar.log
logs/opportunities.log
```

---

# PARTE J — Testes

Execute:

```powershell
pytest -q
```

Os testes cobrem parsing, armazenamento GB/TB, filtros, score, outlier, bootstrap, parser de loja e deduplicação de alertas.

---

# PARTE K — Troubleshooting rápido

## `telegram_setup.py` não encontra conversa

Abra o bot, mande `/start` de novo e imediatamente rode:

```powershell
python tools/telegram_setup.py
```

## GitHub Action mostra falta de secret

Confira os nomes exatos:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

## Não chegou alerta, mas workflow ficou verde

Pode simplesmente não ter aparecido nenhuma oferta acima do `min_score`. Abra o resumo da execução em **Actions** e veja `report.md`.

## Mesma oferta não é reenviada

É intencional. A deduplicação padrão é de 24 horas.

## O banco começou do zero

Provavelmente o cache de estado não estava disponível. O programa recria o banco e usa a pesquisa inicial como bootstrap.

## Repositório público ficou muito tempo parado

GitHub pode desabilitar workflows agendados em repositórios públicos após um longo período sem atividade no repositório. Se isso acontecer, abra **Actions** e reabilite o workflow ou faça uma atualização normal no repositório.

---

# Resumo do funcionamento cloud

```text
GitHub Actions
      ↓
restaura histórico SQLite
      ↓
Mercado Livre / Magalu / páginas oficiais
      ↓
normalização + filtros
      ↓
histórico + mediana + mínimo
      ↓
score / falso desconto / outlier
      ↓
passou regra de alerta?
      ↓ SIM
fingerprint já avisado recentemente?
      ↓ NÃO
Telegram
```

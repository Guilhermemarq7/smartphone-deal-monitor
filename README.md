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

- Mercado Livre API: usa `ML_ACCESS_TOKEN`; acesso atual ao endpoint precisa ser validado com o aplicativo autorizado. Sem token, a fonte é ignorada sem requisições. HTML é opt-in apenas local.
- Magalu: busca pública opcional local; desabilitada por padrão no cloud após 403 relatado no Actions.
- Páginas oficiais Samsung/Motorola configuradas em `config.yaml`: somente preço estruturado com variante/capacidade comprovadas.
- Catálogos públicos VTEX de Fast Shop e Motorola: nova integração com preços/estoque por SKU, validada neste cloud.
- Extensão para outras páginas estruturadas: disponível, desabilitada e vazia até validação live de cada loja.

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

O radar como um todo não depende dele, mas a fonte Mercado Livre API exige `ML_ACCESS_TOKEN`. O fallback público é somente opt-in local e não é executado em GitHub Actions. Um token não garante permissão para busca; veja a auditoria e a documentação oficial antes de assumir que um HTTP 403 será resolvido.

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


# Coleta cloud, saúde e validação

A auditoria e as evidências estão em [docs/collector-audit.md](docs/collector-audit.md).
Após um bloqueio inicial do proxy, a coleta live passou a funcionar neste cloud:
Samsung e os catálogos públicos VTEX de Fast Shop/Motorola foram acessados. A
documentação oficial VTEX confirma endpoint, filtros e limites usados. Mercado
Livre e sua documentação continuaram retornando HTTP 403: não foi possível
certificar a API de busca vigente em outubro de 2026 nem testar acesso autorizado.
A disponibilidade neste cloud ainda precisa ser confirmada no runner Actions.

| Fonte | Cloud | Local | Credenciais / evidência |
| --- | --- | --- | --- |
| Mercado Livre API | Tentativa autenticada habilitada | Tentativa autenticada | ML_ACCESS_TOKEN; endpoint existente, acesso atual não confirmado |
| Mercado Livre HTML | Desabilitado sempre | Opt-in `public_web_fallback: true` | Sem credenciais; disponibilidade não confirmada |
| Magalu HTML | Desabilitado por padrão | Opcional, sem preço validado | HTTP 200 aqui com zero ofertas no parser; 403 no runner relatado pelo usuário |
| Samsung/Motorola HTML | Habilitadas | Habilitadas | Sem credenciais; variante, capacidade e preço estruturado exigidos; Samsung testado live |
| Fast Shop/Motorola catálogo público VTEX | Habilitados | Habilitados | Sem credenciais nos hosts verificados; estoques/preços por SKU; testes live e mocks |
| Outras páginas estruturadas | Desabilitadas/vazias | Desabilitadas/vazias | Habilitar somente depois de validar loja e produto reais |

## Modo cloud versus local

`GITHUB_ACTIONS=true` ativa o modo cloud automaticamente. Fora do Actions, use
`--cloud` para reproduzir a seleção das fontes. Cada fonte usa `enabled` e
`cloud_enabled`; Magalu tem `cloud_enabled: false`. Recusas 401/403/429 e falhas
de proxy encerram as consultas daquela fonte na execução, incluindo discovery,
em vez de repetir a recusa por aparelho. A próxima execução tenta novamente.
Não há CAPTCHA bypass, cookies pessoais, proxies rotativos, spoofing ou navegador.

Somente ofertas novas confirmadas entram no histórico quando `new_only: true`.
Variante, capacidade, moeda e vínculo entre produto e preço precisam ser
comprovados. Preço riscado não determina desconto real; parcelas, cashback,
cupom não confirmado e condições de troca/cartão/assinatura não são tratados
como preço direto garantido. O preço atual continua sendo avaliado **antes**
de entrar no histórico que determina sua mediana. Frete ausente permanece
desconhecido; confira o custo final no checkout.

## Catálogos públicos VTEX

A integração nova usa a [Legacy Search API documentada](https://developers.vtex.com/docs/api-reference/search-api)
em hosts públicos que responderam sem autenticação. Não usa a API privada de
catálogo ou alterações de carrinho/checkout. Cada busca tem no máximo 50 produtos,
com atraso de 1,5 s, timeout e retries limitados; não varre o catálogo inteiro.
Na Fast Shop, a categoria de celulares evita acessórios e a lista aceita somente
sellers observados: Fast Shop, Ponto e Casas Bahia. Outros sellers são rejeitados.
A saúde conta o canal Fast Shop uma vez, com o seller separado em cada oferta.
Condição nova é a premissa do catálogo varejista desses sellers; usados/vitrine/
recondicionados detectados são rejeitados, e confirme a condição no checkout.

`Price`, `ListPrice` e preço Pix são separados. Pix vem do total de pagamento
único explicitamente associado ao sistema Pix público sem autenticação ou BIN,
em centavos; parcelas de cartão, cashback e Teasers não viram desconto direto.
Estoque indisponível e preço expirado não produzem oferta. Motorola usa essa API
para Edge 70 Pro/Edge 60 Pro e uma consulta limitada de discovery. Não há novo secret.

## Mercado Livre e OAuth

Use uma aplicação autorizada na plataforma oficial do Mercado Livre e o fluxo
OAuth indicado na documentação de [autenticação e autorização](https://developers.mercadolivre.com.br/pt_br/autenticacao-e-autorizacao).
O titular da conta autoriza a aplicação; o código de autorização é trocado por
access token segundo a documentação. Mantenha client secret e refresh token fora
do repositório. Este projeto **não implementa renovação automática**: tokens
expirados ou sem permissão deixam a fonte indisponível. Antes de automatizar,
confirme o acesso de busca na documentação de
[itens e buscas](https://developers.mercadolivre.com.br/pt_br/itens-e-buscas).
Estas páginas não puderam ser lidas neste ambiente, portanto o procedimento e a
permissão exatos atuais ainda precisam ser conferidos, sem assumir acesso global.

No GitHub, configure o access token em **Settings > Secrets and variables >
Actions**, nome `ML_ACCESS_TOKEN`. O workflow já injeta esse secret. Localmente,
use essa variável de ambiente ou `.env` ignorado pelo Git. Não cole valores em
issues, logs, PRs ou no código. Os secrets existentes do Telegram não precisam
ser alterados para os alertas operacionais.

## Interpretar a saúde

- **HEALTHY**: duas ou mais lojas, pelo menos 50% da lista com preços válidos e
  nenhuma falha inesperada de fonte.
- **DEGRADED**: pelo menos dois modelos com preço, mas cobertura insuficiente
  ou falha parcial. Uma loja apenas continua DEGRADED.
- **CRITICAL**: nenhuma oferta válida ou menos de dois modelos com preço
  (o mínimo é limitado ao tamanho da lista monitorada).
- **OFFLINE**: execução sem rede; nenhuma conclusão sobre saúde live.

Ajuste os limiares na seção `health` do `config.yaml`. Contamos lojas e variantes
**depois dos filtros**, sem usar bootstrap ou discovery como cobertura da lista.
`output/report.md`, o terminal e `output/health.json` mostram a classificação.
Ausência de promoções em CRITICAL não significa que não haja ofertas nas lojas.

O workflow usa `--fail-on-critical`: CRITICAL gera relatórios e retorna código 2,
com Job Summary e gravação do cache SQLite executados mesmo nessa falha.
Uma fonte falhar isoladamente não derruba o job se ainda há cobertura útil.
O Telegram recebe um aviso **operacional**, separado de promoções, no máximo uma
vez a cada 24 horas em estado CRITICAL após entrega bem-sucedida. O cooldown fica
no SQLite restaurado pelo Actions, e uma falha de envio pode ser tentada novamente.
Sem credenciais Telegram, não existe entrega remota; OFFLINE não envia aviso.

## Testar localmente sem enviar mensagens

Linux/cloud, na raiz do projeto:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pytest -q
.venv/bin/python main.py --validate
.venv/bin/python main.py --offline --no-alerts
.venv/bin/python main.py --cloud --no-alerts --fail-on-critical
```

No Windows, use `python` com o ambiente virtual ativado. Os testes usam mocks,
uma fixture JSON-LD sintética e campos selecionados de uma resposta real VTEX;
não dependem da internet e não enviam Telegram.
A última execução acima acessa as fontes habilitadas: inspecione o relatório,
a cobertura e os preços reais, não apenas o código de saída. `--no-alerts`
impede tanto alertas de promoção quanto operacionais nesse teste controlado.

Para novas lojas, adicione URLs **reais verificadas** em
`sources.structured_pages.pages` com `store`, `url` e `target_id`, e só então
habilite `enabled`/`cloud_enabled`. Não use busca HTML protegida como uma API.
O parser aceita Product/Offer JSON-LD, grafos e variantes, rejeitando preço de
família (`AggregateOffer`), moeda diferente, estoque indisponível e preços
expirados/restritos detectáveis. Uma página sem capacidade comprovada ou somente
com texto monetário não produz oferta. Verifique condições de uso e estabilidade
da fonte antes de automatizar; a extensão por si só não aumenta a cobertura.

## Testar no GitHub Actions

Depois da revisão e merge manual deste PR, rode **Radar de celulares > Run
workflow**. O teste opcional Telegram existente permanece disponível. Confira:

1. Os testes passam no runner.
2. O Job Summary mostra saúde, lojas e variantes cobertas, e falhas/ignoradas.
3. CRITICAL deixa o job com falha; DEGRADED permanece visível no relatório.
4. O passo de persistência salva o SQLite mesmo em CRITICAL; a execução seguinte
   restaura histórico e cooldown.
5. Confira uma oferta diretamente na loja e confirme capacidade, condição,
   estoque, preço direto e frete. Não conclua sucesso de uma fonte por um job verde.

O agendamento, execução manual, teste Telegram e retenção de histórico foram
preservados. Nenhum secret foi modificado. O cache continua sendo conveniência
sem garantia de durabilidade; se for perdido, histórico e cooldown recomeçam.

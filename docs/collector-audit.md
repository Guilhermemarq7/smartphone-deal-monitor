# Auditoria da coleta — 6 de outubro de 2026

## Resultado e evidência

O relato do usuário registrava HTTP 403 nas buscas de Mercado Livre/Magalu no
GitHub Actions, com cobertura parcial de Samsung/Motorola. A auditoria encontrou
além disso erros de associação de variante: o target consultado era atribuído
sem validar o modelo retornado, números de modelo eram descartados no matcher,
e páginas oficiais podiam usar parcelas/cashback ou preço de outra variante.

Nesta tarefa, os primeiros acessos foram recusados pelo proxy (CONNECT 403),
antes da resposta das lojas. Após mudança observada na conectividade, foi possível
repetir as operações e receber respostas reais. Não se alterou TLS, cookies,
fingerprint nem se usou CAPTCHA, navegador ou proxies alternativos.

| Fonte / documentação | Resposta posterior | Decisão |
| --- | --- | --- |
| Mercado Livre `/sites/MLB/search` sem token | HTTP 403, HTML genérico de erro Mercado Libre | Somente tentativa autenticada; sem token não consulta |
| Mercado Livre busca HTML | HTTP 403, mesmo HTML genérico | Não usar em cloud; opt-in local sem promessa de disponibilidade |
| Documentação ML de itens/buscas e OAuth | HTTP 403, mesmo HTML genérico | API vigente/permissão atual não puderam ser certificadas |
| Magalu busca HTML | HTTP 200 neste ambiente; parser controlado obteve zero ofertas; 403 no runner relatado | Continua desabilitada por padrão em cloud; acesso não é uniforme |
| Portal Magalu, API de produtos | HTTP 200 | API de gestão de portfólio do seller, não busca global de consumidor |
| Samsung, páginas S25/S26 | HTTP 200 e Product/Offer JSON-LD | Parser conservador validado live |
| Motorola, páginas Edge | HTTP 200; capacidade/estoque limitam aceitação | Sem inferir preços ausentes; API pública é alternativa |
| Motorola, catálogo público VTEX | HTTP 206, JSON com SKUs/preços/estoque | Nova integração pública por SKU |
| Fast Shop, catálogo público em `site.fastshop.com.br` | HTTP 206, JSON com SKUs/preços/estoque/sellers | Nova loja habilitada via API pública |
| KaBuM! | HTTP 403, página Azion Forbidden | Não habilitar nem contornar |
| Buscapé/Zoom | HTTP 403, CloudFront Request blocked | Não habilitar nem contornar |
| Casas Bahia, HTML | HTTP 403, página de erro | Não coletar HTML; preços de seller Casas Bahia podem vir do catálogo público Fast Shop |
| Carrefour, catálogo público | HTTP 403, "Please contact the site owner for access" | Não habilitar nem contornar |
| mibrasil, catálogo público | HTTP 403, página de manutenção | Não habilitar |
| Xiaomi mi.com/br | HTTP 200, conteúdo institucional | Sem fonte de preços verificada |
| Promobit | HTTP 200, anúncios públicos em JSON-LD | Não usar anúncios/cuponagem como preço live garantido de loja |
| Pelando | HTTP 200, página sem ofertas utilizáveis no HTML | Não habilitar |
| Amazon, página inicial | HTTP 200 na primeira consulta; HTTP 503 na repetição final | Acesso variável não prova catálogo/API autorizado; não acrescentar scraping |
| Referência oficial VTEX + OpenAPI oficial no GitHub | HTTP 200 | Endpoint, filtros, paginação e limite de 50 produtos conferidos |

## Mercado Livre: o que o 403 permite concluir

O endpoint anônimo e o HTML de busca retornaram o mesmo HTML genérico de erro;
a documentação também foi recusada. Isso sugere uma recusa de acesso além da
mensagem da aplicação, mas **não identifica a regra do fornecedor**. Não é
possível atribuir a causa definitivamente a IP de datacenter, token ausente ou
escopo do aplicativo. Nenhum access token estava disponível neste ambiente;
não houve teste autenticado real nem solicitação/exposição de credenciais.

A integração anterior recomendava token como solução para qualquer 403 e
repetia consultas por modelo/discovery. Authorization também era colocado na
sessão compartilhada com o HTML. Agora `ML_ACCESS_TOKEN` é lido apenas do ambiente,
Bearer é enviado apenas na requisição à API, e uma recusa 401/403/429 ou falha de
proxy encerra a fonte naquela coleta. Sem token, o estado é `missing_credential`,
sem tráfego. Discovery segue o mesmo tratamento e foi testado com mocks.

`/sites/MLB/search` é o endpoint já existente: **a disponibilidade ao aplicativo
do usuário em outubro de 2026 ainda precisa ser confirmada oficialmente**. Um
token não garante acesso. Não se inventou outro endpoint, não se usou busca de
itens de um vendedor como substituto da busca global, nem se contornou o 403.

Referências oficiais tentadas:

- https://developers.mercadolivre.com.br/pt_br/itens-e-buscas
- https://developers.mercadolivre.com.br/pt_br/autenticacao-e-autorizacao

Também se tentou a referência oficial argentina
https://developers.mercadolibre.com.ar/en_us/items-and-searches; o proxy recusou
essa conexão. Essa tentativa não determina a disponibilidade da API nem muda
a evidência de HTTP 403 recebido dos hosts brasileiros.

O usuário deve seguir o OAuth oficial com aplicação autorizada, verificar as
permissões de busca e manter a renovação do token fora deste projeto; não há
refresh automático implementado. O secret `ML_ACCESS_TOKEN` já é referenciado no
workflow e nenhum GitHub Secret foi alterado.

## Magalu

A documentação acessível descreve portfólio, preços e estoque com escopos como
`open:portfolio-skus-seller:read` e `open:portfolio-prices-seller:read`. Isso é
integração de seller, não comprovação de uma busca pública global de preços.

Referência lida: https://developers.magalu.com/docs/apis/products/overview

O HTML de busca funcionou neste ambiente, mas o relato registra 403 no Actions.
`cloud_enabled: false` permanece a escolha conservadora. Localmente, é opcional,
com circuit breaker, validação de variante e leitura de preço Pix explícito ou
metadado do card, sem mínimo de todos os valores monetários. Funcionamento local
não é garantido. Não há bypass ou mascaramento de identidade.

Após a confirmação de rede habilitada pelo usuário, uma busca controlada pelo
coletor local recebeu a página sem erro HTTP, mas produziu **zero ofertas**.
Portanto não se certifica o parser local como funcionando com os preços atuais.

## Nova integração VTEX: Fast Shop e Motorola

Referências oficiais lidas:

- https://developers.vtex.com/docs/api-reference/search-api
- https://github.com/vtex/openapi-schemas/blob/master/VTEX%20-%20Search%20API.json

A API documenta `GET /api/catalog_system/pub/products/search`, `ft`, filtros `fq`
e paginação `_from`/`_to`, com máximo de 50 produtos por resposta. Apenas os
endpoints públicos dos varejistas que responderam sem autenticação foram usados.
O OpenAPI também descreve credenciais para acessos protegidos: isso não autoriza
uso de APIs privadas, nem garante acesso anônimo universal em outras lojas.

Fast Shop redireciona sua loja para `site.fastshop.com.br`; esse é o host validado.
A categoria pública `/18/113/` identifica celulares/smartphones e exclui capas e
películas. A lista de sellers aceita somente IDs observados de Fast Shop (`1`),
Ponto (`cnl222`) e Casas Bahia (`cnl223`). Sellers desconhecidos são recusados.
Esses preços são do canal Fast Shop, com seller separado; não contamos cada
seller como uma fonte independente para inflar a saúde. Produtos usados,
recondicionados, vitrine e kits são descartados. A condição nova é uma premissa
do catálogo varejista desses sellers, sujeita a confirmação no checkout.

Motorola é consultada somente para targets da marca, e discovery é limitado a
uma consulta de Edge Pro. Essa integração expõe o Edge 70 Pro 256GB com estoque
sem depender de um preço na página HTML configurada. Edge 60 Pro 512GB sem estoque
não vira oferta só porque existe um valor em `AggregateOffer`.

Cada consulta tem timeout/retries limitados, atraso de 1,5 s e no máximo 50
produtos; não há varredura paginada do catálogo inteiro. O endpoint retornou HTTP
400 "Scripts are not allowed" quando espaços vieram como `+`; a codificação
padrão `%20` funcionou com **o mesmo User-Agent identificando o monitor**. Corrigiu-se
a codificação da query, sem spoofing ou mudança de identidade.

O parser vincula título/capacidade/condição ao SKU e vendedor. Aceita somente
estoque disponível e preço vigente em BRL; `Price` é preço base e `ListPrice` fica
separado do desconto histórico. Pix vem somente do **total** de uma parcela em um
sistema Pix público, sem BIN restritivo ou autenticação; valores em centavos são
convertidos uma vez. Não se usa valor da parcela de cartão, RewardValue/cashback,
Teasers ou cupom não confirmado como desconto direto. Frete continua desconhecido.

A fixture `tests/fixtures/vtex_fastshop_product.json` contém campos públicos
selecionados de uma resposta real de Fast Shop (S25 FE vendido por Ponto).
Metadados voláteis, validade temporal e campos não usados foram omitidos para
manter o teste determinístico; expiração é coberta separadamente com mocks.
A fixture `structured_product.html` é sintética e está identificada como tal.

## Páginas estruturadas e filtros

O parser vincula Product/Offer JSON-LD, inclusive `@graph`, referências de Offer
 e `ProductGroup/hasVariant`, ou preço/moeda em metadados com h1 comprovando a
variante. Rejeita preço agregado de família, moeda diferente, estoque
indisponível, preço expirado/restrito detectável e capacidade não comprovada.
Não usa mínimo monetário do texto nem capacidade inferida a partir do target.

O matcher preserva números de modelo (Edge 60/70, iPhone 15/16), normaliza GB/TB
com ou sem espaço e distingue FE/Ultra/Plus/Pro/Edge/Fusion. `S25+` não vira S25,
mas os sinais de soma em câmeras/RAM não criam uma variante Plus.

`sources.structured_pages` permite outras páginas verificadas, mas permanece
vazio/desabilitado: uma extensão genérica não é uma loja adicional certificada.
As novas fontes efetivas são catálogo Fast Shop e catálogo Motorola; não foram
acrescentados coletores apenas para aumentar a quantidade.

## Saúde, histórico e Actions

- HEALTHY: pelo menos duas lojas, 50% dos targets com preços válidos e nenhuma
  falha inesperada das fontes configuradas.
- DEGRADED: pelo menos dois targets com preço útil, mas falha/cobertura limitada.
- CRITICAL: nenhuma oferta válida ou menos de dois targets com preços live
  (mínimo limitado ao tamanho da lista configurada).
- OFFLINE: rede não avaliada; não prova saúde live.

Só ofertas aceitas após filtros contam. Bootstrap e discovery não substituem
cobertura da watchlist. O relatório, terminal e `output/health.json` mostram o
estado. `--fail-on-critical` retorna 2 após relatórios/alertas; o workflow usa
essa opção e conserva Summary com `always()`, mesmo em CRITICAL. O cache SQLite
é salvo somente em `refs/heads/main`; testes de branch podem restaurá-lo sem
publicar um novo estado persistente. Execuções manuais usam `dry_run: true`
por padrão para suprimir alertas do radar; o teste Telegram é opt-in independente.

O Telegram operacional usa uma tabela SQLite aditiva e cooldown global de 24 h
para CRITICAL, separado de promoções. Marca entrega somente após sucesso; uma
falha pode ser retentada. OFFLINE não envia aviso. Testes usam mocks e nenhuma
mensagem real foi enviada. Bootstrap, score antes da gravação do preço atual,
retenção e fingerprints de promoção foram preservados.

## Validação final após confirmação de rede habilitada

Em 6 de outubro de 2026, os acessos externos foram retomados: API/documentação
Mercado Livre continuaram em HTTP 403; documentação Magalu/VTEX respondeu 200;
as respostas das lojas e candidatas foram revistas sem tratar o bloqueio inicial
do proxy como diagnóstico definitivo. Amazon mudou de 200 para 503 na repetição.

```bash
.venv/bin/python -m pytest -q
.venv/bin/python main.py --validate
.venv/bin/python main.py --cloud --no-alerts \
  --db /tmp/radar-live-after-network-confirmation.db --fail-on-critical
```

- **86 testes passaram**, usando mocks/fixtures independentes de rede.
- Configuração validada com **10 variantes**; dependências passaram `pip check`.
- Coleta live terminou com código **0**, saúde **DEGRADED**, **20 ofertas**
  aceitas e **5/10 variantes** cobertas em **3 canais**: Fast Shop, Motorola e
  Samsung. Não é uma declaração de cobertura total nem de saúde HEALTHY.
- Os targets cobertos foram S25 256GB, S25 FE 256GB, S26 256GB, Edge 60 Pro
  512GB e Edge 70 Pro 256GB. As 20 ofertas incluem duas ofertas de discovery
  Edge 60 Pro 256GB, que não aumentam a cobertura da watchlist.
- Antes dos filtros globais, os catálogos retornaram 16 ofertas nas 12 consultas
  de targets e 69 candidatos nas 3 consultas de discovery; candidatos não são
  contados como ofertas válidas nem evidência adicional de saúde.
- SQLite da coleta passou `PRAGMA integrity_check`; não há alertas operacionais
  ou de promoção enviados nesta execução com `--no-alerts`.
- A revisão live revelou dois riscos de associação que foram corrigidos e
  cobertos por regressões: números de modelo Edge 60/70 e Realme 15T confundido
  com Xiaomi. Os resultados acima são da execução posterior às correções.

Não se iniciou um workflow remoto nem se enviou Telegram real. O teste no runner
Actions, com as políticas/IPs daquele ambiente, deve ocorrer após revisão e
merge manual; o README descreve os passos e os resultados a verificar.

## Limitações restantes

- API atual/permissão ML não certificadas e autenticação real não testada.
- Compatibilidade observada neste cloud precisa ser confirmada no runner do
  GitHub Actions após revisão/merge manual: IPs e políticas podem diferir.
- Fontes e estoques podem mudar; Pix/frete/condição devem ser conferidos no checkout.
- Sem token ML, essa fonte permanece indisponível e a saúde indica limitação.
- Cache Actions é conveniência: perder cache perde histórico/cooldown.
- Não há integração privada de seller Magalu nem scraping de lojas que recusaram acesso.

Nenhum GitHub Secret foi alterado. Nenhum novo secret é necessário para VTEX ou
saúde; Telegram usa as variáveis existentes. Não foi feito merge na main.

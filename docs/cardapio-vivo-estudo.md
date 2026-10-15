# Cardápio Vivo — estudo

> O cardápio digital da mesa: um feed vertical, um prato por tela, com vídeo ou foto —
> e, para a gestão, a medida da ATENÇÃO que cada prato recebe cruzada com venda e margem.
> Pedido do dono em 14/10/2026. Este documento manda sobre o código; a memória do módulo
> (`docs/memoria/catalogos.md`) guarda o que for decidido no caminho.

## 0. O que o dono decidiu (14/10/2026) — isto manda sobre o resto

| # | Pergunta | Decisão |
|---|---|---|
| 1 | Lançar no PDV automaticamente | **Não, por enquanto.** Continua a marca manual "lançado no PDV" (decisão de 28/09). |
| 2 | Esgotado | **Existe a marca "esgotado"** no item. ⚠️ Revoga a decisão 6 de 28/09 ("não haverá pausa"). O item continua no cardápio, marcado, e não pode ser adicionado (interpretação a confirmar — a resposta veio cortada). |
| 3 | Pedido da mesa | **Cada envio é um pedido**, ligado à mesa e à sessão. |
| 4 | Onde mora | **Rota pública no Next** (`web/`), mesmo domínio da API. O site de reservas continua como está e ganha o link. |
| 5 | Qual catálogo | **A configuração da loja aponta UM catálogo de origem PRODUTOS**; o QR da mesa sai dela. A loja continua podendo ter vários cardápios no site. |
| 6 | Segurança da URL | **Token por mesa**, regenerável (como o da fidelidade). Uma etiqueta só na mesa. |
| 7 | Fidelidade | **Respeitar o método configurado** (`QRCODE_MESA` ou `CODIGO_CAIXA`). |
| 8 | Chamar garçom / pedir conta | **Configurável** (liga/desliga). Ligado: notificação e som no painel aberto. |
| 9 | Seção por dia/horário | Dias da semana + faixa de horário + marca "vale nos dias de horário especial". |
| 10 | Mídia | **Spaces com CDN** para a mídia, e conversão com `imageio-ffmpeg`. Bucket e credenciais a criar no painel. |
| 11 | Onde fica cada campo | **Vídeo e restrições no PRODUTO**; "destaque" e "esgotado" no ITEM do catálogo. Restrições: lista fixa (vegano, sem glúten, sem lactose). |
| 12 | Adicionais | O adicional **pode apontar para um produto** (preço e custo saem dele); sem produto, é texto + preço. |
| 13 | Sem exigir confirmação | O pedido **nasce CONFIRMADO**. |
| 14 | Painel | Pedidos de mesa no **mesmo painel**, numa coluna "Mesas". |
| 15 | Identidade por loja | Cor principal, cor de fundo, logo e fonte. |

## 0b. O complemento do dono (14/10/2026, mesmo dia) — "sem alterar o que já foi feito"

| # | Pedido | Onde entrou |
|---|---|---|
| 1 | **Hub** antes do feed: marca + "Ver cardápio", "Avaliar no Google", "Wi-Fi" (rede, senha, copiar). Cada extra se liga à parte; sem nenhum, o Hub é pulado | **Fase 1** — migração 114: `unidades.google_avaliacao_url`, `wifi_rede`, `wifi_senha` (cadastro da LOJA) e `cardapio_config.hub_avaliacao`/`hub_wifi` |
| 2 | **Favoritos** (coração), nos dois modos, guardados no aparelho. Não substitui seleção nem carrinho | **Fase 1** — `localStorage` por LOJA (não por mesa), sem prazo |
| 3 | **Objetivo de negócio** (aumentar venda, girar estoque, lançamento, manter) e **nível de margem** (da ficha, com ajuste manual) no item | **Fase 2**, com o painel |
| 4 | Eventos `deslizou_frente`, `deslizou_tras`, `favoritou`, `desfavoritou`, `abriu_personalizacao`, `escolheu_opcao`, `abriu_hub`, `clicou_avaliacao`, `clicou_wifi` | **Fase 1** — 114 |
| 5 | Definições: **sessão engajada** (≥ 3 itens diferentes vistos OU 1 interação: favorito, personalização, adição); **atenção estimada** (tempo visível, teto de 60 s por visualização — não é rastreamento ocular nem intenção de compra); **deslize para trás** (voltou a um item já visto) | **Fase 1** a regra e os dados (`SQL_SESSAO_ENGAJADA`, `ATENCAO_MAX_MS`, `cardapio_resumo_dia`); o TEXTO no painel vem com ele |
| 6 | Painel: "atenção estimada média" no lugar de "tempo médio"; favoritos e deslizes para trás por item; cliques em Google e Wi-Fi no topo | **Fase 2** — os dados já são agregados (`cardapio_agregados_dia.favoritos/deslizes_tras`, `cardapio_resumo_dia`) |

⚠️ **O teto de 60 s vale na SOMA, não na gravação**: o bruto guarda o tempo medido, e todo
agregado usa `least(duracao_ms, 60000)`. Mudar o teto depois não pede reescrever o passado
enquanto o bruto existir.
⚠️ **Rolagem que a tela faz** (tocar numa categoria, abrir um favorito) **não é deslize** — o
feed suspende o registro por 1,2 s.

## 1. O que já existe e é reaproveitado (não duplicar cadastro)

| Precisa de | Já existe em |
|---|---|
| Seções, itens, ordem, foto e descrição | `catalogos` origem PRODUTOS, `catalogo_categorias/subcategorias/itens` (084) |
| Nome de vitrine, foto e texto do produto | `produtos.nome_catalogo`, `foto_url`, `informacao_adicional` (083/085) |
| Preço da loja | `produto_precos`, cascata loja → casa (a mesma do PDV) |
| Tradução EN/DE | colunas `_en/_de` e `traducao.escolher` (103) |
| Salões e mesas | `saloes`, `mesas` (069, 106, 108) |
| Pedido, painel, alertas, idempotência | `pedidos`, `pedido_itens`, `pedido_historico` (101) |
| Fidelidade | `fidelidade.checkin` / `pedir_codigo` (091, 097) |
| Margem por prato | aba "Margem por prato" do CMV (`margem_pratos`) |
| Vendas por produto | `vendas`/`venda_itens` via `codigo_pdv` |
| Arquivos | `api/arquivos.py` (banco hoje; Spaces é a troca prevista) |
| QR em PDF | `services/fidelidade_qr.gerar` |

## 2. Modelo de dados

### Fase 1 — migração 113 (`113_cardapio_vivo.sql`)

- **`produtos`** + `video_url`, `video_capa_url`, `video_bytes`, `video_segundos`, `video_em`,
  `restricoes text[]` (`VEGANO`, `SEM_GLUTEN`, `SEM_LACTOSE`, com CHECK).
- **`catalogo_itens`** + `destaque boolean`, `esgotado boolean`.
- **`catalogo_categorias`** e **`catalogo_subcategorias`** + `dias smallint[]` (1=seg … 7=dom,
  nulo = todos), `hora_de time`, `hora_ate time`, `horario_especial boolean` (aparece também nos
  dias de horário especial das Reservas).
- **`mesas`** + `token varchar(24)` único, gerado para todas as existentes.
- **`cardapio_config`** (uma por loja, PK `id_unidade`): `id_catalogo`, `modo`
  (`VITRINE`|`PEDIDO`), `exige_confirmacao`, `pedido_hora_de/ate`, `chamar_garcom`,
  `esconder_esgotado`, `cor_principal`, `cor_fundo`, `fonte`, `logo_url`, `retencao_meses`
  (padrão 13).
- **`cardapio_excecoes`** (salão OU mesa, nunca os dois): `modo`, `exige_confirmacao`,
  `pedido_hora_de/ate`. 🔑 A mais específica vence: mesa → salão → loja.
- **`produto_adicionais_grupos`** (`id_produto`, `nome`, `minimo`, `maximo`, `ordem`) e
  **`produto_adicionais_opcoes`** (`id_grupo`, `nome`, `preco`, `id_produto_ref` nulo, `ordem`).
- **`cardapio_sessoes`** (`id uuid` do navegador, `id_unidade`, `id_mesa`, `modo`, `dispositivo`,
  `idioma`, `inicio`, `ultimo`) — sem dado pessoal.
- **`cardapio_eventos`** (append-only, `bigserial`): `id_sessao`, `id_unidade`, `id_mesa`,
  `tipo`, `id_item`, `id_produto`, `id_categoria`, `modo`, `midia` (`VIDEO`|`FOTO`|`NENHUMA`),
  `duracao_ms`, `quando`. Índices por (`id_unidade`, `quando`) e (`id_produto`, `quando`).
- **`cardapio_agregados_dia`** (`dia`, `id_unidade`, `id_produto`, `id_mesa`, `hora`, `midia`,
  contadores e soma de atenção) — o que fica depois que a retenção apaga o bruto.

### Fase 2 — migração seguinte

- **`pedidos`**: `modo` aceita `MESA`; `id_mesa`, `id_sessao`, `origem` (`SITE`|`CARDAPIO`);
  `nome`, `telefone`, `forma_pagamento` passam a ser opcionais **só** quando `modo = 'MESA'`
  (CHECK condicional — os pedidos de site continuam exigindo tudo).
- **`pedido_item_adicionais`** — a escolha congelada (nome e preço) de cada item.
- **`cardapio_chamados`** (`id_unidade`, `id_mesa`, `tipo` GARCOM|CONTA, `criado_em`,
  `atendido_em`, `atendido_por`) — o tempo de atendimento sai daqui.

## 3. APIs

### Públicas (sem login, em `routers/cardapio_publico.py`, prefixo `/publico/cardapio`)

| Rota | O que faz |
|---|---|
| `GET /publico/cardapio/mesa/{token}` | Resolve loja + mesa, devolve modo efetivo, marca e o feed |
| `GET /publico/cardapio/loja/{id_unidade}` | O mesmo, sem mesa (vitrine/balcão) — modo da loja |
| `POST /publico/cardapio/eventos` | Lote de eventos (`sendBeacon`, corpo `text/plain` com JSON) |
| `GET /arquivos/{nome}?w=480` | (já existe) ganha redimensionamento em WebP e `Range` para vídeo |
| Fase 2: `POST …/mesa/{token}/pedido`, `POST …/mesa/{token}/chamado`, `POST …/identificar` | |

⚠️ **O feed nunca expõe custo, saldo nem id de produto**; o item vai pelo `id` do ITEM (como o
carrinho do 101).
⚠️ **Eventos: limite por sessão e por origem**, e tipo/ids conferidos contra a loja — é a
única rota pública que grava sem identificação nenhuma.

### Internas (com permissão)

| Rota | Permissão |
|---|---|
| `GET/PUT /cardapio-vivo/config` (loja) | `catalogos.editar` (ver: `catalogos.ver`) |
| `GET/PUT/DELETE /cardapio-vivo/excecoes` | `catalogos.editar` |
| `GET /cardapio-vivo/mesas` (links, tokens) · `POST /mesas/{id}/token` · `GET /mesas/qr.pdf` · `GET /mesas/{id}/qr.png` | `reservas.configurar` |
| `PUT /catalogos/itens/{id}/marcas` (destaque, esgotado) | `catalogos.editar` |
| `PUT /catalogos/secoes/{tipo}/{id}/exibicao` (dias, horário) | `catalogos.editar` |
| `POST/DELETE /produtos/{id}/video` · `PUT /produtos/{id}/restricoes` · CRUD de adicionais | `cadastros.produtos` |
| `GET /cardapio-vivo/sem-midia` | `catalogos.ver` |
| Fase 2: `GET /cardapio-vivo/painel` (Atenção × Vendas) | nova `cardapio.atencao` |

## 4. Telas

- **Cliente** — `web/app/c/[loja]/[[...mesa]]/page.tsx`: feed com `scroll-snap`, barra de
  categorias que acompanha a rolagem, mídia na regra vídeo → foto do item → da subcategoria →
  da categoria, detalhe com adicionais, filtro de restrição, "minha seleção" (VITRINE, no
  aparelho), aviso de cookies. ⚠️ **Sem service worker** e sem a casca do sistema.
- **Catálogos ▸ cardápio** — na página do catálogo: destaque/esgotado por item, dias/horário por
  seção, aviso "publicados sem foto e sem vídeo", pré-visualização (iframe do feed).
- **Produto ▸ aba Catálogo** — vídeo (upload + capa), restrições, grupos de adicionais.
- **Portal de Clientes ▸ Cardápio Vivo** — modo, opções, identidade visual, exceções por
  salão/mesa, retenção.
- **Salão** — "gerar acesso" por mesa: QR (PNG e PDF de todas) e o link para gravar no NFC.
- Fase 2: coluna **Mesas** e alertas de chamado no painel de pedidos; painel **Atenção × Vendas**.

## 5. Medição de atenção

- Sessão: `crypto.randomUUID()` em `localStorage`, renovada após 4 h sem uso.
- `viu_item` mede o tempo com ≥ 50% visível (`IntersectionObserver` com `threshold 0.5`); a tela
  fecha o intervalo ao sair, ao trocar de aba (`visibilitychange`) e no `pagehide`.
- Lote a cada 10 s ou 20 eventos, e no `pagehide` por `sendBeacon`.
- **"Quase pediu"** é calculado na LEITURA, não gravado: adicionou e removeu na sessão; carrinho
  com itens e sem `enviou_pedido`; `viu_item` acima do p90 do item sem `adicionou`.
- **LGPD**: o id é aleatório e não liga a ninguém; telefone só na identificação opcional (fase 2),
  e nunca no evento. Retenção: job diário agrega o dia anterior e apaga o bruto além de
  `retencao_meses`.

## 6. Testes

- `api/tests/smoke_cardapio_vivo.py`: config e exceções (a mais específica vence), token da mesa
  (gerar de novo invalida o antigo), feed (mídia em cascata, seção fora do dia/horário some,
  esgotado marcado, produto inativo some, preço da loja), eventos (lote, limites, loja errada
  recusada), retenção (agrega antes de apagar).
- `web/scripts/verificar-cardapio-vivo.mjs`: abre `/c/{loja}/{token}` em 390×844, rola com
  encaixe, a categoria ativa acompanha, adiciona à seleção, e os eventos chegam.
- Lighthouse mobile ≥ 85 medido no `next build` local.

## 7. Roteiro de implantação por fase

**Fase 1** — acesso, feed, VITRINE, cadastro, eventos
1. Migração 113 rodada aqui sobre base COM dado (idempotente: rodar duas vezes).
2. API + smoke verde; tela do cliente + verificação no navegador; Lighthouse ≥ 85.
3. Spaces: criar bucket e CDN, pôr `SPACES_*` no painel **antes** de promover; sem eles, o
   vídeo continua recusado com a frase que explica (a foto segue funcionando pelo banco).
4. `imageio-ffmpeg` entra no `requirements.txt` preso; conferir o build da DO.
5. Promover com `.\promover.ps1` (backup antes: há migração). Imprimir QR de UMA mesa e testar
   no salão antes de imprimir o resto.

**Fase 2** — PEDIDO, chamados, fidelidade, painel Atenção × Vendas.
⚠️ A mudança em `pedidos` é a única que mexe em tabela que já está no ar: a suíte
`smoke_pedidos` inteira tem de continuar verde antes e depois.

**Fase 3** — A/B de mídia e ordem, sugestões automáticas de destaque.

**Fora do escopo** — pagamento pelo celular; lançamento automático no PDV.

## 8. Fase 2 — construída em 15/10/2026 (migração 115)

Decisões do dono no início da fase: **esgotado aparece marcado** (confirmação da resposta
cortada de 14/10); **nível de margem pela margem-alvo da Precificação** (na meta ou acima =
alta; até 10 pontos abaixo = média; abaixo = baixa; sem meta ou sem custo = sem nível, salvo
ajuste manual); **cliente sem cadastro se cadastra no próprio cardápio** (nome + termo, e o
que a loja exigir).

- **Pedido da mesa** = a MESMA tabela `pedidos`: `modo = 'MESA'`, `origem = 'CARDAPIO'`,
  `id_mesa`, `mesa_nome` (congelado), `id_sessao`. Telefone e pagamento ficaram opcionais SÓ
  no modo MESA (`ck_pedido_site_completo`). ⚠️ A CHECK do modo MESA é sobre `mesa_nome`, não
  `id_mesa`: o `ON DELETE SET NULL` zeraria o id e travaria a exclusão da mesa.
- **Adicionais congelados** em `pedido_itens.adicionais` (jsonb), já somados no
  `preco_unitario` — total, painel e PDF não mudaram de conta. A troca na confirmação
  preserva os adicionais do item que fica.
- **O que a mesa pode pedir é o que o FEED mostra agora** (`cv.feed`): fora do horário da
  seção, esgotado ou sem preço é recusado. Sem mesa (URL da loja) é sempre VITRINE.
- **Chamados** em `cardapio_chamados`, um ABERTO por mesa e tipo (índice único parcial);
  "atendido" no painel mede o tempo de atendimento.
- **Identificação** reusa `reserva_clientes.identificar`; a fidelidade segue o método:
  `QRCODE_MESA` marca a visita com o segredo do programa (que nunca vai ao celular),
  `CODIGO_CAIXA` abre o pedido de código. Falha da fidelidade nunca desfaz a identificação.
- **Painel Atenção × Vendas** (`cardapio_atencao.py`, permissão `cardapio.atencao`):
  lê o evento BRUTO (aceita salão, dia da semana e hora); venda do PDV pelo produto (sem
  salão — o cupom não diz); quadrante pela MEDIANA do cardápio; sugestões com a prioridade
  do objetivo de negócio (lançamento/girar estoque com pouca atenção sobem para destaque;
  MANTER não vira "sair"). As definições saem da API e a tela as mostra.
- Telas: carrinho e acompanhamento na mesa, chamados, identificação; coluna **Mesas** e
  chamados com som no Painel de pedidos; opções do PEDIDO e **exceções** no Cardápio Vivo;
  objetivo e margem no item do catálogo; página **Atenção × Vendas**.
- Cobertura: `smoke_cardapio_pedido.py` (59) e `web/scripts/verificar-cardapio-pedido.mjs` (16).

**Fase 3 (não começou):** testes A/B de mídia e ordem, e sugestões automáticas de destaque.

## 9. Fase 3 — construída em 15/10/2026 (migração 116)

Decisões do dono no início da fase: **A/B de mídia = vídeo × foto** no mesmo prato (só prato
que tem os dois); **vencedor pela taxa de adição** (quem viu e adicionou — atribuível à
sessão); **A/B de ordem = a do catálogo × a sugerida pelo painel**; **destaque: o sistema
sugere, o gerente aprova**.

- **A variante não é gravada**: `mod(abs(hashtext(sessao || ':' || teste)), 2)` no banco, a
  mesma conta no feed e na análise. O feed recebe a sessão anônima (`?sessao=`); quem recusou
  a medição não manda e fica fora dos testes; a prévia do cadastro também.
- **Um teste aberto por prato (mídia) e um de ordem por cardápio** (índices únicos parciais).
  A ordem B fica CONGELADA no início (`ordem_b`), para a variante não mudar no meio.
- **Resultado**: sessões expostas (viram o prato — ou qualquer prato, no de ordem) e quantas
  adicionaram, por braço; teste de duas proporções bicaudal; abaixo de 100 sessões por braço
  é "amostra pequena" e não aponta vencedor; p < 0,05 aponta.
- **Aplicar** é sempre um clique de quem edita o catálogo, auditado: mídia B grava
  `catalogo_itens.midia_preferida = 'FOTO'` (o feed passa a mostrar a foto); ordem B grava a
  ordem congelada no catálogo, lista a lista, com passo 10.
- **Sugestões de destaque**: pôr = o painel diz DESTACAR e o prato não está em destaque;
  tirar = está em destaque e é candidato a sair, ou tem margem baixa sem ser lançamento.
  Aplicar passa pela mesma porta da marca manual do catálogo.
- Telas: **Testes A/B** (começar, resultado por braço, encerrar, aplicar A/B) e o cartão
  **Sugestões de destaque** no painel Atenção × Vendas.
- Cobertura: `smoke_cardapio_testes.py` (29) e `web/scripts/verificar-cardapio-testes.mjs` (10).

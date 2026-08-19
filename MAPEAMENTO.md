# Botane — Mapeamento do Sistema

> Documento-fonte da fase 0. Decisões tomadas em 18/08/2026 com o cliente.
> Escopo desta primeira parte: **base cadastral robusta + CMV + integração Omie**.

---

## 1. O problema que o sistema resolve

Um café/restaurante perde dinheiro em três lugares que a contabilidade só mostra
depois que o mês fechou:

1. **Compra** — o preço do insumo subiu e ninguém percebeu no ato do recebimento.
2. **Ficha técnica** — a receita no papel usa 80 g, a cozinha usa 110 g.
3. **Perda** — quebra, validade vencida, consumo interno e desvio saem do estoque
   sem nome, e todo mundo chama isso de "CMV alto".

O sistema separa esses três. Ele responde, a qualquer dia do mês:
*quanto custou o que eu vendi, quanto deveria ter custado, e onde está a diferença.*

- **CMV real** = estoque inicial + compras − estoque final
- **CMV teórico** = Σ (vendas do prato × custo da ficha técnica na data)
- **Variância** = real − teórico → é ela que aponta perda, desvio ou ficha errada

---

## 2. Princípios de arquitetura (as regras que não se negociam)

1. **O estoque é um livro-razão append-only.** `estoque_movimentos` nunca sofre
   `UPDATE` nem `DELETE`. Correção é movimento de estorno. Sem isso o CMV de
   ontem muda quando alguém edita algo hoje, e o relatório perde a fé.
2. **Dinheiro e quantidade em `numeric`, jamais em float.** Custo unitário com
   6 casas (`numeric(18,6)`), valores com 2. Arredonda só na tela.
3. **Custo médio é gravado no movimento, não recalculado do zero.** Cada linha do
   razão carrega `saldo_apos` e `custo_medio_apos`. Recalcular a série inteira é
   um job explícito de recuperação, nunca o caminho normal de leitura.
4. **Ficha técnica é versionada e o custo é congelado no uso.** A ordem de produção
   guarda a versão da ficha e o custo do momento. Editar a receita hoje não pode
   reescrever o custo do prato que saiu mês passado.
5. **Fechamento congela o período.** Depois de fechado, movimento com data anterior
   é recusado; reabrir exige permissão própria e fica na auditoria.
6. **Permissão é verificada no servidor, sempre.** A tela esconder o botão é
   conforto, não segurança.
7. **Toda linha carrega `id_unidade`.** Multi-loja desde o primeiro dia — botar isso
   depois é reescrever tudo.
8. **Banco em UTC, sessão em `America/Sao_Paulo`.** O fechamento do dia de um
   restaurante vira madrugada; sem isso a venda das 23h50 cai no dia errado.

---

## 3. Mapa de módulos

### Fase 1 — Fundação (o que esta parte entrega)

**3.1 Identidade e acesso**
- Usuários (e-mail, senha com hash, ativo, último acesso, foto)
- Papéis (perfis) com conjunto de permissões
- Permissões granulares por chave (`estoque.entradas`, `fichas.custos`, …)
- Vínculo usuário × papel **por unidade** (gerente da loja A ≠ da loja B)
- Sessão via JWT curto + refresh token revogável
- Auditoria: quem, o quê, quando, valor antes/depois (`jsonb`)
- Recuperação de senha, primeiro acesso, bloqueio por tentativas

**3.2 Cadastro da empresa** (a tela que o dono abre uma vez e não mexe mais)
- **Identificação fiscal** — razão social, nome fantasia, CNPJ, IE, IM, CNAE, regime
  tributário, data de abertura
- **Endereço completo** com CEP, código IBGE do município
- **Contato** — telefone, WhatsApp, e-mail, site, Instagram
- **Responsável e contador** — nome, CPF, CRC, e-mail e telefone do escritório contábil
- **Marca** — logo e cor, usadas nos relatórios e PDFs que saem do sistema
- **Lojas** — uma hoje; cada uma com CNPJ, endereço, horário de funcionamento e nº de mesas
- **Parâmetros de operação** (por loja) — dia de fechamento do CMV, permitir saldo negativo,
  exigir motivo de perda, dias de alerta de validade, % de variação de preço que dispara
  aviso na nota, criar produto automaticamente a partir da nota
- **Integrações** — credenciais do Omie e do PDV Legal, guardadas **cifradas**, nunca
  devolvidas pela API e mascaradas na tela

**3.3 Cadastros base**
- **Unidades** (lojas/filiais) — CNPJ, endereço, fuso, parâmetros próprios
- **Setores** — Cozinha, Bar, Confeitaria, Salão, Estoque, Delivery.
  Servem para (a) destinar consumo interno, (b) agrupar produção,
  (c) filtrar o CMV por área.
- **Locais de estoque** — Estoque seco, Câmara fria, Freezer, Bar.
  *Não confundir com setor:* setor é organizacional, local é físico e tem saldo.
- **Categorias** — árvore (`id_pai`), com tipo: insumo, revenda, produzido, embalagem
- **Unidades de medida** + conversões (kg↔g, L↔ml, cx→un, un→kg por produto)
- **Fornecedores** — CNPJ, contato, prazo, código no Omie
- **Produtos** — o cadastro central (detalhe em 4.3)

**3.4 Fichas técnicas** (o coração do custo)
- Ficha por produto de produção própria, com rendimento e nº de porções
- Itens: insumo **ou** sub-ficha (preparo intermediário — molho, massa, base)
- Peso bruto × peso líquido → **fator de correção (FC)**
- Fator de cocção (o que perde ou ganha peso ao cozinhar)
- Custo por porção calculado em cascata (recursivo, com trava de ciclo)
- Modo de preparo, foto, alérgenos, tempo, rendimento
- Versão + status (rascunho / homologada / arquivada), vigência por data
- **Permissão separada para ver custo** — chef edita receita sem ver dinheiro

**3.5 Estoque**
- Entradas: nota fiscal (Omie), entrada manual, devolução, produção
- Saídas: venda, requisição de produção, perda, consumo interno, transferência
- Motivos de perda catalogados (quebra, validade, erro de preparo, cortesia)
- Inventário/contagem com apuração de diferença → gera ajuste
- Saldo e custo médio por produto × local × unidade
- Estoque mínimo e alerta de ruptura
- **Lote e validade, opcionais por produto** — ligados só em quem precisa (perecível),
  e mesmo lá o campo não é obrigatório no lançamento (detalhe em 5.1)

**3.6 CMV e análise**
- Painel: CMV real, CMV teórico, variância, food cost % (CMV ÷ receita)
- CMV por período, por setor, por categoria, por produto
- Curva ABC de insumos (onde está 80% do dinheiro)
- Margem de contribuição por prato e engenharia de cardápio
- Evolução do custo do insumo (o que subiu de preço no mês)
- Fechamento de período com trava

**3.7 Integrações** — Omie na seção 8, PDV Legal na seção 9

### Fases seguintes (mapeadas, não construídas agora)

| Fase | Entrega |
|---|---|
| 2 | Compras: cotação, pedido de compra, conferência de recebimento |
| 3 | Produção: ordem de produção, etiqueta com validade, rendimento real |
| 4 | Vendas: API do PDV Legal alimentando o CMV teórico sozinha (seção 9) |
| 5 | Cardápio: precificação, simulador de margem, matriz de engenharia |
| 6 | Mobile: contagem de inventário pelo celular, offline |
| 7 | App de loja (Capacitor) — Android/iOS sobre o mesmo front |

---

## 4. Modelo de dados

DDL de rascunho em [`docs/schema_draft.sql`](docs/schema_draft.sql).

### 4.1 Empresa, lojas e parâmetros

```
empresa(id=1, razao_social, nome_fantasia, cnpj, ie, im, cnae, regime_tributario,
        data_abertura, telefone, whatsapp, email, site, instagram,
        cep, logradouro, numero, complemento, bairro, cidade, uf, codigo_ibge,
        responsavel_*, contador_nome, contador_crc, contador_email, contador_telefone,
        logo_url, cor_primaria)
unidades(id, nome, apelido, cnpj, ie, matriz, endereço…, timezone,
         horario_funcionamento jsonb, mesas, id_omie, ativo)
parametros(id_unidade PK, dia_fechamento_cmv, bloquear_retroativo,
           permitir_saldo_negativo, exigir_motivo_perda, casas_decimais_qtd,
           alerta_validade_dias, bloquear_saida_vencido,
           alerta_variacao_preco_pct, criar_produto_da_nota)
integracoes(id, id_unidade, servico, ativa, modo, credenciais bytea,
            config jsonb, ultima_sincronizacao, ultimo_status)
```

Credencial mora em `integracoes.credenciais`, **cifrada**. A API nunca devolve o valor —
só `••••1234` e a data da última sincronização. Trocar a chave é escrever, jamais ler.

### 4.2 Núcleo de acesso

```
usuarios(id, nome, email UNIQUE, senha_hash, ativo, ultimo_acesso)
papeis(id, nome, descricao, sistema bool)
permissoes(chave PK, modulo, descricao)
papel_permissoes(id_papel, chave)
usuario_papeis(id_usuario, id_papel, id_unidade)   -- escopo por loja
usuario_setores(id_usuario, id_setor)              -- opcional: ajudante só na área dele
sessoes(id, id_usuario, refresh_hash, expira_em, revogada_em, ip, agente)
auditoria(id, id_usuario, id_unidade, entidade, id_entidade, acao,
          antes jsonb, depois jsonb, em)
```

### 4.3 Produto — o cadastro central

```
produtos(
  id, id_unidade_dona,
  codigo, nome, nome_curto,
  tipo,                            -- INSUMO | REVENDA | PRODUZIDO | KIT | EMBALAGEM
  id_categoria, id_setor,
  producao_propria bool,           -- liga a ficha técnica
  controla_estoque bool,
  um_estoque, um_compra, fator_compra,   -- 1 CX = 12 UN
  perecivel bool, validade_dias,
  estoque_minimo, estoque_maximo,
  ncm, cest, codigo_barras,
  codigo_omie,
  controla_lote bool, controla_validade bool,     -- opcionais, por produto
  origem,                          -- MANUAL | OMIE | NOTA | PDV
  status,                          -- RASCUNHO | ATIVO | ARQUIVADO
  revisado_em, revisado_por,
  ativo, criado_em, criado_por
)
produto_precos(id_produto, id_unidade, preco_venda, vigente_de, vigente_ate)
produto_fornecedor(id_produto, id_fornecedor, codigo_no_fornecedor,
                   embalagem, fator, ultimo_preco)
```

`status = RASCUNHO` é o produto que nasceu sozinho (do catálogo do Omie ou de um item de
nota) e ainda não passou por gente. Ele **não entra no estoque** enquanto não tiver unidade
de estoque e fator de conversão — sem isso o custo por quilo sai errado e contamina o CMV.
É a única trava dura do cadastro automático.

`tipo` + `producao_propria` são o que separam o mundo: **INSUMO** entra por nota e
sai por ficha; **PRODUZIDO** nasce de uma ficha e é o que se vende; **REVENDA**
(uma água, uma cerveja) entra por nota e sai por venda, sem ficha.

### 4.4 Ficha técnica (recursiva)

```
fichas_tecnicas(id, id_produto, versao, status, rendimento_qtd, rendimento_um,
                porcoes, tempo_preparo_min, modo_preparo, foto_url,
                vigente_de, vigente_ate, homologada_por, homologada_em)
ficha_itens(id, id_ficha,
            id_insumo NULL, id_subficha NULL,   -- exatamente um dos dois
            qtd_bruta, qtd_liquida, um,
            fator_correcao,      -- bruto ÷ líquido
            fator_coccao,
            perda_percentual, observacao, ordem)
```

Custo por função recursiva `fn_custo_ficha(id_ficha, data_ref)`, com `WITH RECURSIVE`
e trava de profundidade — sub-ficha que referencia a si mesma precisa ser recusada
na gravação, não descoberta em runtime.

### 4.5 Estoque (o razão)

```
estoque_movimentos(
  id, id_unidade, id_local, id_produto,
  data_movimento, tipo, quantidade,        -- sinal + entrada / − saída
  custo_unitario, custo_total,
  saldo_apos, custo_medio_apos,            -- fotografia do momento
  origem_tipo, origem_id,                  -- NOTA | PRODUCAO | INVENTARIO | VENDA | MANUAL
  id_estorno_de, observacao, id_usuario, criado_em
)
estoque_saldos(id_unidade, id_local, id_produto, quantidade, custo_medio, atualizado_em)
estoque_lotes(id, id_unidade, id_local, id_produto, lote, validade, quantidade, id_nota)
movimento_lotes(id_movimento, id_lote, quantidade)
inventarios(id, id_unidade, id_local, data, status, id_usuario, fechado_em)
inventario_itens(id_inventario, id_produto, qtd_sistema, qtd_contada, custo_medio, diferenca)
perda_motivos(id, nome, ativo)
```

**Tipos de movimento:** `ENTRADA_NF`, `ENTRADA_MANUAL`, `ENTRADA_PRODUCAO`,
`ENTRADA_DEVOLUCAO`, `SAIDA_VENDA`, `SAIDA_PRODUCAO`, `SAIDA_PERDA`,
`SAIDA_CONSUMO_INTERNO`, `TRANSFERENCIA_SAIDA`, `TRANSFERENCIA_ENTRADA`,
`AJUSTE_INVENTARIO`, `ESTORNO`.

### 4.6 Compras, notas e de-para

```
notas_entrada(id, id_unidade, chave_nfe UNIQUE, numero, serie, id_fornecedor,
              data_emissao, data_entrada, valor_produtos, valor_frete, valor_desconto,
              valor_total, origem, id_omie, status, importada_em)
nota_itens(id, id_nota, seq, descricao_fornecedor, codigo_fornecedor, ncm,
           codigo_barras, lote_nf, validade_nf,
           quantidade, um_nota, valor_unitario, valor_desconto, valor_frete_rateado,
           id_produto NULL, sugestao_produto, sugestao_score,
           quantidade_convertida, custo_aquisicao_unitario, variacao_preco_pct)
codigos_externos(sistema, codigo, id_produto, descricao_externa, fator,
                 id_fornecedor, origem_vinculo, confirmado_por, confirmado_em)
sync_log(id, servico, chamada, pagina, registros, status, mensagem,
         iniciado_em, terminado_em)
```

`status` da nota: `IMPORTADA → CONCILIADA → LANCADA`. Só em `LANCADA` ela vira
movimento de estoque.

### 4.7 Vendas e CMV

```
vendas(id, id_unidade, data, hora, origem, canal, documento, id_externo, mesa,
       valor_total, desconto, cancelada, importada_em)
venda_itens(id_venda, codigo_pdv, descricao_pdv, id_produto NULL,
            quantidade, valor_unitario, valor_total, custo_ficha_unitario)
cmv_fechamentos(id, id_unidade, competencia, estoque_inicial, compras, estoque_final,
                cmv_real, cmv_teorico, variancia, receita, food_cost_pct,
                status, fechado_por, fechado_em)
```

Na fase 1 as vendas podem entrar por planilha/CSV enquanto a credencial do PDV Legal não
chega; o modelo já é o mesmo que a integração vai preencher (seção 9).

---

## 5. Motor de custo médio ponderado móvel

Toda entrada e toda saída passam por um único serviço. Ninguém escreve no razão
por fora.

```
ENTRADA:
  saldo_novo  = saldo_atual + qtd
  valor_novo  = (saldo_atual × custo_medio_atual) + (qtd × custo_aquisicao)
  custo_medio = valor_novo ÷ saldo_novo          -- se saldo_novo > 0

SAÍDA:
  custo_unitario = custo_medio_atual              -- a saída não muda o médio
  saldo_novo     = saldo_atual − qtd
```

**Detalhes que decidem se o número fecha:**

- **Custo de aquisição ≠ valor unitário da nota.** É
  `(valor unitário − desconto + frete rateado + IPI/ST) ÷ fator de conversão`.
  Uma caixa de 12 un a R$ 60 com R$ 6 de frete rateado dá R$ 5,50 por unidade,
  não R$ 5,00.
- **Concorrência.** Lançamento simultâneo do mesmo produto corrompe o médio.
  `SELECT … FOR UPDATE` na linha de `estoque_saldos` (ou advisory lock por produto)
  serializa o cálculo dentro da transação.
- **Saldo negativo.** Restaurante lança saída antes de a nota chegar o tempo todo.
  Bloquear trava a operação; permitir e ficar calado mente no custo. A escolha:
  **permitir com alerta**, usar o último custo médio conhecido e marcar o
  movimento como `custo_provisorio` — quando a nota entrar, o sistema oferece o
  reajuste retroativo dentro do período ainda aberto.
- **Estoque zerado com valor residual** (resto de arredondamento) é zerado no
  fechamento por um ajuste identificado, nunca escondido.

### 5.1 Lote e validade — controle, não custo

O cliente quer rastrear lote e validade, mas **sem obrigar** ninguém a digitar. As três
regras que fazem isso funcionar sem quebrar o CMV:

1. **Lote não é camada de custo.** A valorização continua sendo o custo médio. Se lote
   virasse camada de preço, viraria PEPS — que foi justamente o que não escolhemos.
2. **Liga por produto**, não no sistema inteiro: `controla_lote` e `controla_validade` são
   marcados na ficha de cadastro de quem é perecível. Farinha e detergente ficam de fora.
3. **Mesmo ligado, o campo é opcional no lançamento.** Movimento sem lote sai do saldo
   geral — o "sem lote". A soma dos lotes é sempre **menor ou igual** ao saldo do produto;
   a diferença é justamente o que entrou sem identificação. O inventário reconcilia.

Na saída, o sistema **sugere** o lote que vence primeiro (FEFO) e deixa trocar. O alerta de
vencimento usa `alerta_validade_dias` dos parâmetros; bloquear a saída de vencido é uma
opção desligada por padrão, porque travar a operação em serviço é pior que avisar.

---

## 6. Permissões — chaves previstas

```
admin.unidades            admin.usuarios           admin.papeis
admin.auditoria           admin.parametros         admin.integracoes

cadastros.produtos        cadastros.categorias     cadastros.setores
cadastros.locais          cadastros.fornecedores   cadastros.unidades_medida

fichas.visualizar         fichas.editar            fichas.homologar
fichas.custos                                    -- ver dinheiro na ficha

estoque.saldos            estoque.entradas         estoque.saidas
estoque.perdas            estoque.transferencias   estoque.inventario
estoque.ajuste            estoque.retroativo       -- lançar em data passada

compras.notas             compras.conciliar        compras.lancar

cmv.painel                cmv.relatorios           cmv.fechamento
cmv.reabrir

integracao.omie           integracao.omie.config
```

**Papéis de fábrica** — desenhados sobre as pessoas que existem na casa
(dono, cozinheiras, garçons/conferentes, ajudantes):

| Papel | Quem é | O que faz no sistema |
|---|---|---|
| **Dono / Administrador** | o dono | tudo, inclusive empresa, usuários e reabrir período |
| **Gerente** | quando houver | tudo da loja, menos `admin.*` e `cmv.reabrir` |
| **Cozinha** | cozinheiras | fichas técnicas **sem ver custo**, requisição de produção, apontar perda e quebra |
| **Conferente / Estoque** | garçons e ajudantes no recebimento | conferir a nota, lançar entrada, contar inventário, transferir entre locais |
| **Salão** | garçons | consultar ficha e cardápio, apontar cortesia e quebra do salão |
| **Contador** | escritório externo | leitura do CMV, dos relatórios e das notas; escrita nenhuma |

Duas travas que valem a pena desde o começo:

- **Custo é permissão à parte.** `fichas.custos` fica fora de Cozinha e Salão: a receita é
  do trabalho, a margem não.
- **Escopo por setor** (`usuario_setores`, opcional): ajudante lança perda e conta
  inventário só na área dele. Sem linha na tabela, sem restrição — não atrapalha a casa
  pequena e já resolve quando crescer.

---

## 7. Arquitetura técnica

```
D:\dsv\botane\
├─ api\        FastAPI + psycopg  (porta 9200)
│  ├─ main.py            monta routers, roda migrações no start, agenda jobs
│  ├─ migrations\        001_....sql, 002_....sql — numeradas, idempotentes
│  ├─ routers\           1 arquivo por domínio, requer_permissao no router
│  ├─ services\          regra de negócio; único lugar que escreve no razão
│  ├─ models\            Pydantic (request e response) — nunca body: dict
│  └─ integracoes\omie\  cliente, importador, de-para, fixtures
├─ web\        Next.js App Router + Tailwind (porta 3100), PWA
│  ├─ app\               rotas por módulo
│  ├─ components\        design system próprio
│  └─ lib\api.ts         cliente único; nada de fetch solto na página
├─ app\        Capacitor (fase 7)
├─ docs\       schema_draft.sql, decisões
└─ iniciar_local.ps1     sobe banco + api + web
```

**Padrões herdados dos outros projetos da casa** (Gestor Civil / ZonaViável):
migração `.sql` numerada rodando no start da API; router protegido por
`requer_permissao`; camada de service no front (nada de chamada crua na página);
service worker que **nunca** cacheia `/api`.

**Mobile:** o web é responsivo e instalável (PWA) desde o dia 1 — é o que o
estoquista vai usar na contagem. O app de loja vem na fase 7, empacotando o mesmo
front com Capacitor, e só ganha o que exige nativo: câmera para código de barras e
contagem offline.

---

## 8. Integração Omie — notas fiscais → estoque

**Ainda não temos `app_key`/`app_secret`** — e isso **não bloqueia a construção**. O que
se constrói agora, sem credencial nenhuma:

- o cliente HTTP com autenticação, paginação, retry com espera crescente e log;
- as tabelas (`notas_entrada`, `nota_itens`, `codigos_externos`, `sync_log`);
- o de-para, o rateio, a conversão de unidade e o lançamento no razão — tudo isso é
  **lógica nossa**, roda sobre resposta gravada em arquivo e é testável sem rede;
- a tela de conciliação e a fila de pendências;
- o modo `simulado`, que serve de demonstração para o cliente antes de qualquer chave.

O que **só** dá para fechar com a credencial na mão: o nome exato de cada campo da resposta,
qual serviço a conta usa de fato (`notaentrada` ou `recebimentonfe`), os limites de chamada
e como aquela conta preenche unidade e CFOP. Por isso a tradução da resposta do Omie para o
nosso modelo fica **isolada num único módulo** (`mapeadores.py`): quando a chave chegar,
o ajuste é lá, e não espalhado pelo sistema.

### 8.1 Como a API do Omie funciona

Todas as chamadas são `POST` JSON para `https://app.omie.com.br/api/v1/<serviço>/`
com o corpo:

```json
{ "call": "ListarNotaEnt", "app_key": "...", "app_secret": "...",
  "param": [ { "pagina": 1, "registros_por_pagina": 50 } ] }
```

### 8.2 Serviços que interessam

| Serviço | Endpoint | Métodos que usamos |
|---|---|---|
| Nota de entrada | `/api/v1/produtos/notaentrada/` | `ListarNotaEnt`, `ConsultarNotaEnt` |
| Recebimento de NF-e | `/api/v1/produtos/recebimentonfe/` | `ListarRecebimentos`, `ConsultarRecebimento` |
| Produtos | `/api/v1/geral/produtos/` | `ListarProdutos`, `ConsultarProduto` |
| Fornecedores | `/api/v1/geral/clientes/` | `ListarClientes` |
| Estoque | `/api/v1/estoque/consulta/` | `ListarPosEstoque`, `ListarMovimentoEstoque` |
| Famílias | `/api/v1/geral/familias/` | `ListarFamilias` |
| Pedido de compra (fase 2) | `/api/v1/produtos/pedidocompra/` | `ListarPedCompra` |
| Contas a pagar (futuro) | `/api/v1/financas/contapagar/` | `ListarContasPagar` |

`ListarPosEstoque` devolve o **CMC** (custo médio de compra) do próprio Omie — é a
nossa conferência cruzada: se o custo médio do Botane divergir do CMC, alguma
entrada não foi conciliada.

### 8.3 Como o produto da nota encontra o produto daqui

O vínculo é uma **cascata**, do mais confiável para o mais frágil. Só os três primeiros
níveis vinculam sozinhos:

| # | Chave | Automático? | Por quê |
|---|---|---|---|
| 1 | `codigos_externos` já gravado (código Omie → produto) | sim | é o vínculo que alguém já confirmou |
| 2 | **EAN / código de barras** do item da NF | sim | chave natural, global, não depende de quem digitou |
| 3 | Código do produto **no fornecedor** + CNPJ do fornecedor | sim | resolve hortifruti e distribuidor que não usa EAN |
| 4 | Semelhança de descrição (`pg_trgm`) + NCM igual | **não** | vira *sugestão* com nota de 0 a 100 |
| 5 | Nada bateu | — | vai para a fila de pendências |

Nível 4 nunca vincula sozinho: "FILÉ DE FRANGO CONG 1KG" e "FILE FRANGO RESF 1KG" são
parecidos e não são a mesma coisa — errar aqui contamina o custo de dois produtos ao mesmo
tempo. O sistema mostra o palpite já selecionado; a pessoa confirma com um clique.

**Confirmar grava o de-para** (`codigos_externos`) junto com o fator de conversão daquele
fornecedor. Da segunda nota em diante, aquele item entra sozinho. É esse aprendizado que faz
a fila de pendências encolher até quase zero depois de dois ou três meses.

Um produto daqui pode ter **vários** códigos externos — o mesmo café tem código diferente em
cada fornecedor, e ainda outro no PDV Legal. Por isso o de-para é N:1, e é a mesma tabela
para os dois sistemas.

### 8.4 Produto que ainda não existe aqui

Sim, dá para puxar. São dois caminhos, e os dois entram como **rascunho**:

**Carga inicial** — `ListarProdutos` traz o catálogo inteiro do Omie de uma vez. É o jeito
mais barato de nascer com centenas de insumos já cadastrados, com nome, NCM, EAN e unidade,
em vez de digitar tudo. Vira uma tela de "revisar importados": a pessoa passa produto a
produto completando unidade de estoque, categoria e setor.

**Item novo na nota** — quando a NF traz um item que não casou com nada, o sistema cria o
produto a partir do que a nota já diz (descrição, NCM, EAN, unidade da nota, último custo e
o fornecedor) e o deixa em `status = RASCUNHO`. Liga e desliga no parâmetro
`criar_produto_da_nota`.

A trava que protege o CMV: **rascunho não entra no estoque**. Falta a informação que decide
o custo — a unidade de estoque e o fator (a nota veio em CX, o consumo é em KG). Enquanto
houver rascunho, a nota fica em `CONCILIADA` e não vira movimento. Completar leva segundos
e é feito uma vez por produto, para sempre.

> Exceção: item que não se controla em estoque (descartável, material de limpeza avulso)
> pode ser marcado como `controla_estoque = false` e aí a nota fecha sem ele.

### 8.5 O fluxo de importação

```
 job a cada 30 min (+ botão "Sincronizar agora")
        │
        ▼
 ListarNotaEnt / ListarRecebimentos  ── janela por data de alteração, paginado
        │
        ▼
 grava em notas_entrada  ── chave: chave_nfe (44 díg.) com índice ÚNICO
        │                   reimportar não duplica; a idempotência é do BANCO
        ▼
 CONCILIAÇÃO  ── cada item procura o produto pelo de-para
        │        (código Omie → id_produto). Não achou? vira pendência.
        │        Vincular uma vez ensina o sistema para sempre.
        ▼
 CONVERSÃO    ── unidade da nota (CX/FD) → unidade de estoque (KG/UN)
        │        pelo fator do produto ou do produto × fornecedor
        ▼
 RATEIO       ── frete, desconto, IPI e ST diluídos por valor no item
        │        = custo de aquisição real
        ▼
 LANÇAMENTO   ── um ENTRADA_NF por item; o motor recalcula o custo médio
```

### 8.6 Cuidados

- **Paginação obrigatória** (`pagina` / `registros_por_pagina`) — nunca puxar tudo.
- **Back-off em erro.** O Omie recusa consumo redundante e tem limite de chamadas;
  o cliente precisa de retry com espera crescente e registro em `omie_sync_log`.
- **Nada é escrito no Omie na fase 1.** Só leitura. Escrever (baixar pedido, gerar
  título) fica para depois de a leitura estar confiável.
- **Item sem vínculo não entra no estoque.** A nota fica conciliada parcialmente e
  aparece na fila de pendências — importar errado é pior que não importar.
- **Nota que já veio lançada com estoque no Omie** não pode entrar de novo aqui como
  se fosse nova entrada. Qual sistema é dono do estoque é parâmetro da integração.

---

## 9. PDV Legal — as vendas que alimentam o CMV teórico

O PDV do cliente é o **PDV Legal**, que roda sobre a plataforma **Tablet Cloud**. Ele tem
API própria — verificado na documentação pública deles:

- **Autenticação:** `POST https://api.tabletcloud.com.br/token`, com `username`, `password`,
  `grant_type=password`, `client_id` (código do grupo econômico) e `client_secret` (token do
  grupo econômico). Devolve um Bearer token válido por ~6 horas (21.599 s).
- **Catálogo de endpoints:** **não é público**. Fica no portal de parceiros
  (`oem.tabletcloud.com.br`) ou por `development@tabletcloud.com.br`.
- Métodos SOAP antigos foram descontinuados; o que vale é o REST.

**O que precisa ser pedido ao suporte do PDV Legal** (o cliente pede, como titular da conta):
credenciais de integração (as cinco acima) **e** o acesso à documentação dos endpoints.
Enquanto isso não vem, vale a mesma regra do Omie: não dar por pronto o que não foi testado
com credencial.

**Plano B que não trava o projeto:** a Retaguarda do PDV Legal tem relatório de vendas
exportável. O importador nasce lendo planilha, com o mesmo destino (`vendas` e
`venda_itens`); quando a API abrir, muda a fonte e não o resto.

**O que queremos de lá:** venda por dia com item, quantidade, valor, desconto,
cancelamento e canal (salão, balcão, delivery) — e o cadastro de itens do cardápio, para o
de-para. O vínculo item-do-PDV → prato daqui usa a **mesma** tabela `codigos_externos`, com
`sistema = 'PDV_LEGAL'`.

**Duas decisões de desenho que evitam contar duas vezes:**

1. **A venda não baixa estoque.** Quem baixa insumo é a produção/requisição. Se a venda
   também baixasse, o mesmo quilo de carne sairia duas vezes. A venda serve para o **CMV
   teórico** (quantidade vendida × custo da ficha) e para o food cost.
2. **Cobertura de vínculo vira indicador.** O painel mostra qual % da receita do período está
   com prato vinculado à ficha. CMV teórico de 60% do faturamento não é CMV teórico — é
   metade da conta, e o número precisa dizer isso na cara.

O PDV Legal tem módulo de estoque e de ficha técnica próprios. Vale dizer isso ao cliente
antes que ele descubra sozinho: o que o Botane faz e ele não faz é **fechar o ciclo** —
nota de compra do Omie com rateio virando custo médio, ficha em cascata com fator de
correção, e o confronto entre CMV real e teórico com a variância nomeada.

---

## 10. Ordem de construção

| # | Etapa | Entrega verificável |
|---|---|---|
| 0 | Mapeamento | este documento + página de apresentação ✔ |
| 1 | Fundação ✔ | *concluída em 18/08/2026* — banco, login, papéis e permissões, empresa, lojas, auditoria |
| 2 | Cadastros ✔ | *concluída em 19/08/2026* — produtos com tipo/conversão/lote, fornecedores, categorias em árvore, setores, locais e UM |
| 3 | Fichas técnicas ✔ | *concluída em 19/08/2026* — sub-ficha em cascata, fator de correção, custo por porção, versão e homologação |
| 4 | Estoque ✔ | *concluída em 19/08/2026* — razão append-only, custo médio móvel com trava, perdas, transferência, produção pela ficha e inventário |
| 5 | Omie | importação de NF com de-para e rateio (simulado → real) |
| 6 | CMV ✔ | *concluída em 19/08/2026* — painel real × teórico, variância, ABC, margem por prato, vendas por planilha e fechamento com trava |
| 7 | Mobile/PWA | contagem e consulta pelo celular |
| 8 | App | Capacitor, Android primeiro |

---

## 11. Decisões registradas

| Data | Decisão | Motivo |
|---|---|---|
| 18/08/2026 | Next.js + FastAPI + PostgreSQL | telas densas (ficha, CMV), PWA no dia 1, app depois pelo mesmo front |
| 18/08/2026 | Custo médio ponderado móvel | padrão do food service brasileiro, concilia com o CMC do Omie |
| 18/08/2026 | Projeto local, sem deploy | a primeira parte é validação com o cliente |
| 18/08/2026 | Integração Omie só de leitura | sem credencial ainda; escrever no ERP do cliente exige confiança conquistada |
| 18/08/2026 | Uma loja hoje, modelo multi-loja | `id_unidade` em tudo; a interface esconde o seletor enquanto houver só uma |
| 18/08/2026 | Lote e validade **opcionais**, por produto | rastreio sem obrigar digitação; lote é controle, não camada de custo (seção 5.1) |
| 18/08/2026 | Produto pode nascer do Omie, como rascunho | carga inicial do catálogo + item novo da nota; rascunho não entra no estoque |
| 18/08/2026 | De-para em cascata, com confirmação humana no nível frágil | EAN e código do fornecedor vinculam sozinhos; semelhança de texto só sugere |
| 18/08/2026 | PDV Legal (Tablet Cloud) é a fonte de vendas | tem API REST; catálogo de endpoints é gated, pedir ao suporte |
| 18/08/2026 | Venda não baixa estoque | quem baixa é a produção; senão o insumo sai duas vezes |
| 18/08/2026 | Papéis pelas pessoas reais da casa | dono, cozinha, conferente/estoque, salão, contador — custo é permissão à parte |
| 18/08/2026 | Cadastro de empresa completo, com parâmetros e credenciais cifradas | é a tela que configura o comportamento do sistema inteiro |

---

## 12. Em aberto

Respondido em 18/08/2026: uma loja (modelo já é multi-loja), PDV Legal, lote/validade
opcional, e os papéis reais da casa. Segue pendente:

- [ ] **Credenciais do Omie** — `app_key` / `app_secret` (cliente vai verificar)
- [ ] **Credenciais do PDV Legal / Tablet Cloud** — `username`, `password`, `client_id`,
      `client_secret` **e** o acesso à documentação dos endpoints (pedir ao suporte deles)
- [ ] **Dados da empresa** para o cadastro: CNPJ, IE, regime tributário, endereço, contador, logo
- [ ] **Quais setores e locais de estoque** existem de fato (cozinha, bar, confeitaria?
      câmara fria, freezer, estoque seco?) — é o que estrutura o inventário
- [ ] **Quem recebe login**, e quantos: o dono, cada cozinheira, os conferentes?
- [ ] **Quantos insumos e quantas fichas** existem hoje, e em que formato (planilha, caderno,
      cabeça da cozinheira) — define o tamanho da carga inicial
- [ ] O PDV Legal já é usado com ficha técnica/estoque? Se sim, dá para exportar de lá

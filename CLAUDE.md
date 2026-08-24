# Botane — guia para Claude Code

Sistema de gestão para café/restaurante, sob encomenda, construído **por partes**.
Projeto **independente** do Gestor Civil (o `D:\dsv\CLAUDE.md` do diretório acima é
de outro sistema — não vale aqui, exceto pelos padrões de código citados abaixo).

**Antes de qualquer coisa, leia [`MAPEAMENTO.md`](MAPEAMENTO.md)** — é o documento-fonte:
escopo, modelo de dados, regras de negócio, permissões, integração Omie e ordem de
construção. Rascunho do DDL em `docs/schema_draft.sql`.
Apresentação para o cliente: `apresentacao/index.html` (arquivo local, autocontido;
só as fontes vêm da internet). Publicada também como artifact — republicar sempre com a
mesma URL para não criar link novo.

⚠️ **Tudo deste projeto mora no D:.** Não usar o scratchpad da sessão (`%TEMP%`, que fica no C:)
para arquivo nenhum — gravar direto aqui.

## Estado

- Mapeamento e **etapas 1 a 6 — a primeira parte inteira** (fundação, cadastros, fichas,
  estoque, Omie e CMV) concluídas em 18 e 19/08/2026.
- Roda local: `.\iniciar_local.ps1`. Admin inicial `admin@botane.com.br` / `botane123`.
- **Falta só a credencial do Omie**: o importador roda em **modo simulado** sobre fixtures.
  Ao configurar `app_key`/`app_secret` em Integrações e mudar o modo para `real`, o mesmo
  código passa a falar com a conta do cliente — o que pode precisar de ajuste é só
  `services/omie/mapeadores.py`.

### O que já existe
- `api/` FastAPI: `database.py` (pool, sessão em America/Sao_Paulo), `db_updater.py`
  (migrações por checksum — **todo script tem de ser idempotente**), `seguranca.py`
  (bcrypt, JWT, refresh rotativo com hash no banco, `requer_permissao`),
  `auditoria.py` (grava no MESMO cursor da operação e filtra senha/credencial).
- `api/db_scripts/`: 001 acesso+empresa, 002 permissões e papéis de fábrica, 003 empresa inicial.
- `web/` Next.js 16 (App Router): `lib/api.ts` (cliente único, renova o token sozinho),
  `lib/sessao.tsx` (contexto + `pode()`), telas de início, empresa, lojas, usuários, papéis,
  auditoria e troca de senha.
- `api/db_scripts/`: 004 cadastros (setores, locais, categorias, UM, fornecedores, produtos,
  preços e produto×fornecedor), 005 semente dos cadastros.
- Routers da etapa 2: `cadastros.py` (as quatro tabelas de apoio no mesmo arquivo — são
  pequenas e sempre lidas juntas), `fornecedores.py`, `produtos.py`.
- **Loja atual em `seguranca.unidade_atual(cur, ctx)`** (19/08/2026): estava copiado em SETE
  routers, e a cópia ficou para trás quando o seletor passou a existir. A escolha vem do
  cabeçalho **`X-Unidade`** (não do corpo: vale para GET e nenhuma tela precisa repassá-la),
  validada com `ctx.ve_unidade` — mandar o cabeçalho não dá acesso a loja nenhuma.
- **Paginação**: as listas grandes devolvem o total em **`X-Total`** (via `count(*) OVER ()`,
  na mesma varredura) e o front usa `api.listar()`. ⚠️ O header precisa estar em
  `expose_headers` do CORS, senão o navegador não o entrega à tela.
- **O razão filtra por período, produto, tipo e local** (20/08/2026): `GET /estoque/movimentos`
  ganhou `inicio`/`fim`/`busca` (os mesmos nomes do CSV) e a tela ganhou a barra de filtro com
  paginação de 100 por `X-Total`. ⚠️ `fim` é dia **cheio** (`< fim + 1`): `<= fim` cortaria o que
  foi lançado às 14h do próprio dia, porque `data_movimento` guarda data e hora. O CSV aceita os
  mesmos filtros — filtrar na tela e baixar outra coisa faria quem conferisse achar que um dos
  dois mente. Os rótulos dos tipos saem de `GET /estoque/tipos-movimento`, não de uma lista
  copiada no front.
- **Aviso de ação flutua** (`components/aviso-flutuante.tsx`, 20/08/2026): sucesso e erro de
  AÇÃO saem por `useAviso()` e aparecem presos ao canto inferior — a mensagem ficava no topo e
  o botão de salvar está no fim de um formulário longo, então quem clicava não via confirmação
  nenhuma e clicava de novo. Sucesso some em 6 s; **erro fica até fecharem**. O aviso pode levar
  UMA ação ("cadastrar outro"), que é a resposta ao "cadastrei, e agora?".
  ⚠️ Erro de **carregamento** continua inline no cartão (é ele que explica a tela vazia) — a
  regra de bolso: mensagem com "Falha ao carregar" fica; o resto flutua.
- ⚠️ **Voltar tem de parecer um controle**: era `class="rotulo"` (10,5px, maiúsculas, cinza) e
  lia como legenda. Virou `.link-voltar`, pílula com borda e seta.
- Manual da equipe: `docs/manual-da-equipe.md`.
- ⚠️ **`.campo` é `width:100%` e vence a utilitária de largura do Tailwind.** `w-[110px]` num
  input com `campo` não faz nada — a largura tem de ir na COLUNA (`<th>`), e com `min-w` além
  do `w`: em `table-layout: auto` o navegador ignora a largura sugerida quando falta espaço.
- ⚠️ **Nome repetido em tabela de apoio devolvia 500.** A unicidade é do banco (é o certo),
  mas deixar a constraint estourar dava "Internal Server Error" para quem só digitou duas
  vezes o mesmo nome — no primeiro dia, cadastrando setores e locais. `_recusar_repetido()`
  em `routers/cadastros.py` confere antes e devolve 409 com frase.
- ⚠️ **As suítes rodam contra base virgem.** `tests/comum.py` tem `garantir_local`,
  `garantir_locais`, `garantir_setores` e `garantir_fornecedor` — nenhuma suíte pode supor
  que existe local, setor ou fornecedor, nem contar linhas de semente. `garantir_fornecedor`
  procura pelo **CNPJ**, não pelo nome: o CNPJ é a chave única, e buscar por nome falhava
  quando o Omie simulado criava outro fornecedor com o mesmo documento.
- `api/limpar_dados.py` zera a operação e deixa a base como instalação nova (`--simular`
  mostra sem apagar). Produtos e fornecedores saem inteiros de propósito: o seed não cria
  nenhum. **Recusa banco que não seja local.**
- **Tela inicial = painel do dono** (20/08/2026): `routers/inicio.py` entrega tudo numa
  chamada só — painel que faz seis requisições pisca seis vezes. ⚠️ **Número verdadeiro ou
  nenhum**: sem venda importada, `food_cost_pct` e `variancia` vão como `null` (não 0) e a
  tela mostra "—" com o motivo; zero ali pareceria um resultado excelente. Dinheiro só sai
  com `cmv.painel` — quem não tem recebe `dinheiro: null`, não um valor zerado. A cobertura
  de ficha viaja junto porque é ela que diz o quanto dá para confiar na variância.
- Telas: `/produtos`, `/fornecedores`, `/cadastros`, `/fichas`, `/estoque`, `/ajustes`,
  `/producao`, `/inventario`, `/compras`, `/cmv`, `/vendas`, `/integracoes`.
- **Busca de cadastro é o padrão onde havia combobox** (21/08/2026):
  `components/busca-cadastro.tsx` + `lib/busca-cadastro.ts`. Digita-se código ou nome e dá
  **Tab**: um resultado preenche e segue; mais de um (ou nenhum) abre a janela de pesquisa já
  filtrada; a lupa abre direto. A busca vai ao SERVIDOR (`?busca=`), então não depende da
  página carregada — combobox só serve até umas dezenas de linhas. Aplicado em produto
  (ajustes, nota manual, conciliação, ficha, kit, venda) e fornecedor (nota manual, vínculo do
  produto). ⚠️ Categoria, setor, local e unidade **continuam `<select>`**: são poucos por
  natureza, e trocar por busca ali seria atrito sem ganho.
  ⚠️ Na ficha o item aceita insumo OU preparo com ficha; **o id do preparo entra negativo**,
  que é o que deixa produto 5 e ficha 5 conviverem na mesma lista.
  ⚠️ Ficha só de leitura mostra o nome como TEXTO, não campo desabilitado.
- **Filtrar ≠ escolher** (`FiltroCadastro`): nos saldos e no razão o texto continua filtrando
  solto ("café" traz os cinco), e a **lupa FIXA** um produto — que vira etiqueta com ×, para
  ninguém achar que a lista está curta por acaso. Fixado manda `id_produto`; texto manda
  `busca`. Na **contagem de inventário** o filtro é só texto e local: a lista já está na tela e
  é ela que se percorre — abrir janela para escolher um item seria perder a contagem de vista.
  ⚠️ O impacto previsto soma **todos** os itens, nunca os filtrados.
- **`fonteDaLista()`** serve a janela a partir de uma lista já carregada (as receitas da
  produção). Mesma janela, outra origem.
- ⚠️ **"Tabelas de apoio" não era o nome de nada que se procura** (21/08/2026): quem precisava
  cadastrar o local de estoque procurava "local de estoque" no menu e não achava — as quatro
  tabelas estavam atrás de um rótulo genérico. Agora cada uma tem entrada própria apontando
  para `/cadastros?aba=…`, e a tela abre na aba pedida. ⚠️ O item de menu ativo compara
  **caminho + query**, e `useSearchParams` obriga uma fronteira de **Suspense**: ela envolve só
  o `MenuLateral`. Envolvendo a casca inteira, toda tela ficava em branco até o roteador
  resolver a query — e o `next build` recusa a pré-renderização sem a fronteira.
  ⚠️ A gaveta do celular fecha por mudança de CAMINHO; como as quatro abas compartilham o
  mesmo, os links do menu também chamam `aoNavegar`.
- ⚠️ **`innerText` não enxerga valor de campo.** Depois que a escolha virou input, "o nome
  aparece na tela" ficou falso no teste e verdadeiro no monitor — `verificar.mjs` tem
  `textoVisivel()`, que junta `innerText` com o valor dos inputs.
- **Consultar e lançar são telas separadas** (21/08/2026): entrada, saída, perda e
  transferência eram quatro botões no cabeçalho de `/estoque`, que é onde se CONSULTA.
  Viraram **Estoque ▸ Ajustes** (`/ajustes`): escolhe-se o tipo e o formulário se molda a ele.
  Depois de lançar o formulário **fica aberto e limpo** — quem ajusta um item ajusta o
  próximo. ⚠️ O item de menu aceita **lista** de chaves (`chave: string | string[]`): Ajustes
  serve a quatro permissões e quem só tem a de perda também precisa chegar nele.
- **`services/nfe_xml.py`** + `routers/notas.py`: a casa opera **sem integração nenhuma**. A
  nota entra por três portas — XML da NF-e, digitação e Omie — e da gravação em diante o
  caminho é um só (conciliação → conversão → rateio → razão). Por isso o ciclo da nota
  (conferir, vincular, lançar, estornar) mora em `notas.py`, e `omie.py` ficou só com
  credencial, sincronização e catálogo. Nota digitada não tem chave da NF-e: a repetição se
  reconhece por fornecedor + número + série (índice único `ux_nota_manual`).
  ⚠️ **Só a nota MANUAL se edita** (`PUT /notas/{id}`), e só antes de lançar: a que veio do
  XML/Omie é o documento do fornecedor, e mudar valor ali faria o sistema divergir da nota
  fiscal sem rastro. Os itens são reescritos inteiros — nada virou movimento ainda, e casar
  linha a linha só abriria caminho para item órfão.
- **Cadastro pode vir do Omie por três caminhos** (20/08/2026): catálogo de produtos (já
  existia, nasce RASCUNHO), **catálogo de fornecedores** (`importar_fornecedores`) e
  **criar produto direto do item da nota** (`POST /notas/itens/{id}/criar-produto`, que já
  cria o de-para e o `produto_fornecedor`). ⚠️ O importador de fornecedores **só preenche o
  que está em branco** — nunca sobrescreve o que alguém digitou aqui, senão reimportar
  desfaria correção. ⚠️ No Omie **cliente e fornecedor moram na mesma lista**: daí o
  `apenas_completar`. ⚠️ Criar produto do item **vincula ao existente quando o EAN já é de
  outro produto** — dois cadastros para o mesmo insumo partiriam o custo dele em dois (antes
  disso era 500). Depois de cada sincronização com nota nova, os fornecedores da leva são
  completados sozinhos.
- ⚠️ **A janela da busca do Omie é adaptativa** (`importador.janela`): sem parâmetro, vai
  **desde a última sincronização com 7 dias de folga** — a folga existe porque nota emitida
  antes e lançada no Omie depois cairia fora se a janela começasse onde a anterior parou, e
  ninguém veria (o resultado seria "0 novas"). `desde=` faz a carga inicial do histórico;
  `dias=` fixa. O controle do que já veio continua sendo a **chave da NF-e**, nunca um
  marcador. `GET /omie/conferencia-notas` compara período a período e **nomeia** as notas que
  faltam — "0 novas" sozinho não distingue "nada mudou" de "passou batido".
- **`services/omie/`**: `cliente.py` (HTTP, paginação, back-off, modo simulado com fixtures),
  `mapeadores.py` (**o único arquivo que muda quando a credencial real chegar** — cada campo
  é lido por uma lista de nomes possíveis) e `importador.py` (de-para em cascata, rateio,
  conversão, lançamento).
- Credenciais ficam cifradas (`services/segredos.py`, Fernet com chave derivada do
  `JWT_SECRET`) e **nunca voltam pela API** — só mascaradas. Trocar o `JWT_SECRET` invalida
  as credenciais guardadas.
- **`services/kits.py`** (19/08/2026): combo/kit — a linha única do PDV que vale por vários
  produtos. `KIT` já era um tipo previsto em `produtos.tipo` e nunca tinha sido implementado:
  o combo não é produzido (sem ficha) nem estocado (sem custo médio), então entrava no CMV
  teórico **sem custo**. ⚠️ A composição aponta para **produto**, não para ficha (ao
  contrário de `ficha_itens`): ficha é uma VERSÃO, e o combo preso a uma versão continuaria
  calculando pela receita velha depois de a cozinha homologar a nova. Cada componente resolve
  o custo pela regra dele. Componente sem custo **não zera** o combo — o que se sabe entra e a
  origem vira `kit_parcial`, para o buraco aparecer em vez de sumir. Ciclo recusado na
  gravação, com trava de profundidade por segurança (igual às fichas).
- **`services/relatorios.py`** (19/08/2026): os dois relatórios do dono. `cmv_por_grupo`
  quebra a MESMA conta do CMV por setor ou categoria — **não é rateio**, e a soma dos grupos
  fecha com o CMV do período (o teste confere isso). Produto sem grupo aparece como "Sem
  setor" em vez de sumir na junção. `evolucao_de_preco` ordena pelo **impacto em reais**, não
  pelo percentual: 8% num item semanal dói mais que 60% num trimestral. Base é o **custo de
  aquisição** (frete dentro), não o valor de tabela.
- **`services/cmv.py`**: `CMV real = estoque inicial + compras − estoque final`. O valor do
  estoque numa data sai do próprio razão (último movimento antes do corte já traz
  `saldo_apos` × `custo_medio_apos`) — não se recalcula série nenhuma.
- **O custo da ficha é congelado no item de venda** (`venda_itens.custo_ficha_unitario`):
  corrigir receita hoje não reescreve o CMV teórico do mês passado.
- Compras contam só `ENTRADA_NF` e `ENTRADA_MANUAL`; produção e transferência são
  transformação interna e se anulam na conta.
- **`services/custos.py` é o único lugar que sabe quanto custa um insumo**: custo médio do
  estoque, com o último preço do fornecedor como reserva. Dinheiro em `Decimal`.
- **FEFO (19/08/2026):** a saída de produto com `controla_lote` **escolhe o lote sozinha** —
  o que vence antes sai antes, quebrando em vários lotes se preciso (`_consumir_fefo`).
  Sem validade fica no fim da fila. ⚠️ **Lote nunca barra a operação**: a soma dos lotes pode
  ser menor que o saldo (o campo é opcional na entrada) e o que falta sai como "sem lote" —
  quem manda no saldo é o razão, lote é camada de controle. ⚠️ O **estorno espelha os lotes do
  movimento original** (`_lotes_espelho`), nunca o FEFO — senão devolveria ao lote errado.
  Antes disso a saída não baixava `estoque_lotes`: o saldo por lote só crescia e **o alerta de
  vencimento mentia**.
- **`services/estoque.py` é a única porta de escrita no razão.** `lancar()` trava a linha de
  saldo (`FOR UPDATE`), calcula o médio e grava a fotografia (`saldo_apos`,
  `custo_medio_apos`). Router nenhum monta INSERT em `estoque_movimentos`.
- **O médio segue a ordem de LANÇAMENTO, não a data do movimento** — data serve ao relatório;
  recalcular por data faria o CMV de ontem mudar sozinho.
- **Recuperação de senha** (19/08/2026): `services/senhas.py` (token de 32 bytes, só o sha256
  no banco, 30 min, **uso único**, pedido novo mata o anterior; redefinir **revoga todas as
  sessões**), `services/email.py` + `routers/email_config.py` (SMTP em `integracoes`, senha
  cifrada e mascarada). ⚠️ A tela pública responde **a mesma frase** para e-mail cadastrado e
  inventado — senão vira verificador de quem trabalha na casa; o motivo real vai só para a
  auditoria. Sem SMTP o sistema **não para**: grava o `.eml` em `api/arquivos/emails/` e o
  admin entrega o link pela tela de Usuários (`POST /usuarios/{id}/recuperar-senha` devolve o
  link — é o único lugar onde ele aparece).
- **PWA instalável** (19/08/2026): `app/manifest.ts`, `public/sw.js`, `app/offline/page.tsx`,
  `components/pwa.tsx` (registro + convite) e `scripts/gerar-icones-pwa.mjs` (roda na mão,
  usa sharp). Regras do service worker que **não se afrouxam**: a API (outra origem) e
  `/api` são ignoradas por completo — cachear serviria o saldo de um usuário para o próximo
  que entrasse no mesmo aparelho; HTML é network-first com a página `/offline` de reserva;
  só `_next/static/*` é cache-first (o nome tem hash). ⚠️ **Em dev o cache de estático é
  desligado** (`/sw.js?dev=1`), senão o HMR do Next serve pedaço velho e vira caça a bug que
  não existe. ⚠️ `apple-mobile-web-app-capable` está declarado à mão em `metadata.other`: o
  Next 16 só emite o nome padronizado, que o Safari entende do iOS 17.4 em diante.
- Testes: `smoke_fundacao.py` (36), `smoke_cadastros.py` (46), `smoke_fichas.py` (37),
  `smoke_estoque.py` (57), `smoke_cmv.py` (45), `smoke_omie.py` (70), `smoke_notas.py` (47),
  `smoke_senha.py` (40), `smoke_lotes.py` (28), `smoke_relatorios.py` (37),
  `smoke_kits.py` (29), `smoke_conversao.py` (23) e
  `web/scripts/testar-sw.mjs` (17, sem navegador) e `web/scripts/verificar.mjs` (no Chrome,
  com fotos em `web/scripts/_fotos`). Todos idempotentes; os de CMV medem **delta** sobre a
  apuração anterior, porque o banco local já tem dado de outras rodadas.

### Armadilhas já pagas
- ⚠️ **`ON CONFLICT (id_unidade, servico)` não pega linha com `id_unidade` NULL**: no Postgres
  nulos são distintos, então o UPSERT nunca conflita e cada gravação cria outra linha (o SMTP,
  que é da casa toda, sofreu disso). Quem garante a unicidade dessas linhas é o índice parcial
  `ux_integracao_global` (migração 012), e o `ON CONFLICT` precisa **nomeá-lo**:
  `ON CONFLICT (servico) WHERE id_unidade IS NULL`. Toda leitura da configuração global também
  filtra `AND id_unidade IS NULL`.
- ⚠️ **Matar o uvicorn no Windows pode deixar o worker órfão** segurando a 9200 — e o
  processo novo **sobe do mesmo jeito**, sem "address already in use". Os dois respondem
  alternadamente e metade dos pedidos volta do código velho (endpoint novo dando 404 no meio
  de um teste que já tinha passado). Ao reiniciar a API na mão, conferir se sobrou
  `multiprocessing-fork` órfão: `Get-CimInstance Win32_Process -Filter "Name='python.exe'"`.
- **`allowedDevOrigins` no `next.config.mjs`**: sem isso o dev server do Next devolve **403
  nos chunks** quando a página é aberta por `127.0.0.1` (ou pelo IP, no teste em celular).
  A tela renderiza, nunca hidrata, e o formulário vira submit nativo — parece bug de login.
- **`EmailStr` recusa domínio `.local`** (reservado). Por isso o admin é `@botane.com.br`.
- Componente `Aviso` renderiza `<p>`: não colocar dentro de outro `<p>` (erro de hidratação).
- **`localStorage` é do domínio, não da aba**: no teste de navegador, logar como outro
  usuário em qualquer página troca a sessão de todas — voltar como admin antes de seguir.
- Produto, fornecedor e categoria **não são apagados** quando já têm uso: viram inativos.
  Os testes contam com isso (reaproveitam em vez de recriar).
- **Ficha homologada não se edita** (mudaria custo histórico) — só nova versão. Ciclo de
  sub-ficha é recusado na gravação, e o cálculo ainda tem trava de profundidade por segurança.
- **`fichas.custos` filtra o JSON, não só a tela**: sem a chave, nenhum campo de dinheiro
  sai do servidor. Ao mexer no router de fichas, manter isso.
- **Um produto tem UMA unidade de estoque e N de compra** (20/08/2026, migração 015):
  `produto_unidades` (CX=12, FD=6, palete=480). `produtos.um_compra/fator_compra` continuam
  como reserva e são mantidos em dia pela unidade padrão. ⚠️ A ordem em `_fator_do_item`:
  de-para confirmado → **unidade da nota no cadastro** → fator do fornecedor → fator de
  compra. A unidade da nota vem antes do fornecedor porque casa pela UNIDADE; o número do
  fornecedor não diz em que embalagem.
- ⚠️ **A prévia de custo da nota digitada divide pela quantidade EM ESTOQUE**, não pela da
  nota: mostrava R$ 20,60 por caixa onde o custo real era R$ 1,72 por unidade. A tela busca
  o fator em `/produtos/{id}/unidades` e diz "por UN" no número.
- ⚠️ **CX, FD, PCT, BDJ e UN são todas grandeza UNIDADE com fator 1**: a conversão de
  grandeza diria que 1 CX = 1 PCT e engoliria a caixa de 12. `custos.converter()` agora
  **recusa** o par (devolve `None`) quando os dois lados são UNIDADE com o mesmo fator base —
  quem sabe o tamanho da caixa é o cadastro do PRODUTO. Dúzia continua convertendo: o fator
  12 é que separa "unidade de medida" de "nome de embalagem".
- **`custos.converter_para_estoque()` é a única regra de conversão** (20/08/2026):
  mesma unidade → **embalagem do produto** (`produto_unidades`, depois `um_compra/fator_compra`)
  → grandeza → `(None, "desconhecida")`. Ficha, produção e nota de entrada passam **todas** por
  ela. Antes só a nota consultava a embalagem: a mesma caixa valia 12 na entrada e 1 na ficha,
  e a produção baixava 1 pacote onde a receita pedia uma caixa de 12 — some com 11 do razão sem
  ninguém ver. Sem conversão conhecida a ficha **avisa** e a produção **recusa**; 1:1 calado é
  o que não pode acontecer. A ficha devolve `qtd_estoque`/`conversao` por item, e a tela mostra
  "no estoque 12 PCT".
- **O local de estoque é do PRODUTO** (`produtos.id_local_padrao`, migração 017): uma nota traz
  congelado e seco na mesma folha, e um local por NOTA obrigaria a lançar duas vezes ou a
  aceitar o sorvete no estoque seco. O local da nota virou **reserva** — vale para o produto
  que ainda não tem um definido, e a tela da nota mostra o destino item a item antes de lançar
  (`local_destino`). Ordem no lançamento: local do produto → local passado no lançar → local da
  nota.
- ⚠️ **O primeiro local da loja nasce principal** (migração 016), marque-se a caixinha ou não:
  estoque, produção e inventário usam o principal como padrão, e sem nenhum marcado o seletor
  mostrava o nome do local (era o único da lista) enquanto o pedido saía **sem** local — 404
  "Local não encontrado" com o local à vista na tela. As telas também caem para o primeiro
  local quando não há principal. ⚠️ Nenhuma suíte pegou isso porque `garantir_locais` mandava
  `principal: true` — mais cuidado do que quem cadastra "Balcão" tem. O helper parou de mandar.
- ⚠️ **`produto_fornecedor.ultimo_preco` é POR UNIDADE DE ESTOQUE**, não pela embalagem: quem
  grava é o lançamento da nota (o `custo_aquisicao_unitario`, com frete dentro), e
  `custo_do_insumo` lê **sem dividir por fator** — dividir de novo aplicaria a caixa duas vezes
  (12,00 a caixa de 12 virava 0,08 o pacote). O lançamento faz UPSERT: com `UPDATE` só, a
  primeira compra de um insumo não gravava preço nenhum.
- ⚠️ **Salvar o produto pela tela não pode apagar o que a tela não manda**: `_gravar_fornecedores`
  apagava tudo e reinseria, levando junto `ultima_compra` e `ultimo_preco` — e com eles o custo
  de reserva de toda ficha de insumo sem entrada no estoque. Agora só sai da tabela quem saiu
  da lista.
- Item de nota sem produto **não entra no estoque** e barra o lançamento da nota inteira.
- ⚠️ No XML da NF-e, `vFrete` **ausente** e `vFrete` igual a **zero** são coisas diferentes:
  zero é o emitente dizendo "neste item não há frete". Tratar zero como ausente joga o item no
  rateio por valor e cobra dele um frete que a nota não pôs. Se **algum** item traz o campo, o
  rateio é do emitente e os outros recebem zero — senão o frete entraria duas vezes.
- **Fechamento de mês bloqueia lançamento retroativo** — mas quem tem `estoque.retroativo`
  (inclusive o admin) passa. Teste da trava precisa de usuário sem a chave (o Conferente).
- **Movimento de estoque não se apaga**: estorno cria a contrapartida apontando para o
  original. Produto desativado mantém saldo e razão (a lista de saldos filtra por padrão).
- ⚠️ **Parâmetro NULL sem tipo dentro de `COALESCE` estoura no Postgres**: em
  `COALESCE(validade, '9999-12-31') = COALESCE(%s, '9999-12-31')`, um `None` vira `text` e dá
  "operador não existe: date = text". Entrada com lote **sem validade** dava 500 desde a etapa
  4 porque nenhum teste passava por esse caminho. Corrigido com `%s::date`.
- Teste que usa acento ou espaço na query precisa de `urllib.parse.quote` — o urllib recusa.
- `input[type=number]` no Chrome não seleciona conteúdo com `clickCount: 3` — no teste de
  navegador, limpar com ctrl+A, senão o valor entra colado (1 + 8 = 18).

## Stack e portas

| Camada | Escolha | Porta |
|---|---|---|
| Banco | PostgreSQL local (`botane_db`) | 5432 |
| API | FastAPI + psycopg, migrações `.sql` numeradas rodando no start | 9200 |
| Web | Next.js App Router + Tailwind, PWA | 3100 |
| App | Capacitor sobre o mesmo web (fase 8) | — |

Não há deploy: o projeto roda só local nesta primeira parte.

## Regras que valem para todo código deste repositório

1. `estoque_movimentos` é **append-only**. Correção é estorno, nunca `UPDATE`/`DELETE`.
2. Dinheiro e quantidade em `numeric` (custo unitário com 6 casas), **jamais float**.
3. Só o service de estoque escreve no razão, sempre com `SELECT … FOR UPDATE` no saldo.
4. Toda rota declara a permissão que exige; nada de checagem só na tela.
5. Toda tabela de movimento carrega `id_unidade` (multi-loja desde o início).
6. Banco em UTC, sessão em `America/Sao_Paulo`.
7. Ficha técnica é versionada; o custo é congelado no momento do uso.
8. Idempotência de importação é do **banco** (índice único), nunca do gatilho.

## Padrões herdados dos outros projetos da casa

- Migração `.sql` numerada e idempotente, executada no start da API
- Router FastAPI protegido por dependência de permissão; nada de `body: dict` (Pydantic)
- Front com camada de service — nenhuma chamada de API crua dentro da página
- Service worker do PWA **nunca** cacheia `/api`

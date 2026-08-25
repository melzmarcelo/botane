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
- **O Omie já foi exercitado contra a conta REAL do cliente** (24/08/2026): 37 notas do
  período, 2.183 produtos e 793 fornecedores importados de verdade. Sem credencial, o
  importador cai no **modo simulado** sobre fixtures, e as duas rotas passam pelo mesmo código.
  ⚠️ **A credencial que estava configurada se perdeu** quando a suíte `smoke_omie` estourou no
  meio, depois de gravar a chave de teste na mesma linha (ver `preservar_credenciais`, já
  corrigido) — para voltar ao modo real é preciso redigitar `app_key`/`app_secret` em
  Integrações.

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
- **Paginação é o PADRÃO de todo grid** (25/08/2026): `components/paginacao.tsx` —
  `usePaginacao(nome, { padrao, filtros })` + `<Paginacao p={pag} rotulo="…" />`. O rodapé diz
  "1–20 de 2.183", deixa escolher **20, 50 ou 100** e **lembra a escolha** (localStorage, por
  lista: conferir estoque numa tela grande pede 100, o celular pede 20).
  ⚠️ **O corte é do SERVIDOR** — trazer tudo e fatiar no navegador só troca a mentira de lugar.
  ⚠️ **Trocar o filtro volta para a primeira página** (é o que `filtros:` faz): quem está na
  página 7 e digita uma busca cairia numa tela vazia sem nada explicando.
  ⚠️ A preferência é lida num **efeito**, não no estado inicial: o servidor renderiza a tela
  antes de existir `localStorage`, e valores diferentes dos dois lados quebram a hidratação.
  Aplicado em produtos, fornecedores, notas, saldos, razão, fichas, vendas, inventários,
  produções, auditoria, usuários e movimentação do CMV. **Fora, de propósito**: tabelas de
  apoio, lojas, papéis e tudo que é detalhe de UM registro (itens da nota, insumos da ficha) —
  são poucos por natureza, e rodapé de página em lista de três linhas é ruído.
  ⚠️ **A movimentação do CMV é a única que fatia no navegador**, porque o rodapé precisa somar
  TODAS as linhas para a identidade fechar — o relatório vem inteiro de propósito.
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
- ⚠️ **Tabela nova que aponta para as tabelas limpas derruba `limpar_dados.py`** — e a
  mensagem do Postgres passa longe de "atualize a lista do script". Aconteceu com
  `produto_unidades` e com `cmv_movimentacao`: a limpeza estourava no meio e quem rodou achava
  que tinha limpado. O script agora **confere antes** (`referenciam()`) e recusa nomeando o que
  falta na lista.
- ⚠️ **A limpeza NÃO toca nas tabelas de apoio** (locais, setores, categorias): elas são
  cadastro base e ficam. Mas as suítes criam locais e setores com marcador a cada rodada, e a
  lista incha — vale tirar o que não é da semente de fábrica depois de uma bateria. A flag
  `--tabelas-de-apoio` esvazia mesmo, e aí a base fica MAIS vazia que uma instalação nova (a
  semente do script 005 não volta: o `db_updater` não reexecuta migração já aplicada).
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
- **A contagem tem tela própria, feita para o celular** (`/inventario/[id]`, 21/08/2026):
  quem conta anda pela despensa com o telefone, e uma tabela de dez colunas não serve na mão.
  Cada produto é um cartão; o progresso fica grudado no topo; há filtro "só o que falta".
  ⚠️ **Grava item a item, no blur** — contagem que só existe na tela até um "salvar tudo" no
  fim é contagem que se perde. ⚠️ A **unidade é escolhível** (migração 019), com a de estoque
  por padrão: quem conta conta caixa, e converter de cabeça é onde o erro entra. `qtd_contada`
  segue na unidade de ESTOQUE (é ela que o fechamento compara); `qtd_informada`/`um_informada`
  guardam o que foi digitado, senão ninguém sabe depois que 36 eram 3 caixas de 12.
- **Contagem cega** (`inventarios.cega`, migração 020): opção ao abrir o inventário. Ver o
  saldo esperado transforma a contagem em conferência — a pessoa lê 12, olha a prateleira e
  escreve 12. ⚠️ O esconderijo é no **servidor**: enquanto ABERTO, `qtd_sistema`, `diferenca`,
  `custo_medio` e `diferenca_valor` saem `null` para todos, e a folha CSV perde as colunas.
  Esconder só na tela deixaria o número no JSON e no papel impresso. Ao fechar, tudo aparece.
- ⚠️ **Seletor com uma opção só, desabilitado, lê como travado.** O de unidade da contagem
  ficava assim para produto sem embalagem cadastrada. Agora ele oferece as três origens que
  convertem de verdade — unidade de estoque, embalagens do produto e unidades da **mesma
  grandeza** (KG↔G sem cadastro nenhum) — e, ao lado, o caminho "contar em outra embalagem?"
  para o cadastro do produto. ⚠️ Dentro de UNIDADE, siglas com o mesmo fator base ficam de
  fora: CX e PCT não se convertem entre si (é a mesma regra de `custos.converter`).
- ⚠️ **`.campo` tem `font-size: 15px` e vence a utilitária** — abaixo de 16px o Safari do
  iPhone dá **zoom ao focar** e a tela salta a cada campo. Use `.campo-toque` (16px + alvo
  maior) em tela de uso no aparelho. `scripts/celular.mjs` fotografa e checa corte lateral.
- **As quatro tabelas de apoio ficam num item de menu só** — decisão do dono, 24/08/2026,
  depois de experimentar as quatro separadas. ⚠️ Como "Tabelas de apoio" não é o nome de nada
  que alguém procura, **a tela diz o que tem dentro** logo abaixo do título, e cada aba tem
  endereço próprio (`/cadastros?aba=locais`) para guardar e voltar direto.
  ⚠️ O item de menu aceita **lista** de chaves — Tabelas de apoio serve a quatro permissões.
- ⚠️ **`innerText` não enxerga valor de campo.** Depois que a escolha virou input, "o nome
  aparece na tela" ficou falso no teste e verdadeiro no monitor — `verificar.mjs` tem
  `textoVisivel()`, que junta `innerText` com o valor dos inputs.
- **Consultar e lançar são telas separadas** (21/08/2026): entrada, saída, perda e
  transferência eram quatro botões no cabeçalho de `/estoque`, que é onde se CONSULTA.
  Viraram **Estoque ▸ Ajustes** (`/ajustes`): escolhe-se o tipo e o formulário se molda a ele.
  Depois de lançar o formulário **fica aberto e limpo** — quem ajusta um item ajusta o
  próximo. ⚠️ O item de menu aceita **lista** de chaves (`chave: string | string[]`): Ajustes
  serve a quatro permissões e quem só tem a de perda também precisa chegar nele.
- **Cada nota tem endereço** (25/08/2026): `/compras` é só a LISTA, `/compras/nova` digita e
  `/compras/[id]` mostra — com **cabeçalho, itens e total**, no mesmo modelo do formulário de
  digitação. Antes as três coisas dividiam a mesma tela: o formulário empurrava as notas para
  fora do campo de visão, e a conferência mostrava os itens espremidos e **nunca somava o
  total** — quem conferia via as linhas e não via o número que se bate contra o papel do
  fornecedor. `/compras/[id]/editar` corrige a digitada (a correção também é longa demais para
  caber num cartão).
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
- **Achados da PRIMEIRA conta real** (24/08/2026) — cada um derrubava ou falseava a
  importação, e nenhum aparecia no modo simulado:
  1. ⚠️ **Fornecedor se separa de cliente por ETIQUETA.** Sem filtro, uma conta de 919
     cadastros trouxe **888 clientes** (pessoas físicas) para dentro dos fornecedores. O
     filtro vai no servidor: `clientesFiltro: {"tags": [{"tag": "Fornecedor"}]}` — desce 648
     em vez de 919. A etiqueta é configurável na tela (em branco = traz todo mundo).
  2. ⚠️ **`ListarProdutos` sem `filtrar_apenas_omiepdv: "N"` devolve ZERO.** A conta tinha
     2.198 produtos e a importação dizia "0 criado(s)" — indistinguível de "não tem catálogo".
  3. ⚠️ **Unidade que a casa não tem derrubava a carga inteira** pela FK (o catálogo trazia
     "M", de metro). Agora o produto nasce **sem unidade** e a mensagem conta quantos foram —
     é rascunho, e rascunho existe para lembrar que falta conferir unidade e fator.
  4. ⚠️ **O mundo real não respeita largura de coluna.** O "código" de um produto era a
     descrição inteira (42 caracteres) e o NCM vinha `2202.99.00.05`. Todo texto sai **aparado
     no tamanho da coluna** no mapeador, e NCM só em dígitos (pontuado num lado só nunca casaria
     com o do XML).
  5. ⚠️ **O teto de páginas truncava calado**: 992 de 2.198, e a mensagem dizia só "992
     criado(s)". `paginar` agora avisa por `ao_truncar(trazidos, total)`.
  6. ⚠️ **O Omie BLOQUEIA a conta por consumo indevido** quando as chamadas vêm rápido demais
     — e o bloqueio pega a integração inteira. Há `INTERVALO_MINIMO` entre chamadas, a espera
     que ele pede ("Aguarde 56 segundos") é obedecida, e **erro de estrutura não é repetido**:
     parâmetro errado continua errado na quarta tentativa e só gasta a cota.
  7. ⚠️ **`ListarNotaEnt` não aceita `apenas_importado`** — foi esse parâmetro inválido que
     consumiu cota até o bloqueio.
- 🔑 **As notas de compra estão em `produtos/recebimentonfe`, NÃO em `produtos/notaentrada`**
  (24/08/2026). O segundo é o lançamento manual de nota do Omie: na conta do cliente tinha
  **uma** nota, de 2024, enquanto o recebimento de NF-e tinha **3.670**. Quem olhasse só o
  primeiro concluiria que a casa não compra nada. A varredura usa `ListarRecebimentos` para os
  cabeçalhos e `ConsultarRecebimento` (por `nIdReceb`) para os itens — a lista **não traz item
  nenhum**, e o detalhe só é pedido para nota que ainda não existe aqui: pedir o de todas
  custaria meia hora e a conta bloqueada. Mapeador: `recebimento_de_nfe` / `item_do_recebimento`.
- ⚠️ **O Omie tem DOIS dialetos de paginação** (`cliente.DIALETO_PADRAO` e `DIALETO_HUNGARO`).
  Os módulos antigos falam `pagina`/`registros_por_pagina`; o recebimento exige
  `nPagina`/`nRegistrosPorPagina` e recusa o outro com "Tag [PAGINA] não faz parte da
  estrutura". Cada chamada recusada gasta cota — e cota gasta bloqueia a conta.
- ⚠️ **`ListarRecebimentos` não aceita filtro de data nenhum.** Testados e recusados:
  `dDtInicial`, `dDataInicial`, `dEmissaoDe`, `dDtEmissaoDe`, `dRegistroInicial`. Aceita só
  `cEtapa` e `nIdFornecedor`. Como a lista vem da nota mais VELHA para a mais nova, a varredura
  vai **da última página para a primeira** (`paginar(do_fim=True)`) e para na primeira página
  inteira fora da janela — senão a sincronização diária atravessaria três anos de histórico.
- **`nIdProduto` do item é o `codigo_omie` do produto** — nível 2 da cascata de conciliação,
  antes do EAN. É o de-para que o Omie já fez. Numa conta real, **109 de 114 itens** acharam
  produto por aí assim que o catálogo entrou.
- **`POST /notas/reconciliar`** passa a cascata de novo nos itens pendentes. Existe porque a
  ordem real é: chegam as notas, e só depois o cadastro fica pronto. Sem isso, item que não
  achou dono no dia da importação só sairia da fila na mão. Nota **lançada** não se mexe (os
  movimentos já estão no razão) e item ignorado fica ignorado.
- ⚠️ **Produto sem `um_estoque` NÃO entra no razão** (`lancar_nota`). Quantidade sem unidade é
  número sem significado — "3" de champignon não diz se são três bandejas ou três quilos —, e o
  custo médio que sair daí contamina ficha, CMV e a próxima compra. O catálogo do Omie cria
  rascunho sem unidade de propósito (a sigla do fornecedor pode não existir na casa); é no
  lançamento que a dívida é cobrada, e a recusa **nomeia todos** os produtos de uma vez.
- ⚠️ **O rodapé de tributos do DANFE vem grudado na descrição** e ia para o nome do produto:
  59 cadastros se chamavam "MAMÃO FORMOSA Trib. Aprox. (Fed: R$ 3,63…) Fonte: IBPT/…".
  `mapeadores._nome_limpo` corta na entrada; a migração 023 limpa o que já entrou.
- 🔑 **O `vTotalItem` do Omie JÁ TRAZ frete, IPI/ST e desconto rateados pelo emitente**
  (25/08/2026). Tratar isso como mercadoria e ratear as acessórias da nota por cima cobrava
  tudo DUAS vezes: numa conta real, R$ 74,44 a mais no razão e um queijo entrando 13,5% acima
  da nota. `mapeadores._acessorias_do_emitente` reconhece a sobra (`vTotalItem` − mercadoria
  líquida) e a transforma em acessória INFORMADA — a mesma regra que o XML já seguia: quando o
  emitente rateou, o rateio é dele e ninguém soma nada por cima. A mercadoria passou a ser
  **quantidade × preço**, nunca `vTotalItem`, e o desconto da NOTA guarda só o que não está
  nos itens (`vTotalDescontos` é a soma dos `vDesconto`). Migrações 024 e 025 consertam o que
  entrou antes; nota já lançada precisa de estorno + novo lançamento.
- ⚠️ **Fator 1 num vínculo não é resposta, é a falta dela.** `codigos_externos.fator` e
  `produto_fornecedor.fator` nascem 1 por padrão — e **o lançamento da nota CRIA a linha de
  `produto_fornecedor`** só para guardar o último preço. A cascata de `_fator_do_item` aceitava
  esse 1 como informação, e o vínculo recém-criado passava na frente do `fator_compra` do
  produto: o galão de azeite de 5 L entrou certo na primeira nota e virou 1 L na segunda, sem
  ninguém mexer no cadastro. Agora só fator **diferente de 1** conta como resposta.
- ⚠️ **Cópia congelada acompanha a largura da ORIGEM.** `cmv_movimentacao.codigo` era
  `varchar(20)` contra `produtos.codigo varchar(40)`: **fechar o mês estourava com 500** assim
  que a base tinha um código real de 40 caracteres. Migração 026. É a terceira vez que largura
  de coluna quebra com dado de verdade (catálogo do Omie e NCM foram as outras).
- ⚠️ **A unidade da nota ia CRUA para `produtos.um_compra`, que é chave estrangeira.** Uma
  conta real trouxe "UND", "BJ", "GA", "GF", "1UNID" — e criar produto a partir do item da nota
  devolvia 500 sem dizer por quê. Sigla desconhecida vira nulo.
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
- **Movimentação do estoque por produto** (`cmv.movimentacao_por_produto`, migração 018,
  21/08/2026): estoque inicial, entradas, saídas e estoque final de cada produto — a conta que
  EXPLICA o CMV, que é uma linha só. Aba em `/cmv` e planilha em `/exportar/movimentacao.csv`.
  ⚠️ O saldo inicial e o final saem da **fotografia do razão** (`saldo_apos` ×
  `custo_medio_apos`), não de somar entradas menos saídas: a quantidade daria igual e o
  **valor** não, porque o médio muda a cada entrada. ⚠️ Entradas e saídas aqui são **todas**
  (produção, transferência e ajuste inclusive) — a soma que vira CMV continua sendo só a de
  compras; são perguntas diferentes.
- **O fechamento congela a movimentação junto** (`cmv_movimentacao`): fechar o mês trava o
  relatório que explica o número, não só o número. Nome, código, categoria e setor vão
  **gravados** — renomear o produto depois não reescreve mês fechado. ⚠️ O congelado é do MÊS
  INTEIRO: um recorte dentro dele não vem congelado, e a resposta traz `mes_fechado` para a
  tela oferecer o mês completo em vez de deixar mandarem o parcial ao contador.
- **`services/relatorios.py`** (19/08/2026): os dois relatórios do dono. `cmv_por_grupo`
  quebra a MESMA conta do CMV por setor ou categoria — **não é rateio**, e a soma dos grupos
  fecha com o CMV do período (o teste confere isso). Produto sem grupo aparece como "Sem
  setor" em vez de sumir na junção. `evolucao_de_preco` ordena pelo **impacto em reais**, não
  pelo percentual: 8% num item semanal dói mais que 60% num trimestral. Base é o **custo de
  aquisição** (frete dentro), não o valor de tabela.
- **`services/cmv.py`**: `CMV real = estoque inicial + compras − estoque final`. O valor do
  estoque numa data sai do próprio razão (último movimento antes do corte já traz
  `saldo_apos` × `custo_medio_apos`) — não se recalcula série nenhuma.
- **Duas naturezas de produzido** (`produtos.modo_producao`, migração 021, 24/08/2026):
  `PARA_ESTOQUE` (a massa de pizza: produz, guarda, sai depois) e `NA_HORA` (o café passado:
  a venda produz e baixa no mesmo lançamento, e o saldo volta a zero). ⚠️ Sem o `NA_HORA` a
  casa venderia mil cafés e o pó continuaria inteiro no razão — ninguém registra produção de
  café a café. O par entrada/saída fica visível no razão de propósito.
- ⚠️ **Nada de `window.prompt`/`confirm`**: é a caixa do NAVEGADOR — fonte de sistema, botão
  em inglês, sem espaço para explicar o que a ação faz. O que não se desfaz pergunta pelo
  `Confirmacao` de `components/ui.tsx`, e o número que a ação usa fica num campo **na linha**,
  à vista antes do clique. Aplicado em: estornar movimento (razão e ajustes), estornar nota,
  fechar contagem, fechar e reabrir mês, cancelar venda e produzir da agenda.
  ⚠️ **Confirmação só onde mexe no razão ou fecha período.** Lançar a nota NÃO pergunta — a
  tela inteira é a conferência (itens, custos e destinos à vista) e um diálogo no caminho
  comum treina a clicar sem ler. Cancelar linha da agenda também não: é plano, não é razão.
  Cada diálogo diz **o que a ação faz**, não só "tem certeza".
- **A folha da produção** (`/producao/[id]`, `estoque.previsao_producao`): clicar no nome da
  linha abre o que a produção VAI precisar — por unidade, no total, o que existe no local de
  onde vai sair e o que falta. Roda a MESMA conta da produção (rendimento, conversão de
  embalagem, local de cada insumo); prever com outra regra seria prever outra coisa.
  ⚠️ A previsão é sempre de AGORA, nunca a de quando se agendou. ⚠️ Sub-ficha aparece como o
  PRODUTO dela, não explodida — é isso que a produção consome de fato.
  ⚠️ Resolver `id_local` como a produção resolve (cai no principal): sem isso o saldo era
  procurado num local nulo e a folha dizia que faltava tudo.
- ⚠️ **A agenda é lista de TAREFA, não histórico**: linha produzida some dela. O que já foi
  feito aparece em "Produções recentes" — misturar faria a agenda crescer para sempre e
  esconder o que falta no meio do que já foi. `?status=PRODUZIDA` traz o histórico, para
  conferir plano contra realizado.
- **Agenda de produção** (`producao_agenda` + `services/producao_agenda.py`): o PLANO, que
  não mexe no estoque — quem mexe é a produção, quando a linha é cumprida. ⚠️ A quantidade
  produzida pode sair diferente da planejada (a cozinha rendeu outra coisa) e as duas ficam
  registradas. Agendar o mesmo produto no mesmo dia **soma** em vez de duplicar: quem agenda
  de novo aumenta o lote, não abre outra ida ao fogão. Produto `NA_HORA` não se agenda.
  ⚠️ A sugestão repõe até o **máximo**, não até o mínimo — produzir só até o mínimo deixa a
  casa raspando o limite no dia seguinte.
- ⚠️ **O alerta de mínimo se divide em dois**: `estoque.minimo` (compra-se) e
  `producao.agendar` (a casa produz — aponta para a agenda, não para o estoque). Alerta que
  aponta para o lugar errado é alerta que ninguém segue. Há também `producao.atrasada`.
- ⚠️ **A produção baixa cada insumo do local DELE** (`id_local_padrao`), não do local
  informado no lançamento — uma receita usa leite da câmara e café do seco ao mesmo tempo.
  Achado pelo `cenario_cafeteria.py` em 24/08/2026: a saída batia num local sem saldo, o razão
  registrava a baixa por onde o insumo nunca passou (com **custo provisório**) e o saldo do
  lugar certo continuava cheio. O produzido também entra no local dele.
- ⚠️ **`lancar()` devolve `custo_exato` além de `custo_total`.** O razão guarda dinheiro em
  centavos, mas quem ENCADEIA custo (a produção soma consumos para achar o custo do prato)
  precisa do valor sem arredondar: a produção somava 4,48 + 4,98 = 9,46 onde a conta era
  9,455, e o prato nascia a 0,946 em vez de 0,9455 — meio centavo por unidade que reaparece
  multiplicado no CMV teórico.
- **`tests/cenario_cafeteria.py`**: a casa inteira funcionando uma vez, com números conferidos
  no papel (frete rateado, embalagem convertida, médio ponderado, ficha, sub-ficha, produção,
  perda, transferência, inventário, venda e o fechamento das identidades). 57 checagens.
  ⚠️ Mede **delta** da apuração e soma só os produtos do próprio cenário — a base pode ter
  outra coisa.
- ⚠️ **VENDER É SAIR DO ESTOQUE** (24/08/2026): a importação de venda lança `SAIDA_VENDA`
  para todo produto que `controla_estoque` — não só para o `NA_HORA`. Antes, o que era
  PARA_ESTOQUE (ou revenda) continuava na prateleira do sistema depois de vendido: o **CMV
  real saía subestimado** e a primeira contagem cobria o buraco inteiro como "ajuste de
  inventário", que é onde a diferença some sem nome. Cancelar a venda **estorna** os
  movimentos — cancelar sem devolver deixaria o produto fora da prateleira e fora do caixa.
- **`tests/cenario_semana.py`**: a operação de uma semana com um usuário por papel (gerente,
  conferente, cozinha, salão, contador) — quem pode o quê, e a conta fechando no fim. Com a
  baixa da venda no lugar, a **variância = perdas + ajustes** exatamente, e o food cost sai em
  30,6%. Foi ele que achou a falha acima. ⚠️ Mede **delta** da apuração e afirma só sobre os
  produtos que ele mesmo mexeu: a base é compartilhada com as outras suítes.
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
- Testes (807 verificações de API): `smoke_fundacao.py` (37), `smoke_cadastros.py` (47),
  `smoke_fichas.py` (37), `smoke_estoque.py` (82), `smoke_cmv.py` (56), `smoke_omie.py` (92),
  `smoke_notas.py` (70), `smoke_senha.py` (40), `smoke_lotes.py` (28),
  `smoke_relatorios.py` (37), `smoke_kits.py` (29), `smoke_conversao.py` (29),
  `smoke_producao.py` (46), `smoke_alertas.py` (28), `smoke_paginacao.py` (24),
  `cenario_cafeteria.py` (57) e `cenario_semana.py` (54); mais
  `web/scripts/testar-sw.mjs` (17, sem navegador) e
  `web/scripts/verificar.mjs` (223, no Chrome, com fotos em `web/scripts/_fotos`).
  Todos idempotentes; os de CMV medem **delta** sobre a apuração anterior, porque o banco
  local já tem dado de outras rodadas.
- ⚠️ **As suítes têm de sobreviver a uma base com dado REAL, não só a uma base virgem.** Depois
  de importar 37 notas e 2.183 produtos de uma conta de verdade, SEIS checagens quebraram — e
  nenhuma por bug do sistema: pegavam "o primeiro produto que controla estoque" (caiu num
  rascunho sem unidade), "o primeiro item pendente" (caiu numa nota do cliente), buscavam nota
  numa LISTA paginada onde a da fixture não estava mais, ou afirmavam sobre as primeiras linhas
  de um CSV. Regra: **cada suíte procura os registros DELA**, pelo código ou pelo número que
  ela mesma criou, e garante a precondição em vez de supô-la.
- ⚠️ **Fixture com data fixa envelhece.** As notas simuladas nasceram em 16–20/08/2026 e uma
  semana depois já caíam fora da janela automática da busca — o teste dizia que a importação
  tinha parado. `cliente._aproximar_datas` traz as datas da fixture para a semana de hoje
  mantendo o intervalo entre elas. Vale também para a demonstração: sistema que só mostra nota
  do mês passado parece parado.
- ⚠️ **O teste de navegador põe a integração em `simulado` e devolve o modo no fim.** Depois de
  o dono configurar a conta real, "Buscar no Omie" na suíte sincronizaria 3.670 notas de
  verdade — e a conta bloqueia quem consome demais. Trocar só o MODO não toca na credencial.
  O restauro é registrado em `aoTerminar` e roda no `finally` do roteiro: repor no fim do bloco
  não bastou, porque a suíte estourou no meio uma vez e deixou a integração em `simulado` — a
  busca do dono parou de trazer nota e nada explicava por quê. Mesma lição do
  `preservar_credenciais`.
- ⚠️ **`preservar_credenciais()` em `tests/comum.py`, registrado no `atexit`.** A suíte do Omie
  grava uma credencial de mentira na MESMA linha onde mora a real, e a API não devolve a chave
  em claro (é a regra que protege o segredo) — então perder a credencial do cliente é
  definitivo. Repor no fim do roteiro não bastava: a suíte estourou no meio uma vez, e foi
  assim que a chave real se perdeu. `atexit` repõe mesmo com traceback.

### Armadilhas já pagas
- ⚠️ **`toISOString()` é UTC, e depois das 21h em Brasília ele já diz amanhã.** A tela de
  Vendas propunha a data de amanhã para a importação do dia: um restaurante que fecha às 23h
  lançaria a venda inteira no dia seguinte, o CMV do mês fecharia errado e nada na tela
  denunciaria. Toda data que vira texto `aaaa-mm-dd` no front passa por **`lib/datas.ts`**
  (`hoje`, `diaLocal`, `somarDias`, `somarMeses`, `primeiroDiaDoMes`) — `sv-SE` é o formato
  ISO no fuso de quem está olhando. É a mesma armadilha que o banco resolve com a sessão em
  `America/Sao_Paulo`.
- ⚠️ **Movimento de estoque no FUTURO não existe** (`estoque.lancar`). A trava do período
  fechado olha para trás; para a frente não olhava ninguém, e a data errada acima entrava
  calada — o movimento caía fora do mês e o relatório de movimentação deixava de fechar com o
  saldo. Foi um dia de caça a um erro de cálculo que não existia. O razão é append-only: data
  errada ali não se conserta, só se estorna.
- ⚠️ **Saída com saldo negativo deixa a identidade da movimentação aberta**, e não é erro. A
  saída sai por custo PROVISÓRIO (o último conhecido, ou zero); quando a entrada chega, o médio
  passa a valer para o saldo negativo inteiro e revaloriza o que já tinha saído — uma correção
  legítima que movimento nenhum carrega. Foi por isso que uma entrada de R$ 10 sobre saldo −3
  abriu 30 reais no relatório. A tela nomeia essa causa; a saída é lançar a entrada que faltava.
  ⚠️ Suíte que cria saldo negativo **não pode** lançar entrada nele depois: a base é
  compartilhada, e os cenários que medem a casa inteira acusam a diferença.
- ⚠️ **O rodapé do relatório soma as linhas ARREDONDADAS**, de propósito — o total tem de
  fechar com a coluna que a pessoa confere a mão. Em centenas de produtos isso dá centavos de
  diferença na identidade "inicial + entradas − saídas = final", que **não são erro de razão**.
  A folga acompanha o tamanho do relatório (meio centavo por linha), na tela e nos testes: com
  folga fixa, uma base real acusava "a conta não fecha" toda vez, e alarme que sempre toca
  ninguém escuta.
- ⚠️ **Lista sem total é lista mentirosa.** A tela de compras mostrava as 50 notas mais
  recentes de 3.670 e nada dizia que havia mais — a nota do mês passado simplesmente não
  existia. Toda listagem que pode crescer devolve o total em `X-Total` (helper único em
  `api/paginacao.py`) e ganha busca no SERVIDOR.
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

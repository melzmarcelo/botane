# Estoque, razão e CMV

> Extraído do CLAUDE.md original (seções "O que já existe" e "Armadilhas já pagas").
> Consultar antes de mexer nesta área do sistema.

## O que já existe

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

- ⚠️ **O total sai em consulta SEPARADA e só na primeira página** (`paginacao.pagina`). Medido
  com 400.000 movimentos no razão: página de 100 sem total **4 ms**, com `count(*) OVER ()`
  **388 ms** — a janela obriga o banco a materializar todas as linhas do filtro para depois
  cortar em 100. Virar a página não muda o total, então a conta roda no `offset = 0` e mais
  nada: 148 ms na primeira, **2 ms** nas seguintes. Quando o cabeçalho não vem, `api.listar`
  devolve `total: null` e `usePaginacao.setTotal` **guarda o que já tinha** — tratar nulo como
  zero apagaria o rodapé na página 2. Quem monta a consulta passa o SQL **sem LIMIT**: o total
  usa o mesmo texto e os mesmos parâmetros, e uma cópia do filtro escrita à mão divergiria no
  primeiro `WHERE` novo. As listas limitadas por natureza (fichas, inventários, usuários)
  continuam com `com_total` e `count(*) OVER ()`.

- 🔑 **"Quais são as provisórias?" não tinha resposta** (01/09/2026, pedido do dono). A saída
  que não acha saldo sai por um custo **estimado** e a linha nasce marcada no razão — mas com
  centenas de movimentos a etiqueta só ajuda quem já está olhando para a linha certa. Cada uma
  delas é **uma entrada que ninguém lançou**, e deixa o CMV torto até ser lançada.
  `?apenas_provisorios=true` no razão, caixinha **"só custo provisório"** na tela.
  ⚠️ **Caixinha, não mais um valor no seletor de Movimento**: não é um TIPO de movimento — é
  uma marca que qualquer saída pode ter. Dentro daquela lista pareceria excludente das outras.
  ⚠️ **Lista vazia é a BOA notícia**, e a tela diz isso ("não há entrada faltando"): o
  "nenhum movimento com esses filtros" de sempre faria parecer que o filtro não funcionou.
  ⚠️ **E a lista precisa dizer o que FAZER** — ela é de saídas esperando uma entrada, não de
  erros a corrigir no razão, que é append-only.
  ⚠️ **O ARQUIVO aceita o mesmo filtro**, e ganhou a coluna "Custo provisório" — filtro que
  existe num lado só recria a divergência que o razão exportado existe para não ter. A coluna
  vem **vazia** quando o custo é firme, e não "não": ela é um alerta, e 600 "não" ao lado de 3
  "sim" escondem os três.
  🔑 **Nasceu daí o primeiro filtro de SIM OU NÃO da janela de exportação** (`tipo: "sim_nao"`).
  ⚠️ E `False` sai do que vai para a auditoria **por identidade** (`v is not False`): registrar
  `provisorio: false` em toda exportação é ruído, mas `v not in (None, [], "", False)` levaria
  junto o `dias=0`, que é filtro legítimo — em Python `0 == False`.

- 🔑 **E o razão NÃO filtrava por loja** (01/09/2026). `GET /estoque/movimentos` não tinha
  `id_unidade` no `WHERE` — enquanto o CSV do razão sempre teve. Com duas lojas a tela
  misturava os movimentos das duas e o arquivo baixado trazia só os desta: a divergência exata
  que aquele endpoint documenta querer evitar. Medido na base local: 22 linhas de outras lojas
  numa página de 500. É a mesma dívida que vendas, inventários e locais já pagaram — **toda
  lista de coisa que tem `id_unidade` nasce com ela**, e ela só aparece no dia em que a segunda
  loja existe.

- **O razão filtra por período, produto, tipo e local** (20/08/2026): `GET /estoque/movimentos`
  ganhou `inicio`/`fim`/`busca` (os mesmos nomes do CSV) e a tela ganhou a barra de filtro com
  paginação de 100 por `X-Total`. ⚠️ `fim` é dia **cheio** (`< fim + 1`): `<= fim` cortaria o que
  foi lançado às 14h do próprio dia, porque `data_movimento` guarda data e hora. O CSV aceita os
  mesmos filtros — filtrar na tela e baixar outra coisa faria quem conferisse achar que um dos
  dois mente. Os rótulos dos tipos saem de `GET /estoque/tipos-movimento`, não de uma lista
  copiada no front.

- 🔑 **A folha de UM produto** (`GET /exportar/produto/{id}`, botão **Baixar** em
  `/produtos/[id]`): cadastro, saldo por local, embalagens de compra, quem fornece e os
  **últimos 50** movimentos. A tela junta tudo isso em blocos; quem precisava levar para fora —
  conferir uma compra, discutir preço com o fornecedor, responder ao contador — não tinha como.
  ⚠️ **O bloco de estoque exige `estoque.saldos`.** Saldo, custo médio e razão são dados de
  ESTOQUE e não passam a ser de cadastro por estarem no arquivo de um produto — mesma regra do
  custo na ficha.
  ⚠️ **Os ÚLTIMOS movimentos, não todos**: o razão de um insumo movimentado tem milhares de
  linhas, e quem abre a ficha de um produto quer o que aconteceu com ele agora. O razão inteiro
  tem relatório próprio.
  ⚠️ **Não há quadro principal**: são quatro assuntos do mesmo produto, e promover um deles a
  "a tabela" faria os outros três parecerem apêndice. O bloco principal fica só com título e
  resumo (`colunas=[]`), e cada quadro entra como anexo com o nome dele em cima.
  ⚠️ **Quadro vazio não entra** — produto recém-cadastrado não tem saldo nem fornecedor, e três
  tabelas vazias fazem o arquivo parecer defeituoso. Sem nenhum quadro, uma frase explica.
  ⚠️ O botão fica **fora do `podeEditar`**: baixar é de quem CONSULTA.
  ⚠️ **A ficha sai em RETRATO, e por isso `pdf_de` ganhou `orientacao`.** O corte automático é
  por número de colunas, e está certo para relatório de tabela — lá quem manda é a largura. A
  ficha é outra coisa: um documento com FORMA por convenção. Assim que a receita usava fator de
  correção ela caía em paisagem, e cartão de receita em paisagem não é o papel que se prende no
  armário da cozinha.
  ⚠️ **A coluna "No estoque" só entra quando houve CONVERSÃO de unidade.** Ela existe para o
  caso de a receita pedir 1 CX e o razão baixar 12 PCT; sem conversão é a cópia das duas
  colunas anteriores — e era uma das que empurravam a ficha para paisagem.
  ⚠️ **O custo da LINHA sai em centavos; o unitário, não.** A coluna vinha com "2,375" e
  "1,287" no meio de valores de dois dígitos, e é uma coluna que alguém soma com o dedo. O
  unitário é um PREÇO (R$ por KG) e fica com a precisão que tiver.
  🔑 **E o total do resumo NÃO virou a soma das linhas arredondadas.** Somar a coluna impressa
  dá um centavo a mais que "Custo da receita" — é o centavo que toda coluna arredondada carrega.
  A escolha é deliberada: o resumo mostra o número **autorizado**, o mesmo da tela e do CMV.
  Um relatório que discorda do sistema sobre o custo da receita é pior que um centavo de
  diferença numa soma feita à mão. (⚠️ É o oposto da regra do rodapé dos relatórios de tabela,
  onde o total FECHA com a coluna — lá o total é do próprio relatório; aqui ele é de fora.)
  ⚠️ `components/filtro-multiplo.tsx` saiu de dentro de `/inventario/novo` quando a exportação
  passou a precisar do mesmo controle; ganhou **busca dentro da lista** acima de 12 opções
  (99 locais e 70 categorias numa base real).

- Manuais: `docs/manual-da-equipe.md` (o que cada função faz no dia a dia) e
  **`web/public/ajuda.html`** — o manual de referência: os treze processos e o caminho do dado,
  de onde entra até virar número.
  🔑 **A seção "De onde vem cada número" é o coração dele** (28/08/2026): segue UM quilo de
  café da nota até a variância, com a aritmética real em cada passo — custo de aquisição com
  frete rateado, custo médio ponderado (e por que a média simples erraria R$ 0,92/kg), ficha,
  custo congelado no item de venda, CMV real pela fotografia do razão, e a variância fechando
  **exatamente** com a perda apontada. Fecha com a tabela "cada número e sua origem" e com o
  que ENFRAQUECE cada um (produto sem unidade, prato sem ficha, venda sem vínculo). Quem
  confere um relatório sem saber a origem do valor acaba aceitando o que está lá. ⚠️ **Fonte única**: a tela `/ajuda` o exibe num quadro que
  cresce até a altura do conteúdo, e o mesmo arquivo é o que se publica como artifact
  (republicar sempre com a mesma URL). Reescrevê-lo em JSX criaria duas versões que divergem
  no primeiro parágrafo novo — e aí o sistema explicaria duas coisas diferentes sobre si.

- **O que falta na primeira parte está em [`docs/o-que-falta.md`](docs/o-que-falta.md)** —
  levantado em 25/08/2026 comparando o MAPEAMENTO item a item com o que existe. O maior item
  é a **carga inicial das fichas**: com zero fichas não há CMV teórico, nem variância, nem
  food cost. O documento também registra as três decisões em que a construção divergiu do
  mapeamento e por quê (a venda passou a baixar estoque, `modo_producao`, `KIT`).

- ⚠️ **Produto ATIVO sem unidade de estoque também devolvia 500.** A trava é do banco
  (`ck_produto_rascunho`) e é a certa — quantidade sem unidade não decide custo nenhum —, mas
  vazava como "Internal Server Error" para quem cadastrava um prato sem escolher unidade.
  Virou 400 com frase, e a saída ("salve como rascunho") vai junto. ⚠️ Ao adicionar validação
  que consulta uma coluna, **o `SELECT` do "antes" no PUT precisa trazê-la**: sem `um_estoque`
  ali, um PUT que só mudava o preço levava 400 sem ter tocado no assunto.

- ⚠️ **Tabela nova que aponta para as tabelas limpas derruba `limpar_dados.py`** — e a
  mensagem do Postgres passa longe de "atualize a lista do script". Aconteceu com
  `produto_unidades` e com `cmv_movimentacao`: a limpeza estourava no meio e quem rodou achava
  que tinha limpado. O script agora **confere antes** (`referenciam()`) e recusa nomeando o que
  falta na lista.

- 🔑 **`--filiais-de-teste` na limpeza** (01/09/2026): as suítes criam uma loja por rodada e
  ninguém as apagava — `unidades` está em `PRESERVADAS`, e numa casa de verdade a loja fica.
  Dezenove tinham se acumulado. Não é só sujeira de lista: **filial ATIVA muda a barra
  superior**, porque o seletor de loja aparece e vira o primeiro `<select>` do documento.
  ⚠️ **O critério é estar INATIVA, não o nome.** As suítes desativam a filial delas no
  `atexit`, então "inativa" é exatamente a marca que elas deixam; casar por nome seria o
  palpite que este projeto já removeu uma vez. A matriz nunca entra.
  ⚠️ Roda **depois** do TRUNCATE: com movimento, venda ou nota apontando para a loja, a
  exclusão bate na chave estrangeira.
  ⚠️ Locais, setores e categorias com marca de suíte continuam saindo **na mão** —
  `--tabelas-de-apoio` esvazia tudo, inclusive o que a casa usa.

- **Tela inicial = painel do dono** (20/08/2026): `routers/inicio.py` entrega tudo numa
  chamada só — painel que faz seis requisições pisca seis vezes. ⚠️ **Número verdadeiro ou
  nenhum**: sem venda importada, `food_cost_pct` e `variancia` vão como `null` (não 0) e a
  tela mostra "—" com o motivo; zero ali pareceria um resultado excelente. Dinheiro só sai
  com `cmv.painel` — quem não tem recebe `dinheiro: null`, não um valor zerado. A cobertura
  de ficha viaja junto porque é ela que diz o quanto dá para confiar na variância.

- **Filtrar ≠ escolher** (`FiltroCadastro`): nos saldos e no razão o texto continua filtrando
  solto ("café" traz os cinco), e a **lupa FIXA** um produto — que vira etiqueta com ×, para
  ninguém achar que a lista está curta por acaso. Fixado manda `id_produto`; texto manda
  `busca`. Na **contagem de inventário** o filtro é só texto e local: a lista já está na tela e
  é ela que se percorre — abrir janela para escolher um item seria perder a contagem de vista.
  ⚠️ O impacto previsto soma **todos** os itens, nunca os filtrados.

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

- **Consultar e lançar são telas separadas** (21/08/2026): entrada, saída, perda e
  transferência eram quatro botões no cabeçalho de `/estoque`, que é onde se CONSULTA.
  Viraram **Estoque ▸ Ajustes** (`/ajustes`): escolhe-se o tipo e o formulário se molda a ele.
  Depois de lançar o formulário **fica aberto e limpo** — quem ajusta um item ajusta o
  próximo. ⚠️ O item de menu aceita **lista** de chaves (`chave: string | string[]`): Ajustes
  serve a quatro permissões e quem só tem a de perda também precisa chegar nele.

- 🔑 **O custo inicial vindo do Omie** (migração 049, `importador.custos_iniciais`, botão
  **Trazer o custo inicial** em Integrações, 01/09/2026, pedido do dono). Medido na base:
  **2.323 produtos ativos que controlam estoque estavam sem custo NENHUM** — nunca entrou nota
  deles aqui e não há preço de fornecedor. Sem custo não há ficha, nem CMV teórico, nem margem:
  o prato entra na conta **valendo zero** e o food cost sai bom demais, sem nada denunciando. O
  Omie já sabe o número (o CMC da posição de estoque), e a tela só sabia COMPARAR os dois.
  🔑 **É REFERÊNCIA, não movimento — e essa é a decisão que importa.** Nada entra no razão e
  nenhum saldo muda: o CMV real continua saindo do que a casa comprou e contou. Como movimento,
  2.323 linhas erradas entrariam no CMV do período da carga e **não se apagariam** — o razão é
  append-only, e a única saída seria estornar 2.323 movimentos.
  ⚠️ **`produtos.custo_referencia` é o ÚLTIMO degrau de `custos.custo_do_insumo`**, depois do
  médio do razão e do último preço do fornecedor. A ordem é a da confiança: o médio é o que a
  casa pagou com o frete DELA rateado dentro; o preço do fornecedor é o que ela negociou; a
  referência é o que outro sistema acha — melhor que nada e pior que os dois.
  ⚠️ **Só quem NÃO tem custo**, e rodar de novo só alcança quem continua sem. Referência
  sobrescreve referência; custo de verdade, nunca.
  ⚠️ **CMC zero é PULADO.** Zero não é um custo: é o Omie dizendo que não sabe, e gravá-lo faria
  a ficha calcular com um número inventado — pior que calcular sem, porque o aviso de
  "sem_custo" some.
  ⚠️ **`custo_referencia_origem` existe para daqui a seis meses**: sem ela ninguém sabe se
  aquele número foi importado ou digitado, e é essa diferença que decide se ele pode ser
  sobrescrito sem perguntar.
  ⚠️ **A prévia vem antes, sempre** (`GET /omie/custos-iniciais/previa`): mesma varredura, sem
  gravar. Com 2.323 produtos, descobrir o efeito depois é tarde. E o de-para é
  `vinculo.por_codigo_omie` — a coluna e depois os apelidos, senão o principal que absorveu um
  duplicado ficaria de fora.
  ⚠️ **A suíte provava a precedência lançando uma ENTRADA no produto da conferência** — e o
  razão é append-only: o saldo ficava lá e a rodada seguinte falhava em "o saldo daqui é zero",
  acusando um defeito que não existia. Agora ela usa produto próprio e escreve o
  `custo_referencia` direto. **Teste que deixa rastro derruba a próxima; aqui o rastro seria
  permanente.**

- ⚠️ **Produto sem `um_estoque` NÃO entra no razão** (`lancar_nota`). Quantidade sem unidade é
  número sem significado — "3" de champignon não diz se são três bandejas ou três quilos —, e o
  custo médio que sair daí contamina ficha, CMV e a próxima compra. O catálogo do Omie cria
  rascunho sem unidade de propósito (a sigla do fornecedor pode não existir na casa); é no
  lançamento que a dívida é cobrada, e a recusa **nomeia todos** os produtos de uma vez.

- ⚠️ **Cópia congelada acompanha a largura da ORIGEM.** `cmv_movimentacao.codigo` era
  `varchar(20)` contra `produtos.codigo varchar(40)`: **fechar o mês estourava com 500** assim
  que a base tinha um código real de 40 caracteres. Migração 026. É a terceira vez que largura
  de coluna quebra com dado de verdade (catálogo do Omie e NCM foram as outras).

- 🔑 **Transferência ENTRE LOJAS: dois movimentos ligados, cada um na sua loja** (31/08/2026,
  decisão do dono). `transferir` recebia UMA loja e dois locais: escolhendo um local da outra,
  o razão gravava saída e entrada sob a loja de quem estava na tela — o saldo das duas ficava
  errado e **nada denunciava**. Agora cada lado é lançado na loja do seu próprio local.
  🔑 **O custo ATRAVESSA a fronteira**: a entrada usa o `custo_unitario` que a saída apurou (o
  médio da origem). É isso que faz a origem perder exatamente o valor que o destino ganha.
  ⚠️ **Quem não enxerga a loja não empurra mercadoria para dentro dela** — a transferência toca
  DUAS, e mandar para uma loja que a pessoa não vê seria mexer num estoque que ela não pode nem
  consultar. Validado com o mesmo `ve_unidade`.
  ⚠️ **`/locais?todas_lojas=true` nasceu por causa disso**: o destino pode ser a prateleira da
  outra loja, e `/locais` tinha acabado de passar a filtrar pela atual. O nome da loja vem
  junto, senão a lista mostraria dois "Estoque".
  🔑 **E a remessa ENTRA na apuração como compra do destino e compra negativa da origem.**
  Dentro de uma loja a transferência se anula e por isso nunca contou como compra; entre lojas
  ela NÃO se anula — o destino recebe mercadoria que não comprou (CMV **negativo**) e a origem
  perde mercadoria que não vendeu (CMV inchado). Quem mostrou foi a TELA da rede: a filial que
  só recebeu uma remessa aparecia com **CMV de −R$ 160,00**. Somando de um lado e subtraindo do
  outro, as duas fecham e o total da rede não muda.
  ⚠️ **E isso quebrou a identidade "a soma dos grupos é o CMV do período"** em R$ 1.120,00: o
  relatório por grupo não conhecia a remessa. Ela entrou em TRÊS lugares da consulta — a coluna
  de compras, a expressão do **CMV** (esquecê-la ali manteve a diferença na primeira tentativa)
  e o `HAVING`, senão um grupo cujo único movimento fosse uma remessa sumiria da lista.
  ⚠️ A checagem do CMV da filial tem folga de **um centavo**: o custo unitário tem 6 casas e a
  conta encadeia entrada, saída e estoque — o resíduo é de milionésimos de real.

- 🔑 **A remessa: entre lojas a mercadoria leva TEMPO no caminho, e agora alguém confere na
  chegada** (migração 047, `services/transferencias.py`, tela **Estoque ▸ Remessas entre
  lojas**, 31/08/2026, pedido do dono). Saída e entrada eram gravadas na mesma transação: o
  carro saía hoje e chegava amanhã, e a filial já aparecia com o produto na prateleira. Pior,
  **quem recebia não conferia nada** — chegando menos, a diferença só apareceria na contagem
  seguinte como *ajuste de inventário*, que é exatamente onde a diferença some sem nome.
  🔑 **A decisão difícil não é a tela, é de QUEM É O VALOR no caminho.** Dar baixa no envio e
  entrada só no recebimento faria o valor **desaparecer das duas lojas** nesse intervalo,
  inflando o CMV da origem — um buraco que nenhum relatório explicaria. Por isso **o envio não
  escreve no razão**: a quantidade continua contando no estoque da ORIGEM, marcada como em
  trânsito, e os dois movimentos nascem juntos no recebimento, como sempre nasceram. A
  identidade `inicial + entradas − saídas = final` continua fechando nas duas em qualquer data
  de corte, e o dinheiro nunca fica sem dono.
  ⚠️ **Dentro da MESMA loja nada muda** — prateleira para prateleira alguém carrega a caixa.
  Continua imediata, e `POST /estoque/transferencias` é quem **ramifica**: mesma loja lança na
  hora, lojas diferentes criam a remessa. A frase de sucesso vem do servidor porque as duas
  coisas são diferentes, e escrevê-la no navegador seria repetir a regra lá.
  🔑 **O que não chegou vira PERDA na ORIGEM, não sobra de saldo.** A mercadoria saiu da
  prateleira do mesmo jeito; transferir só o que chegou deixaria a origem com um saldo que ela
  não tem, e a contagem seguinte cobriria o buraco como ajuste anônimo. Como perda ela tem
  nome, dono e uma linha própria no CMV de quem mandou. O recebimento parcial pede o motivo.
  ⚠️ **Nulo e zero são afirmações diferentes** em `qtd_recebida`: nulo é "ainda não conferido"
  (e, no corpo do recebimento, "chegou o que foi mandado" — o caso comum não se digita); zero é
  "conferi e não veio nada".
  ⚠️ **O custo é o do RECEBIMENTO, não o do envio.** A mercadoria foi da origem até chegar,
  então quem responde por ela é o médio da origem no dia em que ela sai de lá. Congelar no
  envio criaria um terceiro número, que não seria nem de quem mandou nem de quem recebeu.
  🔑 **Os dois movimentos apontam UM PARA O OUTRO, não para a remessa** — e isso quase virou um
  defeito calado. `_transferencia_entre_lojas` acha o outro lado com
  `JOIN estoque_movimentos o ON o.id = m.origem_id` para saber se a mercadoria atravessou a
  fronteira; pôr ali o id da remessa faria o JOIN cair num movimento QUALQUER de mesmo número, e
  o CMV das duas lojas passaria a depender de uma coincidência de numeração. Quem liga o
  movimento à remessa é `transferencia_itens`. Pela mesma razão a perda usa
  **`origem_tipo = 'REMESSA'`**: naquele vocabulário `origem_id` é um movimento, e aqui não há
  outro lado.
  ⚠️ **Cancelar não estorna nada, porque nada foi lançado** — é a vantagem silenciosa deste
  desenho, e a frase diz isso: quem cancela espera ter de consertar o razão. Depois de recebida
  não há cancelamento, só estorno dos movimentos.
  🔑 **Quem recebe é o DESTINO, e a pergunta é a LOJA ATUAL — não `ve_unidade`.** A primeira
  versão usou a visibilidade, e o administrador vê todas: com ele a trava **não travava nada**, e
  quem despachou daria entrada na outra loja sem ninguém ter conferido — que é o processo inteiro
  que o recebimento existe para impedir. A loja atual é a do seletor do topo. A frase nomeia a
  loja e manda trocar, senão um 403 seco deixa a pessoa procurando permissão que ela já tem.
  ⚠️ **`estoque.transferencia_receber` é a chave NOVA, não a de enviar** — quem transferia ontem
  continua transferindo e ganha o recebimento de graça. Invertida, o deploy tiraria de todo mundo
  uma coisa que já fazia. Mesma escolha do inventário (045).
  ⚠️ **A lista mostra os DOIS lados da loja atual** — o que ela mandou e o que ela espera.
  Filtrar só pela origem esconderia da filial justamente a remessa que ela precisa receber; a
  etiqueta "a receber" é que separa as duas.
  ⚠️ **O saldo da origem DIZ quanto já está na estrada** (`em_transito` em `/estoque/saldos`).
  Sem isso o "continua contando" vira armadilha: quem olha o saldo da matriz vê mercadoria que
  já está no carro e despacha de novo. Vem de **uma consulta só**, casada em memória — 200 linhas
  por página contra um punhado de remessas abertas, e correlacionar cobraria o preço em toda
  listagem de saldo por causa de um caso que quase sempre vem vazio.
  ⚠️ O item de menu só aparece **com mais de uma loja**: numa casa só, remessa não existe.

- 🔑 **O açúcar em vários setores: o local ganhou um SETOR** (migração 051, 01/09/2026, processo
  descrito pelo dono). O fluxo real: o açúcar entra no **Estoque Central**, e de manhã cada
  setor leva um pacote para o seu canto — Bar, Confeitaria, Cozinha, Cafeteria. Durante a
  semana cada um gasta do que pegou; no fim, **cada setor conta o seu estoque**.
  🔑 **O que ele chama de "setor" nesse fluxo é, no vocabulário do sistema, um LOCAL** — o teste
  é o comportamento: guarda mercadoria, recebe transferência e é contado num inventário próprio.
  Modelando assim, a transferência da manhã, o inventário por setor e o saldo por setor
  funcionam com o que **já existe** — e o "um produto pode ter vários setores" deixa de ser
  problema: ele não precisa de vários setores, ele tem **saldo em vários locais**
  (`estoque_saldos` é por local).
  ⚠️ **NULO é resposta legítima e é o padrão**: o Estoque Central não pertence a setor nenhum,
  ele serve a todos. Exigir setor em todo local obrigaria a inventar um para a despensa, e setor
  inventado suja o relatório que a coluna existe para melhorar.
  ⚠️ `ON DELETE SET NULL`: apagar um setor não pode levar junto a prateleira, que guarda saldo e
  razão. Perder a classificação é o custo certo; perder o local, não.
  🔑 **A produção passou a sair de ONDE SE PRODUZ** (`estoque._de_onde_sai`). Sem isso, o pacote
  que a Confeitaria pegou de manhã nunca baixava, e a contagem do fim da semana acusava uma
  sobra que não existe.
  ⚠️ **Mas só quando há saldo lá** — e a reserva não é conveniência. A regra anterior (cada
  insumo sai do local DELE) existe por um caso igualmente real: uma receita usa leite da câmara
  e café do seco ao mesmo tempo. Forçar tudo no local de quem produz faria a saída bater num
  lugar por onde o insumo nunca passou, com saldo negativo e **custo provisório contaminando o
  custo do prato** — que é justamente o número que a produção existe para apurar. A ordem é: o
  local de quem produz primeiro, o local do produto como reserva.
  ⚠️ **Pergunta pelo SALDO do dia, não pelo cadastro**: se a Confeitaria tem açúcar, sai de lá;
  se acabou no meio da tarde, sai do central. Decidir pelo cadastro faria a produção falhar
  justamente no dia em que o pacote da manhã acabou.
  ⚠️ **A folha da previsão resolve o local do MESMO jeito.** Prever com outra regra seria prever
  outra coisa: ela diria que falta açúcar no central enquanto a produção o tiraria da
  Confeitaria, e quem lesse iria comprar o que já tem.
  🔑 **`GET /estoque/saldos-agrupados`, e a tela escolhe a granularidade**: prateleira ("onde
  está" — o que quem conta precisa), produto ("quanto a loja tem" — o que quem compra precisa)
  e empresa. Um seletor, não duas caixinhas: duas fariam quatro combinações, duas delas sem
  sentido. ⚠️ O corte por setor ali é pelo setor do **LOCAL**, não pelo do produto — a pergunta
  é "o que a Confeitaria tem na mão", e quem responde é onde a mercadoria está.
  🔑 **E o CMV por setor passou a sair do LOCAL do movimento** (02/09/2026), fechando o
  desenho. Enquanto ele agrupava por `produtos.id_setor` — um setor só —, **todo o consumo de
  açúcar era atribuído a um deles**, e a resposta para *"a confeitaria está pesando mais que o
  bar?"* era ficção. Quem sabe de onde a mercadoria saiu é o MOVIMENTO, e ele guarda `id_local`
  desde sempre.
  🔑 **O grão da conta virou `(produto, LOCAL)`, e é isso que preserva a identidade.** Somar é
  associativo: agregar no grão fino e enrolar depois pelo grupo dá exatamente os mesmos totais
  que agregar por produto — então `categoria` e `grupo`, que são atributos do PRODUTO, **não
  mudam um centavo**, e *a soma dos grupos fecha com o CMV do período* continua valendo. Era o
  risco inteiro da mudança, e a suíte cobra as duas coisas.
  ⚠️ **A reserva é o setor do PRODUTO, não "Sem setor"**: o Estoque Central não pertence a setor
  nenhum, e sem a reserva toda casa que ainda não classificou as prateleiras veria o relatório
  inteiro virar uma linha só. Quem não configurou nada continua vendo exatamente o que via.
  ⚠️ **A checagem afirma a PROPRIEDADE, não um número calculado de cabeça.** A primeira versão
  esperava R$ 11,00 da saída do central e esqueceu que a ENTRADA de lá também é compra — o CMV
  daquele pedaço é `20 − 15 = 5`. O que importa provar é que o movimento engordou a linha do
  setor do produto em vez de criar uma linha "Sem setor".

- 🔑 **As prateleiras do produto entram no CADASTRO** (`GET/POST/DELETE /produtos/{id}/locais`,
  cartão "Onde este produto fica", 02/09/2026, pedido do dono). O cadastro só tinha o local
  **padrão** — aquele por onde o produto ENTRA. Os demais só passavam a existir na primeira
  transferência: o canto do Bar não existia até alguém levar o primeiro pacote para lá. Não
  havia como preparar a casa antes de operar, nem como ver de relance em quantos cantos o mesmo
  açúcar mora, com quanto e a que custo em cada um.
  🔑 **Não há tabela nova, e a razão é que ela já existe**: `estoque_saldos` É a relação
  `(loja, local, produto)`, e uma linha com quantidade **ZERO** diz exatamente *"mora aqui,
  vazio no momento"* — que é o que faltava poder declarar. Uma segunda tabela para dizer a
  mesma coisa daria duas versões da mesma verdade, e elas divergiriam no primeiro movimento.
  Acrescentar é o `INSERT ... ON CONFLICT DO NOTHING` que `_travar_saldo` já fazia.
  ⚠️ **Declarar NÃO lança nada no razão** — e a suíte cobra isso contando os movimentos antes e
  depois. A prateleira passa a existir vazia, pronta para receber a transferência e para entrar
  na contagem; se declarar movimentasse, o cadastro estaria inventando estoque.
  ⚠️ **Tirar só com a prateleira VAZIA** (409 com frase que diz o quanto tem e o que fazer).
  Apagar a linha de um produto com mercadoria ali faria o saldo sumir da vista sem um movimento
  explicando — e o razão é a única memória do custo. Quem quer esvaziar transfere ou lança a
  saída; aí a linha fica em zero e pode sair.
  ⚠️ **O razão da prateleira FICA depois de ela sair do cadastro.** Tirar o local é cadastro,
  não correção de movimento — `estoque_movimentos` é append-only, e o que aconteceu lá aconteceu.
  ⚠️ **Repetir responde 200, não 201.** Nada foi criado, e dizer 201 ali afirmaria que sim; a
  frase diz qual dos dois casos foi ("passa a ser" / "já era").
  ⚠️ **Sai da loja ATUAL**: prateleira é da loja, e somar as duas no cadastro mostraria dois
  "ESTOQUE" sem dizer de quem é cada um. O setor da prateleira vem junto — é ele que separa o
  canto da Confeitaria do estoque geral.
  ⚠️ O custo médio e o valor pedem **`estoque.saldos`**, como na ficha: são dados de ESTOQUE, e
  não passam a ser de cadastro por estarem na tela do produto.
  ⚠️ E o cartão só aparece para quem **controla estoque** — produto que não controla não tem
  prateleira nenhuma.
  🔑 **O cartão aparece TAMBÉM na tela de CRIAR** (02/09/2026, pedido do dono). A primeira
  versão o escondia ali, com a justificativa de que o produto não tem id e a linha de saldo não
  teria para onde apontar. Só que é EXATAMENTE ali que a pessoa está decidindo onde o produto
  vai morar — e o dono queria justamente "não precisar criar o local só na transferência". As
  prateleiras escolhidas ficam no estado e sobem logo depois do `POST /produtos`, com prévia da
  lista montada. **É o mesmo caminho da foto da ficha**, e pela mesma razão: campo que não
  aparece na hora do cadastro é campo que a pessoa conclui que não existe.
  ⚠️ **Falhar ao gravar as prateleiras NÃO é "não foi possível salvar"**: o produto já existe
  daquele ponto em diante, e a frase genérica mandaria cadastrar tudo de novo — criando um
  segundo cadastro do mesmo item. A mensagem diz quantas não foram e onde acrescentá-las.
  ⚠️ **Na criação a tabela não mostra saldo, custo nem valor**: não há nenhum, e uma coluna de
  zeros afirma que há.

- ⚠️ **Identidade que soma a lista INTEIRA precisa varrer a lista inteira** (02/09/2026). A
  checagem da conciliação do estoque da rede pedia `limite=1000`, que é o **teto** do endpoint:
  assim que a base passou de mil produtos com saldo, ela lia 1.000 de 1.065 e acusava a conta de
  não fechar — um defeito que só existia no teste, e que apareceria sozinho num dia qualquer,
  longe de qualquer commit. Agora ela **pagina** até acabar. É a mesma família do "relatório
  cortado no topo esconde o registro que se procura".

- 🔑 **O estoque da EMPRESA: `GET /estoque/saldos-rede`** (01/09/2026, pedido do dono). A tela
  da rede dizia quanto **VALE** o estoque da empresa e não dizia **de quê** — para conferir um
  item era preciso trocar de loja no seletor e somar de cabeça, que é exatamente a conta que a
  visão consolidada existe para evitar. Interruptor **"somar todas as lojas"** na aba de saldos
  de `/estoque`, só com mais de uma loja.
  ⚠️ **A linha vira o PRODUTO e a prateleira sai.** Agrupar por local devolveria a mesma lista
  de sempre, só que mais longa; onde ele está vem em `por_loja`, uma coluna por loja. O filtro
  de local **some** da barra nesse modo — seletor que não corta nada é promessa falsa.
  🔑 **O custo médio da rede é PONDERADO, nunca a média dos médios.** Matriz com 10 kg a R$ 40 e
  filial com 1 kg a R$ 52 dão **R$ 41,09**, não R$ 46 — a média simples daria o mesmo peso ao
  estoque grande e ao pequeno. É a mesma lição do food cost da rede.
  🔑 **Só as lojas que a pessoa ENXERGA entram na soma**, e essa é a trava que mais importa
  aqui: somar uma loja que ela não pode consultar entregaria pelo **total** justamente o que o
  `ve_unidade` esconde — e o total é o pior lugar para vazar, porque nada na tela denuncia um
  número maior do que devia. `smoke_lojas_do_usuario` cobra que quem só vê a filial some só a
  filial, na quantidade **e** no valor.
  ⚠️ **Transferência em trânsito não aparece**: entre lojas ela é movimento INTERNO da rede, a
  mercadoria continua contando na origem e o total não muda. Mostrá-la sugeriria que parte do
  estoque da empresa está fora dela.
  ⚠️ **Traço, não zero**, na coluna de uma loja sem aquele produto: "não tem linha aqui" e "tem
  zero" se leem igual e só o segundo é um saldo.
  ⚠️ **O relatório `saldos-rede` some do catálogo com uma loja só** — ali ele é o de sempre com
  uma coluna a mais, e oferecer os dois lado a lado faria escolher entre duas versões da mesma
  coisa. As lojas visíveis chegam ao montador por `_com_as_lojas`, num parâmetro `_lojas` com
  underscore: é INTERNO, não um filtro que a janela oferece — `exportacao_catalogo` não conhece
  `ve_unidade`, e resolver a lista lá dentro somaria o que a pessoa não pode ver.
  ⚠️ **O total do cartão de saldos somava a PÁGINA e se chamava "valor em estoque"** — a mentira
  que a casa já pagou noutra tela. Agora o rótulo diz qual das duas coisas é: "valor nesta
  página" quando há mais de uma.
  ⚠️ **A rede com ZERO daquele item derrubava a lista INTEIRA com 500.** O custo médio da rede
  é uma divisão pela quantidade — com o saldo zerado ele não existe —, e o modelo de resposta
  exigia `float`. O caminho é o comum (desmarcar "só com saldo"), e o que morria era a resposta
  da PÁGINA, não daquela linha: a tela ficava vazia sem dizer por quê. Agora ele é **nulo**, e
  a tela mostra traço — zero não serve, porque "não custa nada" e "não há nada para custar" se
  leem igual e só o primeiro é um custo.
  🔑 **O painel da rede e a lista consolidada NÃO fechavam, e nada dizia por quê**
  (`GET /estoque/saldos-rede/inativos`, 01/09/2026). Medido na base local: o painel dizia
  R$ 34.893,38 e a lista somava R$ 9.984,88 — **R$ 24.908,50 em 162 produtos INATIVOS que ainda
  têm saldo**. As duas regras estão certas e são antigas: o painel soma `estoque_saldos` inteiro
  (tirar o inativo do estoque final inflaria o CMV) e a lista de saldos filtra por ativo desde
  sempre, aqui e na visão de uma loja só. O que mudou é que passou a existir uma tela que
  **promete explicar** aquele total — e explicava menos de um terço dele. Agora a lista diz
  quanto ficou de fora, com a caixinha para incluí-los; com ela marcada os dois fecham ao
  centavo, e a suíte cobra essa identidade.
  ⚠️ **O aviso segue os MESMOS filtros da lista** — busca, produto e "só com saldo". Número que
  responde por outro recorte é pior que número nenhum: diria "e mais R$ 24 mil" com um produto
  só na tela. Por isso ele é do servidor, não uma conta escrita na tela.
  ⚠️ **E só as lojas que a pessoa enxerga**, como a lista: o aviso é um TOTAL, e total é o pior
  lugar para vazar — nada nele denuncia um número maior do que devia.
  ⚠️ **Endpoint próprio em vez de mais um cabeçalho.** `X-Total` é o padrão da casa para isso,
  mas ele passa por `api.listar`, que serve a TODA lista do sistema: alargar o contrato dele
  por causa de uma tela sairia caro em todas as outras. ⚠️ A mesma divergência existe entre
  `/inicio` e `/estoque` numa loja só — lá continua sem aviso, de propósito, porque ali a lista
  nunca prometeu explicar o painel.

- 🔑 **A visão da REDE** (`GET /inicio/rede` + tela `/rede`, 31/08/2026). Toda outra tela
  responde por UMA loja, e está certo: quem opera opera numa de cada vez. Mas o dono de duas
  não tinha onde ver as duas — e somar de cabeça dois food costs de bases diferentes é a conta
  que ninguém faz certo.
  ⚠️ **Roda a MESMA `apurar` de cada loja, uma por vez** — nunca uma consulta nova que soma
  tudo. Uma segunda implementação divergiria no primeiro caso de borda (ciclo diferente, grupo
  fora do CMV configurado só numa delas), e o consolidado passaria a discordar do painel de
  cada uma. Assim, **se a soma não bate, o erro está numa das partes**.
  🔑 **O food cost da rede se RECALCULA, não se soma**: média de percentuais dá o mesmo peso à
  loja que vendeu R$ 100 mil e à que vendeu R$ 5 mil — e erra justamente para quem tem uma
  grande e uma pequena, que é o caso de quem abre a segunda. A tela diz isso, porque quem
  confere com a calculadora acharia outro número.
  ⚠️ **Cada loja declara o SEU período** (uma pode fechar por semana e a outra por mês), e a
  tela avisa quando eles diferem. ⚠️ Só as lojas que a pessoa ENXERGA entram, e sem
  `cmv.painel` a tela não abre.
  ⚠️ **O item de menu só aparece com MAIS DE UMA loja** (`soComVariasLojas`): com uma só, a
  visão da rede é o Início repetido, e item de menu que leva a tela redundante ensina a
  ignorar o menu.

- 📄 **O estudo da SEGUNDA LOJA está em [`docs/segunda-loja.md`](docs/segunda-loja.md)**
  (30/08/2026), com a ordem aprovada. 🔑 O achado que manda: **`custos.custo_do_insumo` faz a
  média de `estoque_saldos` sem filtrar `id_unidade`** — com duas lojas, o insumo que uma
  comprou a R$ 40 e a outra a R$ 52 passa a valer R$ 45,30 nas duas, contaminando ficha, CMV
  teórico, margem e food cost. É silencioso, e o custo do item de venda é CONGELADO: o erro
  fica gravado. Também não há transferência entre lojas, e a loja nova nasce sem local.

- ⚠️ **Comparar a tela FILTRADA com a API inteira acusa de defeito o comportamento certo.**
  A checagem do aviso "quanto ficou de fora por estar inativo" lia o texto com a busca de um
  produto preenchida e o comparava com `/estoque/saldos-rede/inativos` **sem filtro**: a API
  dizia 181 produtos, a tela dizia nada — e ela estava certa, porque o aviso obedece à busca,
  que é exatamente o que ele tem de fazer. Ou se limpa o filtro antes de medir, ou se pergunta
  à API pelo MESMO recorte. É a família do "teste que descreve o estado do dia", pela ponta do
  recorte em vez da do tempo.

- ⚠️ **Navegar com um parâmetro de URL que a tela não lê mede a tela errada.** A checagem do
  saldo em trânsito abria `/estoque?id_produto=…` — o filtro daquela tela é ESTADO dela, não
  query string, e o teste media a primeira página do cadastro inteiro. Digitar no campo é o
  único caminho que existe de verdade.

- **Movimentação do estoque por produto** (`cmv.movimentacao_por_produto`, migração 018,
  21/08/2026): estoque inicial, entradas, saídas e estoque final de cada produto — a conta que
  EXPLICA o CMV, que é uma linha só. Aba em `/cmv` e planilha em `/exportar/movimentacao.csv`.
  ⚠️ O saldo inicial e o final saem da **fotografia do razão** (`saldo_apos` ×
  `custo_medio_apos`), não de somar entradas menos saídas: a quantidade daria igual e o
  **valor** não, porque o médio muda a cada entrada. ⚠️ Entradas e saídas aqui são **todas**
  (produção, transferência e ajuste inclusive) — a soma que vira CMV continua sendo só a de
  compras; são perguntas diferentes.

- **`services/relatorios.py`** (19/08/2026): os dois relatórios do dono. `cmv_por_grupo`
  quebra a MESMA conta do CMV por setor ou categoria — **não é rateio**, e a soma dos grupos
  fecha com o CMV do período (o teste confere isso). Produto sem grupo aparece como "Sem
  setor" em vez de sumir na junção. `evolucao_de_preco` ordena pelo **impacto em reais**, não
  pelo percentual: 8% num item semanal dói mais que 60% num trimestral. Base é o **custo de
  aquisição** (frete dentro), não o valor de tabela.

- **O fechamento tem três ritmos** (`services/periodos.py`, migração 028, 25/08/2026):
  `MENSAL` (o padrão e o de sempre), `SEMANAL` (escolhendo o dia em que a semana fecha) e
  `DIARIO`. A casa que viu a apresentação fecha o CMV toda **semana** — mês é o ritmo do
  contador, e uma variância que só aparece no dia 30 chega tarde para virar decisão. Escolhe-se
  em `parametros.ciclo_fechamento` + `fechamento_dia_semana` (ISO: 1 = segunda, 7 = domingo).
  ⚠️ **A pergunta "que período é este dia?" é feita num lugar só.** O mês estava escrito por
  dentro de quatro: o fechamento, o painel de CMV, a tela inicial e a frase com que o razão
  recusa lançamento. Trocar o ritmo em um deles faria o sistema discordar de si mesmo.
  ⚠️ **`dia_fechamento_cmv` era campo MORTO** — estava na tela de Lojas e ninguém lia. Virou o
  dia em que o mês do CMV COMEÇA: 1 dá o mês do calendário (idêntico ao de antes), 26 dá o
  ciclo 26/07–25/08 de quem fecha junto com o fornecedor. Limitado a 28: dia 30 não existe em
  fevereiro, e período de tamanho variável não compara com o anterior.
  ⚠️ **Período que ainda não terminou não fecha.** A conferência antiga (`competencia > mês
  corrente`) deixava fechar o mês CORRENTE: no dia 25, congelar agosto travava os seis dias que
  ainda iam acontecer. O corte é `fim > hoje`, e não `>=`, porque o dia do fechamento pertence
  ao período que ele encerra — recusar o último dia deixaria a casa sempre um período atrasada.
  ⚠️ **Períodos fechados não se sobrepõem** (409 nomeando o outro): quem fechava por mês e passa
  a fechar por semana teria dois congelados dizendo coisas diferentes sobre os mesmos dias.
  ⚠️ `cmv_fechamentos.ciclo` entra na unicidade (`ux_fechamento_ciclo`) — sem ele a semana que
  começa no dia 1 colidiria com o mês que começa no dia 1, e o `ON CONFLICT` sobrescreveria um
  com o outro em silêncio.
  ⚠️ **O nome do período vem do SERVIDOR** (`periodos.rotulo`), nunca remontado no front: só a
  coluna `ciclo` sabe se "01/08" é o mês de agosto ou a semana que começou nele. E o nome curto
  ("agosto de 2026") só vale para o período INTEIRO — um recorte que para no dia 25 mostra as
  duas pontas, senão manda-se ao contador um pedaço achando que é o mês.
  ⚠️ A tela de Lojas mostra a prévia do calendário **pedindo ao servidor**
  (`GET /unidades/{id}/parametros/previa-fechamento`), com os valores do formulário e sem
  salvar: semana que fecha na quarta, mês que começa no 26 e dia corrido são três aritméticas,
  e uma segunda implementação em TypeScript divergiria no primeiro caso de borda — aparecendo
  como fechamento no período errado, que só se desfaz reabrindo.

- **A casa monta os próprios grupos do CMV, por TIPO de produto**
  (`services/cmv_grupos.py`, migração 029, 26/08/2026). O painel já mostrava Perdas, Consumo
  interno e Ajustes de inventário como linhas que EXPLICAM o número; faltava a pergunta que o
  dono faz olhando a nota do mês: **quanto disto não é comida?** Detergente, sacola e marmita
  entram no custo pela mesma porta dos insumos e somem no total. Tipo novo:
  **`MATERIAL_LIMPEZA`**. O grupo de exemplo ("Material de limpeza e embalagem" = EMBALAGEM +
  MATERIAL_LIMPEZA) nasce na migração — funcionalidade que não aparece é funcionalidade que
  ninguém procura —, e é editável e apagável como qualquer outro.
  ⚠️ **Um tipo só entra em UM grupo, e quem garante é o BANCO**: `tipo` é a chave primária de
  `cmv_grupo_tipos`. Conferir só na aplicação deixaria duas telas gravarem ao mesmo tempo — e o
  mesmo custo apareceria em dois grupos, com a soma dos grupos deixando de fechar com o CMV, que
  é justamente a propriedade que dá sentido ao corte (a suíte cobra a identidade).
  ⚠️ **O vínculo é com o TIPO, nunca com o produto.** Mudar a configuração reclassifica o
  passado inteiro sem tocar em cadastro nenhum; gravar o grupo no produto exigiria varrer o
  cadastro a cada mudança e deixaria para trás justamente os produtos antigos, que são os que
  têm histórico.
  ⚠️ **O grupo escolhe se entra no CMV real** (`considerar_no_cmv`, migração 032). Marcado, a
  linha EXPLICA o CMV — como Perdas: o custo já está no total e a linha diz quanto do total é
  aquilo. Desmarcado, o custo **sai da conta**, e é isso que separa comida de detergente no food
  cost, que é o percentual que vira decisão de cardápio.
  ⚠️ **Sair é sair das TRÊS pontas** — estoque inicial, compras e estoque final. Tirar só as
  compras deixaria o estoque de limpeza do começo e do fim na conta, e a diferença entre os dois
  viraria custo de comida do mesmo jeito, com sinal imprevisível. Saindo das três, a
  contribuição do grupo se anula por completo: a suíte cobra que o CMV caia **exatamente** o que
  o grupo valia, e que remarcar devolva o número.
  ⚠️ **O dinheiro NÃO some da tela**: o grupo continua no painel, dito "FORA do CMV real", e um
  aviso acima da conta nomeia o que ficou de fora. Gasto que desaparece da vista é gasto que
  ninguém controla — e quem compara com o mês passado precisa saber que a régua mudou.
  ⚠️ `tipos_fora_do_cmv` viaja na apuração e é uma **lista**: o router converte os valores para
  `float`, e `float(list)` derrubava a apuração inteira com 500. Campo novo que não seja número
  precisa entrar na exceção de `_float`.
  ⚠️ **Grupo configurado aparece no painel mesmo valendo zero**, ao contrário do relatório por
  grupo (que lista o que pesou): ali "não apareceu" é indistinguível de "não salvou". E na ordem
  que a casa definiu, não na do valor — linha que troca de lugar entre um período e outro é
  linha que ninguém acha.
  ⚠️ A conta é a MESMA de `relatorios.cmv_por_grupo` (`agrupar="grupo"`), não uma soma escrita à
  parte: painel e relatório mostram o número lado a lado. Configura-se em **Tabelas de apoio ▸
  Grupos do CMV**, sob a chave `cmv.grupos` — ver o painel e remontar a apuração da casa são
  coisas diferentes, e o Contador tem a primeira.

- **`services/cmv.py`**: `CMV real = estoque inicial + compras − estoque final`. O valor do
  estoque numa data sai do próprio razão (último movimento antes do corte já traz
  `saldo_apos` × `custo_medio_apos`) — não se recalcula série nenhuma.
  ⚠️ **Data de HOJE responde pelo `estoque_saldos`, não pelo razão.** Os dois dão o mesmo
  número (o saldo é a fotografia corrente, e o razão não aceita movimento no futuro), mas o
  caminho é outro: uma linha por produto e local contra um `DISTINCT ON` sobre tudo o que já
  aconteceu. Com 400.000 movimentos, **837 ms viraram zero** — e é o caso mais comum, porque
  todo mês aberto termina hoje. O atalho está em DOIS lugares (`valor_do_estoque` e a CTE
  `final` de `movimentacao_por_produto`) e `smoke_cmv` cobra que continuem concordando.
  Para data passada vale o índice `ix_mov_fotografia` (migração 027): apuração do mês de
  ~1.700 ms para **625 ms**, movimentação do mês aberto de 1.262 ms para **642 ms**.

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

- 🔑 **A MEMÓRIA DE CÁLCULO** (`services/memoria_calculo.py`, três relatórios novos,
  02/09/2026, pedido da contabilidade numa reunião). O sistema já dizia o **resultado** (a
  apuração, dez linhas) e já provava a **identidade** (a movimentação por produto, onde
  `inicial + entradas − saídas = final` fecha na própria planilha). Faltava o passo do meio:
  **os documentos que compõem cada linha**. Perguntado *"estes R$ X de compras, de quais notas
  são?"*, não havia resposta — era abrir Compras, filtrar o período e somar à mão.
  🔑 **E somar as notas à mão dá OUTRO número, de propósito** — este é o ponto que faria a
  reunião seguinte terminar mal. A linha "Compras" **não** é a soma dos totais das notas: ela
  soma os MOVIMENTOS de entrada (com frete, IPI e ST já rateados por item), **tira** os grupos
  fora do CMV e **soma** a remessa recebida de outra loja. O contador que soma as notas encontra
  diferença, e ela parece erro. O **Quadro 4** é a conciliação que leva de uma à outra em linhas
  nomeadas, terminando exatamente no número da apuração.
  **Os três relatórios**, todos pela janela de exportação (CSV e PDF, timbre e rodapé de graça):
  * **`memoria-cmv`** (botão em `/cmv`, ao lado do arquivo do contador) — a apuração com quatro
    quadros anexos: estoque inicial item a item, compras por documento, estoque final item a
    item, e a conciliação.
  * **`inventario-valorizado`** (botão em `/estoque`) — o estoque NUMA DATA, com o método de
    custeio declarado no cabeçalho. É o documento do balanço.
  * **`memoria-produto`** (botão em `/produtos/[id]`, com o produto já semeado) — um insumo
    movimento a movimento, com a **conta escrita na linha**:
    `(saldo × médio + entrada × custo) ÷ novo saldo`. É a resposta para *"como você chegou nesse
    custo unitário?"*: sem a conta, o número aparece pronto e não se confere.
  ⚠️ **Nada aqui recalcula.** Toda ponta sai de `cmv.valor_do_estoque` e dos mesmos tipos de
  movimento da apuração — `estoque_em` espelha até o ATALHO de hoje (`estoque_saldos` para hoje,
  fotografia do razão para data passada). Uma segunda implementação divergiria no primeiro caso
  de borda, e o sintoma seria a memória discordando do número que ela existe para explicar: pior
  que memória nenhuma. **`smoke_memoria` cobra que cada quadro FECHE com a linha.**
  ⚠️ **Cada quadro traz DOIS totais: o da coluna e o da apuração.** O do quadro soma as linhas
  ARREDONDADAS (é ele que fecha com a coluna que alguém confere à mão); o da apuração é o
  AUTORIZADO. Em 158 linhas os dois deram 2 centavos de diferença — e esconder um deles seria
  pior: ou a coluna não soma, ou não bate com o painel. Vendo os dois, a diferença tem nome.
  ⚠️ **O custo unitário NÃO vai a centavos**, ao contrário do valor: ele é um PREÇO (R$ por KG),
  e arredondá-lo faria `quantidade × custo` deixar de reproduzir o valor da linha — que é
  justamente a conta que o contador refaz.
  ⚠️ **O inventário do balanço NÃO tira os tipos fora do CMV.** Aquele filtro é da conta do
  custo da comida; o balanço é o que a casa POSSUI, e detergente em estoque é patrimônio igual.
  ⚠️ **Uma DATA, não um período** — filtro novo (`tipo: "data"`) no catálogo e na janela. A
  pergunta "quanto valia o estoque em 31/12" tem uma resposta só, e duas pontas fariam escolher
  um intervalo para ela.
  ⚠️ **A chave é `inventario-valorizado`, não `inventario`**: já existe `/exportar/inventario/{id}`,
  a folha de CONTAGEM. Dois endereços parecidos para documentos diferentes é a divergência que
  só aparece no dia em que alguém baixa o errado e manda ao contador.
  ⚠️ **O sinal vai no VALOR, não no rótulo.** A conciliação dizia "(−) o que não vira mercadoria"
  e somava um número positivo: a conta andava para o lado contrário do texto. Aquela diferença
  vai para os dois lados — item ignorado tira, acessória rateada põe — e só o número sabe qual.
  ⚠️ **O documento diz se o período está FECHADO.** Aberto, o número ainda pode mudar depois de
  o arquivo sair da casa — e este é o que se assina embaixo.
  ⚠️ Sem escolher o produto, a memória por produto sai com uma frase mandando escolher, e não
  vazia: vazio se lê como "não houve movimento", que é outra coisa.

- 🔑 **A DIÁRIA só rodava se alguém estivesse acordado na hora marcada — e o dia inteiro
  passava em branco** (02/09/2026, pedido do dono). `deve_rodar` exigia
  `agora.hour == agenda_hora`: o disparo existia dentro daqueles sessenta minutos e em mais
  nenhum instante. Com a API parada às 4h — um deploy, um reinício, a máquina desligada — a
  busca daquele dia **simplesmente não acontecia**, e nada dizia isso: a tela mostrava a última
  sincronização, que uma busca manual tinha atualizado, e a agenda parecia em dia.
  **Medido na base local**: a diária das 4h do PDV tinha rodado pela última vez em **31/08**,
  com hoje sendo 02/09 — dois dias de notas e cupons perdidos, ou seja compra a menos e receita
  a menos no CMV, em silêncio.
  A regra virou a pergunta que a casa faz: *já buscou hoje?* Não tendo buscado e já passada a
  hora marcada, busca — assim que houver alguém para buscar.
  ⚠️ **Continua sendo UMA vez por dia.** Voltando depois de três dias fora do ar, roda uma vez e
  não três: quem responde é a DATA do último disparo, não quantos horários passaram. Três buscas
  seguidas só gastariam cota, e a janela adaptativa cobre o período inteiro numa ida só.
  ⚠️ **E a primeira configuração dispara logo**, quando a hora escolhida já passou — em vez de
  esperar até a madrugada seguinte. A tela diz isso.

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

- **PWA instalável** (19/08/2026): `app/manifest.ts`, `public/sw.js`, `app/offline/page.tsx`,
  `components/pwa.tsx` (registro + convite) e `scripts/gerar-icones-pwa.mjs` (roda na mão,
  usa sharp). Regras do service worker que **não se afrouxam**: a API (outra origem) e
  `/api` são ignoradas por completo — cachear serviria o saldo de um usuário para o próximo
  que entrasse no mesmo aparelho; HTML é network-first com a página `/offline` de reserva;
  só `_next/static/*` é cache-first (o nome tem hash). ⚠️ **Em dev o cache de estático é
  desligado** (`/sw.js?dev=1`), senão o HMR do Next serve pedaço velho e vira caça a bug que
  não existe. ⚠️ `apple-mobile-web-app-capable` está declarado à mão em `metadata.other`: o
  Next 16 só emite o nome padronizado, que o Safari entende do iOS 17.4 em diante.

- Testes (1.784 verificações de API): `smoke_fundacao.py` (47, 48 em base virgem), `smoke_cadastros.py` (55),
  `smoke_fichas.py` (55), `smoke_estoque.py` (170), `smoke_cmv.py` (63), `smoke_omie.py` (116),
  `smoke_notas.py` (70), `smoke_senha.py` (40), `smoke_email_prazo.py` (15), `smoke_sessao.py` (17), `smoke_lotes.py` (28),
  `smoke_relatorios.py` (44), `smoke_kits.py` (29), `smoke_conversao.py` (29),
  `smoke_producao.py` (46), `smoke_alertas.py` (28), `smoke_paginacao.py` (25), `smoke_ajustes.py` (48), `smoke_ciclos.py` (32),
  `smoke_grupos_cmv.py` (45), `smoke_utensilios.py` (23), `smoke_inventario_filtros.py` (50),
  `smoke_exportacoes.py` (110), `smoke_produto_do_omie.py` (31), `smoke_agenda_omie.py` (31), `smoke_pdv_legal.py` (156), `smoke_vendas.py` (69), `smoke_vinculo.py` (91),
  `smoke_transferencias.py` (47), `smoke_lojas_do_usuario.py` (26),
  `smoke_memoria.py` (37),
  `cenario_cafeteria.py` (57) e `cenario_semana.py` (54); mais
  `web/scripts/testar-sw.mjs` (17, sem navegador) e
  `web/scripts/verificar.mjs` (461, no Chrome, com fotos em `web/scripts/_fotos`).
  Todos idempotentes; os de CMV medem **delta** sobre a apuração anterior, porque o banco
  local já tem dado de outras rodadas.

- ⚠️ **Foto de página inteira não pode derrubar a bateria.** `fullPage` estoura o
  `protocolTimeout` do Chrome numa tela longa; aconteceu com o painel de CMV e voltou a acontecer
  quando Integrações ganhou o segundo bloco de agenda — e levou junto as 280 checagens da rodada.
  `foto()` agora cai para a foto da JANELA e avisa; o `protocolTimeout` subiu para 60 s.

## Armadilhas já pagas

  Removidas `app/(app)/ajustes/{lote,custo}/`, `/ajustes` passou a devolver **404** enquanto as
  outras telas respondiam 200 — o `.next/dev/server/app/(app)/ajustes/custo/` continuava lá com
  manifesto próprio. Some as sobras em `.next/dev` e dê um `touch` na `page.tsx` (ou reinicie o
  `npm run dev`). ⚠️ A suíte de navegador tinha passado VERDE logo depois da remoção: o
  conflito só apareceu numa recompilação posterior.

- 🔑 **O seletor de local oferecia TODOS os locais da casa — 93 numa base real.** O produto
  costuma estar em UM. Escolher o errado não dava erro na hora: numa saída, o razão registrava
  a baixa por um local onde o insumo nunca passou, criando saldo **negativo com custo
  provisório** — o mesmo defeito que a produção já teve. Agora a tela pergunta onde o produto
  tem saldo e oferece só esses, **com a quantidade no rótulo** ("Câmara fria — 12 KG"), o que
  faz a escolha ser consciente em vez de um chute entre nomes de prateleira. Um local só:
  escolhe sozinho.
  ⚠️ **Na ENTRADA a lista continua inteira**, de propósito: a primeira entrada de um produto
  novo não tem saldo em lugar nenhum, e restringir ali impediria de cadastrar o estoque inicial.
  O destino da transferência idem — as duas põem mercadoria onde ela ainda não está.
  ⚠️ **Tirar o seletor não era opção**: produto PODE ter saldo em mais de um local (há casos na
  base), e escolher sozinho ajustaria a prateleira errada em silêncio.
  ⚠️ **Sem saldo em lugar nenhum, a lista volta INTEIRA e o lançamento é PERMITIDO.** Houve
  uma versão que bloqueava com "este produto não tem saldo em nenhum local" — estava errado:
  perda e saída de algo que o sistema acha que é zero são legítimas, o razão aceita e marca o
  custo como provisório. Bloquear obrigaria a inventar uma entrada antes, que é pior: cria uma
  compra que não houve e o custo dela contamina o médio. O acerto de quantidade idem — "a
  prateleira tem 5 e o sistema não tem nada" é justamente o caso em que ele serve, e
  `_saldo_de(exigir=False)` trata a ausência de linha como zero.
  ⚠️ O ajuste de CUSTO continua recusando saldo zero, e não por política: `(novo − atual) × 0`
  é zero. Não há valor a corrigir.

- 🔑 **A tela de Ajustes tem SEIS tipos, e eles se dividem em dois grupos.** Entrada, Saída,
  Perda e Transferência dizem **o que se MOVEU**. Ajuste de estoque e Ajuste de custo declaram
  **a VERDADE** — quanto realmente tem, quanto realmente custa — e o sistema calcula a
  diferença. Pedir a diferença obrigaria a fazer a subtração de cabeça, que é onde o erro entra:
  quem conta lê "12" na etiqueta, não "menos 3".
  🔑 **`estoque.ajuste` ("ajustar saldo fora do inventário") existia desde o script 002 sem
  nenhuma funcionalidade atrás dela** — só era usada pelo estorno. O ajuste de estoque é ela.
  ⚠️ **Ele reusa `AJUSTE_INVENTARIO_ENTRADA/SAIDA`**, e não um tipo novo: é a mesma natureza de
  correção, então cai na linha "Ajustes de inventário" que o painel já mostra. Tipo novo criaria
  uma segunda linha para a mesma coisa.
  ⚠️ **A sobra entra pelo MÉDIO que já existe** (`custo_unitario=None`): item encontrado vale o
  que os outros valem, e assim o acerto de QUANTIDADE não mexe no custo médio — quem faz isso é
  o outro tipo.
  🔑 **Os dois têm efeito OPOSTO no CMV, e é o erro mais fácil de cometer.** Falta de estoque
  baixa o estoque final e o CMV é `inicial + compras − final`: menos estoque, **CMV maior**.
  Já subir o custo aumenta o estoque final: estoque mais caro, **CMV menor**. As duas prévias
  dizem qual dos dois em palavras, e a suíte cobra os dois sinais.

- ⚠️ **O ajuste de custo é MAIS UM TIPO na tela de Ajustes, um produto por vez** — não um
  processo em lote com tela própria. A primeira versão fez lote (`/ajustes/lote`,
  `/ajustes/custo`, item no menu) e o dono pediu igual aos outros quatro: mesma tela, mesma
  forma. O lote saiu; o que ficou do backend é `POST /ajustes/custo` (recebe lista, a tela
  manda uma) e `POST /ajustes/custo/previa`. `ajuste_lotes` continua no banco e recebe um lote
  de UM por ajuste — é o que guarda autor e observação e amarra o movimento por
  `origem_tipo = 'AJUSTE_LOTE'`. **Quantidade tem porta própria e mais antiga**
  (`/estoque/entradas`, `/saidas`, `/transferencias`); o lote de estoque virou código morto e
  foi removido.
  ⚠️ **A prévia é pedida ao SERVIDOR no blur do campo**, não recalculada em TypeScript: seria a
  segunda versão da mesma regra, e as duas divergiriam no primeiro caso de borda.
  ⚠️ O campo de quantidade **some** no tipo custo — mostrá-lo desabilitado sugeriria que alguma
  quantidade se move.

- 🔑 **Movimento de quantidade ZERO some das somas que ramificam por sinal.** O ajuste de custo
  (migração 039) reavalia o estoque sem mover mercadoria: `quantidade = 0`, `custo_total <> 0`.
  A CTE da movimentação ramificava só em `quantidade > 0` e `< 0`, então ele caía em nenhum dos
  dois lados e o valor sumia — enquanto o estoque FINAL, que sai da fotografia do razão, já o
  incluía. A identidade `inicial + entradas − saídas = final` parou de fechar, e a diferença era
  exatamente o reavaliado. **Três suítes caíram de uma vez.** Agora o valor entra pelo SINAL do
  `custo_total` quando a quantidade é zero. ⚠️ A quantidade continua fora (é zero mesmo): a linha
  mostra valor sem unidade, que é literalmente o que aconteceu.
  ⚠️ **O sinal do efeito é contraintuitivo e precisa estar escrito na tela**: subir o custo do
  estoque AUMENTA o estoque final, e o CMV é `inicial + compras − final` — estoque mais caro,
  CMV **menor**. A prévia diz isso em reais antes do botão.
  ⚠️ **Teste de tela que desvia tem de VOLTAR.** As checagens novas navegavam para
  `/ajustes/lote` e `/ajustes/custo` e o bloco seguinte supunha estar em `/ajustes` — a suíte
  morria procurando campos numa página que não os tem, longe da causa.

- ⚠️ **`/estoque/saldos` é paginado, e os dois CENÁRIOS montavam dicionário da primeira página.**
  `cenario_semana` estourou com `StopIteration` e `cenario_cafeteria` passava por sorte — o
  KeyError chegaria na rodada seguinte. Os dois agora pedem `?id_produto=` de cada produto
  DELES (`saldos_de()` no cafeteria).
  ⚠️ **`smoke_conversao` tinha a MESMA doença e ficou de fora daquela correção** — quebrou
  em 29/08/2026, com quatro checagens, na primeira base grande o bastante para empurrar os
  produtos dele para fora da primeira página. E o sintoma engana: a checagem acusa o razão de
  não ter gravado o que gravou. Ao corrigir uma armadilha deste tipo, **procurar todos os
  chamadores**, não só os que estão falhando naquele dia. ⚠️ Pior que o estouro é o caso mudo: a checagem final do
  `cenario_semana` filtrava a página e, vindo vazia, passava sem ter olhado nada.

- 🔑 **Apuração e movimentação NÃO respondem a mesma pergunta, e a diferença dormiu até o
  primeiro grupo fora do CMV existir na base.** `cmv.apuracao` desconta do estoque final os
  tipos com `considerar_no_cmv = false`; `cmv.movimentacao_por_produto` **não recebe esse
  filtro** — é relatório de ESTOQUE e mostra tudo, porque taça guardada é estoque mesmo não
  sendo custo de comida. A checagem do `smoke_cmv` comparava os dois crus e passou anos verde:
  a base local não tinha nenhum grupo fora do CMV (a semente da 029 sumiu numa limpeza com
  `--tabelas-de-apoio`, e migração não reexecuta). Assim que a 037 semeou o de utensílios, a
  identidade abriu **exatamente o valor das taças** — e parecia erro de razão.
  ⚠️ **A segunda checagem, a de ONTEM, passava por sorte**: o estoque do dia anterior ainda não
  tinha utensílio. Quebraria sozinha no dia seguinte, longe de qualquer commit — que é o pior
  tipo de teste frágil. As duas agora tiram a parcela fora do CMV dos dois lados.
  ⚠️ **A movimentação não devolve `tipo`** (só `categoria` e `setor`), então o teste casa por
  `id_produto` contra `/produtos?tipo=`. Pôr `tipo` no relatório seria melhor, mas a cópia
  congelada (`cmv_movimentacao`, migração 018) também não tem a coluna: mês fechado ficaria
  sem ela. É migração própria, não efeito colateral de outra coisa.

- ⚠️ **A fotografia do razão não sobrevive a lançamento retroativo — e não é dos ciclos.**
  `saldo_apos` é calculado na ordem de LANÇAMENTO (decisão certa: por data, o CMV de ontem
  mudaria sozinho). Como o saldo de uma data passada é lido do último movimento antes dela, um
  retroativo gravado hoje entra como "o último" e devolve um saldo que já inclui o que veio
  antes dele na fila. Resultado: `inicial + entradas − saídas = final` abre em recorte que
  termina antes de hoje. No mês inteiro fecha, porque o retroativo e o que ele contamina caem os
  dois dentro da janela — foi por isso que passou anos despercebido, com o mês sendo o único
  período possível. A tela nomeia a causa; o conserto está em `docs/o-que-falta.md`.
  ⚠️ Toda suíte que confere essa identidade tem de **garantir o ritmo MENSAL** antes, não supô-lo.

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

- ⚠️ **O primeiro local da loja nasce principal** (migração 016), marque-se a caixinha ou não:
  estoque, produção e inventário usam o principal como padrão, e sem nenhum marcado o seletor
  mostrava o nome do local (era o único da lista) enquanto o pedido saía **sem** local — 404
  "Local não encontrado" com o local à vista na tela. As telas também caem para o primeiro
  local quando não há principal. ⚠️ Nenhuma suíte pegou isso porque `garantir_locais` mandava
  `principal: true` — mais cuidado do que quem cadastra "Balcão" tem. O helper parou de mandar.

- **Fechamento de mês bloqueia lançamento retroativo** — mas quem tem `estoque.retroativo`
  (inclusive o admin) passa. Teste da trava precisa de usuário sem a chave (o Conferente).

- **Movimento de estoque não se apaga**: estorno cria a contrapartida apontando para o
  original. Produto desativado mantém saldo e razão (a lista de saldos filtra por padrão).

- 🔑 **O custo do produto passou a ter onde ser CONSULTADO** (`GET /produtos/{id}/custo`, cartão
  **Custo** + botão **Histórico** na tela do produto, 03/09/2026, pedido do dono). O número já
  alimentava ficha, CMV teórico e margem, mas nenhuma tela o mostrava: para saber quanto custava
  um insumo era preciso abrir uma ficha que o usasse.
  🔑 **E a "Memória de cálculo" não cobria o caso.** Ela explica o custo MÉDIO, que nasce de
  movimento — numa casa que importou o catálogo e ainda não lançou nota ela sai VAZIA, enquanto o
  custo de referência responde pela cascata sem aparecer em lugar nenhum. Foi exatamente o
  sintoma relatado depois da carga do Omie.
  ⚠️ **A ORIGEM vem junto do valor, sempre.** "R$ 20,03" sozinho não responde se é o que a casa
  pagou, o que o fornecedor cobra ou o que outro sistema acha — três coisas que valem diferente.
  ⚠️ **Sem custo é "—", nunca R$ 0,00.** Zero é uma afirmação, e é o número que faz o food cost
  sair bom demais sem ninguém desconfiar.
  ⚠️ **NÃO se criou tabela de histórico, e não é economia.** O razão já é a memória do custo:
  `estoque_movimentos.custo_medio_apos` guarda o médio depois de cada movimento. Tabela nova
  nasceria vazia para tudo o que já aconteceu e criaria duas versões da mesma verdade. Só as
  linhas em que o médio MUDOU entram (`lag` por local) — listar todas viraria extrato de estoque.
  ⚠️ **As outras duas pontas da cascata não têm série, e a janela DIZ isso**:
  `produto_fornecedor.ultimo_preco` e `produtos.custo_referencia` guardam só o valor corrente e a
  data dele. Mostrá-los como linha do tempo faria parecer que o sistema sabe o que não sabe.
  ⚠️ Pede `estoque.saldos`, a mesma chave da memória de cálculo: custo é dado de ESTOQUE e não
  vira dado de cadastro por estar na tela do produto.

- 🔑 **As vendas antigas que entraram valendo ZERO passam a ser custeadas** (`custos_iniciais`,
  `_custear_vendas_sem_custo`, 03/09/2026, pedido do dono). Trazer o custo para o produto
  consertava METADE do problema: o item de venda guarda o custo congelado do dia da venda, e os
  que entraram antes de existir custo ficavam com nada — contando zero no CMV teórico, que é o
  que faz o food cost sair bom demais sem nada denunciando. Medido: 2.121 de 2.122 itens sem
  custo.
  🔑 **É a MESMA regra que o vínculo de cadastros já aplicava** (`fundir`): só quem está sem
  custo é tocado. Item com número guarda o que se sabia no dia da venda.
  ⚠️ **Mês FECHADO fica de fora — a fronteira que não se cruza.** Ele já foi ao contador. O
  relatório dele sobreviveria (o fechamento congela `cmv_teorico` e a movimentação por produto),
  mas reescrever as linhas por baixo faz o número congelado deixar de se reproduzir a partir dos
  dados — e reabrir o período o mudaria sozinho. A suíte prova nos DOIS sentidos: fechado não
  recusteia, aberto recusteia o mesmo item.
  ⚠️ **A origem vai GRAVADA** (`origem_custo`). A referência é o degrau mais fraco da cascata:
  congelar um palpite dentro do CMV de um mês passado só é aceitável porque a linha diz que é um
  palpite. Sem essa marca, isto não deveria existir.
  🔑 **O escopo errado devolveu ZERO, e o erro ensina onde o custo anda.** A primeira versão
  recalculava só as vendas dos produtos que acabaram de receber referência — e o custo do Omie
  cai nos INSUMOS comprados, enquanto quem foi vendido são os itens do cardápio do PDV, cadastros
  diferentes: dos 215 produtos vendidos, ZERO recebeu referência. O ganho chega ao prato pela
  FICHA, cujos insumos agora têm custo. Varre-se todo item sem custo, não os da carga.
  ⚠️ **Custo nulo continua NULO, não vira zero** — é justamente a afirmação falsa que se está
  corrigindo. Sobraram 213 produtos vendidos sem custo porque não têm ficha; a cada ficha nova,
  rodar o custo inicial de novo os alcança.

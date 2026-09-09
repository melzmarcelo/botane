# Estoque

> Saldos, movimentos, ajustes, inventário e transferências entre lojas.
> Leia antes de mexer neste módulo.

## O que já existe

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

- ⚠️ **Produto ATIVO sem unidade de estoque também devolvia 500.** A trava é do banco
  (`ck_produto_rascunho`) e é a certa — quantidade sem unidade não decide custo nenhum —, mas
  vazava como "Internal Server Error" para quem cadastrava um prato sem escolher unidade.
  Virou 400 com frase, e a saída ("salve como rascunho") vai junto. ⚠️ Ao adicionar validação
  que consulta uma coluna, **o `SELECT` do "antes" no PUT precisa trazê-la**: sem `um_estoque`
  ali, um PUT que só mudava o preço levava 400 sem ter tocado no assunto.

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

- ⚠️ **Produto sem `um_estoque` NÃO entra no razão** (`lancar_nota`). Quantidade sem unidade é
  número sem significado — "3" de champignon não diz se são três bandejas ou três quilos —, e o
  custo médio que sair daí contamina ficha, CMV e a próxima compra. O catálogo do Omie cria
  rascunho sem unidade de propósito (a sigla do fornecedor pode não existir na casa); é no
  lançamento que a dívida é cobrada, e a recusa **nomeia todos** os produtos de uma vez.

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

- ⚠️ **O alerta de mínimo se divide em dois**: `estoque.minimo` (compra-se) e
  `producao.agendar` (a casa produz — aponta para a agenda, não para o estoque). Alerta que
  aponta para o lugar errado é alerta que ninguém segue. Há também `producao.atrasada`.

- ⚠️ **A produção baixa cada insumo do local DELE** (`id_local_padrao`), não do local
  informado no lançamento — uma receita usa leite da câmara e café do seco ao mesmo tempo.
  Achado pelo `cenario_cafeteria.py` em 24/08/2026: a saída batia num local sem saldo, o razão
  registrava a baixa por onde o insumo nunca passou (com **custo provisório**) e o saldo do
  lugar certo continuava cheio. O produzido também entra no local dele.

- ⚠️ **VENDER É SAIR DO ESTOQUE** (24/08/2026): a importação de venda lança `SAIDA_VENDA`
  para todo produto que `controla_estoque` — não só para o `NA_HORA`. Antes, o que era
  PARA_ESTOQUE (ou revenda) continuava na prateleira do sistema depois de vendido: o **CMV
  real saía subestimado** e a primeira contagem cobria o buraco inteiro como "ajuste de
  inventário", que é onde a diferença some sem nome. Cancelar a venda **estorna** os
  movimentos — cancelar sem devolver deixaria o produto fora da prateleira e fora do caixa.

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

## Armadilhas já pagas

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

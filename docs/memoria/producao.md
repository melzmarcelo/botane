# Produção

> Ficha técnica e produção.
> Leia antes de mexer neste módulo.

## O que já existe

- 🔑 **O rendimento É a tabela de destinos, e ela mora no cabeçalho** (13/09/2026, pedido do
  dono: *"o rendimento e destinos estão em um grupo separado; podemos colocar junto com o
  cabeçalho, onde o destino é o local padrão do produto, e assim gerados os seus rendimentos.
  Caso eu adicione um novo local, adicionar uma nova linha com um cadastro igual ao padrão"*).
  🔑 **A primeira linha É a ficha.** `rendimento_qtd`, `porcoes` e `porcao_qtd` continuam sendo
  colunas de `fichas_tecnicas` e continuam valendo para toda prateleira sem linha própria — o
  que mudou é o que a tela diz que eles são. Nenhum dado se moveu e nenhuma ficha existente
  mudou de comportamento.
  ⚠️ **Prateleira nova nasce IGUAL ao padrão**, que é o pedido ao pé da letra: ajusta-se o que
  difere (o forno muda o rendimento, não a receita). Nascer vazia obrigaria a redigitar três
  números para mudar um.
  ⚠️ **A linha do padrão não se remove nem troca de prateleira** — ela é o rendimento da
  receita, e sem ela produzir para um destino sem linha ficaria sem resposta. E a prateleira
  padrão sai da lista das outras linhas: oferecê-la de novo seria duas verdades para o mesmo
  destino.
  ⚠️ **Salvar a ficha grava os destinos junto** (`PUT /fichas/{id}` e depois
  `PUT /fichas/{id}/modos`, nessa ordem — se a ficha recusar, os modos não podem ter mudado
  sozinhos). O cartão anterior tinha botão próprio, e uma mudança só exigia salvar duas vezes.
  ⚠️ **Em ficha NOVA só existe a linha do padrão**: destino aponta para uma ficha gravada.
  ⚠️ **A armadilha desta refatoração, e ela custou três checagens**: a sugestão "a soma dos
  ingredientes dá X · usar" morava DENTRO do campo Rendimento e sumiu junto com ele. A bateria
  pegou — as três checagens do recurso caindo de uma vez, que é a assinatura de "sumiu junto",
  não de "quebrou". Ela voltou ao pé da tabela. Refatorar tela é isso: o que está pendurado no
  que sai vai junto, calado.

- 🔑 **A lista de fichas mostra UMA linha por produto** (13/09/2026, relato do dono: *"quando
  sai uma nova versão, parece que há dois produtos na lista"*). A ficha é versionada e a lista
  mostrava uma linha por versão — o mesmo prato duas vezes, sem nada dizendo que eram o mesmo.
  A linha que aparece é a que VALE: homologada vigente; sem ela, a maior versão — a mesma
  escolha que a produção faz, e outra aqui faria a lista mostrar uma versão e a produção
  consumir outra.
  ⚠️ **`agrupar` é OPT-IN, e tem de ser**: a tela da ficha carrega a MESMA lista para oferecer
  sub-ficha e para o duplicar saber quantas versões o destino tem. Agrupar por padrão esconderia
  versões de quem precisa justamente delas.
  ⚠️ **`count(*) OVER (PARTITION BY id_produto)` vem ANTES do `DISTINCT ON`** — no Postgres a
  janela é calculada depois do WHERE e antes do DISTINCT, então o contador de versões sobrevive
  à escolha da linha. E o total da paginação é recalculado por fora: o `count(*) OVER ()` de
  dentro contaria VERSÕES, e o rodapé diria "22 fichas" numa lista de 14 produtos.
  🔑 **Dentro da ficha, um seletor de versão** — sem ele as versões antigas perderiam a porta de
  entrada quando a lista passou a mostrar uma linha. Só aparece com mais de uma: seletor de um
  item é controle que não controla nada.
  ⚠️ E o cabeçalho ganhou o produto sozinho na primeira linha: ele dividia a grade com
  rendimento e porções, e o campo do tamanho da porção apertou os quatro — o nome do prato
  ficava do tamanho de um campo numérico.


- 🔑 **Rascunho se EXCLUI; publicada se arquiva** (`DELETE /fichas/{id}`, 13/09/2026, pedido do
  dono: *"caso a ficha esteja como rascunho, permitir que ela seja excluída"*). Arquivar existe
  para não quebrar o passado — ficha publicada apurou custo e o histórico aponta para ela.
  Rascunho não tem passado nenhum (nunca homologou, nunca produziu, nunca entrou em CMV), e uma
  lista cheia de tentativas arquivadas é ruído que ninguém pode limpar.
  ⚠️ **O mesmo endpoint faz as duas coisas**, e quem decide é o STATUS — não a vontade de quem
  clica. A tela só oferece "Excluir rascunho" onde ele funciona, mas a guarda é do servidor.
  ⚠️ **Três travas, e as três têm razão de banco**: usada como sub-ficha (a FK de
  `ficha_itens.id_subficha` é `RESTRICT`, e o custo da outra quebraria); com produção registrada
  (`producoes.id_ficha` é `NO ACTION`); e a FOTO sai primeiro, porque `fichas_tecnicas` não é
  dona do arquivo e apagar a linha deixaria a imagem órfã em `arquivos`. `ficha_itens` e
  `ficha_modos` somem por CASCADE — são partes da receita, não registros com vida própria.
  ⚠️ A auditoria grava o `excluir` antes do fim da transação: é o único lugar onde resta
  registro de que aquela ficha existiu.

- 🔑 **O custo que a ficha PREVÊ aparece na tela do produto** (`custos.custo_provisorio_da_ficha`,
  13/09/2026, pedido do dono: *"caso a ficha não tenha sido produzida, a ficha está sem custo,
  levar este custo provisório para a tela do cadastro de produto"*). Produto produzido só ganha
  custo médio quando uma produção entra no razão: antes disso a cascata inteira responde
  "ninguém sabe quanto custa" — enquanto a receita, ali do lado, sabe somar os ingredientes.
  ⚠️ **NÃO entra na cascata de `custo_do_insumo`**, de propósito: ali o número alimenta ficha de
  terceiros, CMV e margem, e um teórico entrando calado mudaria todos de uma vez. É para a TELA,
  que foi o que o pedido disse.
  ⚠️ **Só quando o apurado é NULO.** Com custo de verdade, oferecer um teórico ao lado seria dar
  dois números para a mesma pergunta.
  ⚠️ **Incompleto vem MARCADO, não escondido**: ficha com item sem preço soma parte da receita, e
  o aviso diz quantos faltam. Sem isso seria um custo barato demais com cara de apurado —
  exatamente o que faz o food cost sair bom sem ninguém desconfiar.
  ⚠️ Prefere a ficha VIGENTE; sem ela, a mais recente — que é o rascunho de quem está montando a
  receita agora, e é justamente quem ainda não produziu nada. Arquivada não responde: a suíte
  tropeçou nisso primeiro (o teste reusava um produto cuja única ficha havia sido arquivada) e
  acusou o recurso por um comportamento que está certo.


- 🔑 **A mesma ficha com PROCESSOS diferentes: a prateleira decide o rendimento**
  (`ficha_locais` → hoje `ficha_modos`, + `produtos.id_local_venda`, migração 066,
  12/09/2026, pedido do dono:
  *"a mesma ficha pode ter processos diferentes. Vamos fazer a massa de pizza e estocar para
  servir como insumo para pizza, mas podemos ter produção de massa de pizza que vai para a
  vitrine"*). E o rendimento muda de verdade — a da vitrine vai ao forno e perde água.
  🔑 **O que o dono desenhou, e é o desenho certo**: no produto, mais de um local e a marca de
  qual o PDV consome; na ficha, os locais com rendimento próprio; ao programar, escolher o
  local. As três peças encaixaram no que já existia — `estoque_saldos` já é "onde o produto
  mora", e a agenda já guardava `id_local`.
  🔑 **`id_local_padrao` fazia TRÊS papéis, e essa era a raiz do problema**: (1) de onde a
  VENDA baixa, (2) o fallback de onde os INSUMOS saem (`_de_onde_sai`), (3) o destino padrão da
  produção. Com uma coluna só, pôr a Vitrine como "o local do produto" fazia a receita da pizza
  **comer a massa da vitrine**. `id_local_venda` separa o papel 1 — nulo mantém tudo como era.
  ⚠️ **O modo é OVERRIDE, não substituição.** Sem linha, vale o rendimento da ficha, que
  é o caso de todas as fichas de hoje: é isso que faz a migração não mexer em nenhuma produção
  existente. Índice único em (ficha, local) — dois rendimentos para o mesmo destino seria a
  receita com duas verdades.
  ⚠️ **O rendimento DIVIDE o consumo** (`lotes = quantidade ÷ rendimento`): produzir 10 para um
  destino que rende 8 consome 1,25 receitas. É o objetivo do pedido, e é por isso que `prever` e
  `produzir` devolvem **`rendimento_do_local`** e a tela de produção mostra o número vigente com
  "nesta prateleira" — a linha mostrava o da ficha e iria mentir.
  ⚠️ **A ordem que quase me pegou**: na prévia, o `id_local` era resolvido TRÊS linhas depois de
  o rendimento ser lido. A prévia usava o rendimento da ficha e a produção o do local, para o
  mesmo pedido. O local se resolve ANTES.
  ⚠️ **Ficha homologada não troca de destino**, pela mesma razão dos itens: o rendimento divide o
  consumo, e mexer nele numa ficha publicada mudaria custo já apurado.
  ⚠️ **A cópia leva os destinos** (`_copiar_ficha`): nascer sem eles faria a produção para a
  vitrine voltar ao rendimento da câmara, calada. Quinto lugar onde um campo de ficha precisa
  entrar, junto com modelo, INSERT, `obter` e a tela.
  ⚠️ **A agenda guardava `id_local` desde o começo e a tela nunca o mandava** — caía sempre no
  local padrão do produto. Com rendimento por destino isso passaria a escolher o rendimento
  errado, em silêncio. Agora a agenda pergunta a prateleira; vazio segue no padrão do produto.
  ⚠️ Suíte própria: `smoke_rendimento_por_local.py` (23 checagens) — a prévia e a produção
  concordando no número, os dois papéis de local separados, a cópia levando os destinos e as
  três recusas.


- 🔑 **De onde vem o RENDIMENTO: da soma dos ingredientes** (`custos.rendimento_sugerido` +
  `POST /fichas/rendimento-sugerido`, 12/09/2026, pedido do dono: *"tem como ser gerado
  automaticamente? o sistema que a cliente utiliza soma todos os ingredientes e gera isto"*).
  A fórmula é a da área: **Σ (líquido convertido para massa × fator de cocção)**.
  ⚠️ **SUGESTÃO, nunca escrita sozinha — e isso é o ponto.** `rendimento_qtd` DIVIDE o consumo
  na produção (`lotes = quantidade ÷ rendimento`): recalcular ao salvar mudaria o custo
  unitário de tudo que a ficha produz, calado, e o CMV do mês com ele. Fora que há receita em
  que a soma não é o rendimento — massa que descansa, calda que reduz de propósito. A tela
  mostra o número com um "usar" de um clique; quem decide é quem lê.
  ⚠️ **A rota recebe os ITENS, não um id de ficha**: a tela precisa do número enquanto a
  receita está sendo montada, e em ficha nova não há nada gravado. Sem estado, serve aos dois
  casos com uma rota só.
  ⚠️ **Três coisas que a soma precisa saber**, e cada uma tem checagem na suíte:
  (1) **ML entra por densidade 1** e a resposta DIZ que assumiu — acerta em água e leite
  (1,03), erraria feio em óleo (0,92) e mel (1,42);
  (2) **UN entra pelo peso cadastrado no produto**, em dois passos — quanto o item vale na
  unidade de estoque, e quanto pesa UMA unidade de estoque (a equivalência de peso, lida ao
  contrário). ⚠️ A primeira versão chamou `fator_de_embalagem(produto, um)` direto, que
  responde "quantas unidades de estoque cabem em 1 UN" — para o próprio `um_estoque` não
  existe linha nenhuma, e o ovo ficava fora da soma com o peso cadastrado ali do lado;
  (3) **o que soma é o LÍQUIDO**: 1 kg de cenoura com casca vira 800 g na panela — o bruto é o
  que sai do estoque e custa.
  ⚠️ **Quem não sabe dizer o peso fica de FORA e é NOMEADO** na resposta. Somar "3 UN" como
  3 G seria dizer que três ovos pesam três gramas; rendimento que ignora metade da receita em
  silêncio é pior que rendimento nenhum. A tela lista quem ficou fora e diz o caminho
  (cadastrar o peso de uma unidade no produto).
  🔑 **O `fator_coccao` finalmente entra numa conta.** Está no banco desde a migração 006 com
  `-- muda rendimento, não custo` escrito na coluna, era exportado no relatório e **nenhuma
  tela o oferecia**: ficava 1 em toda ficha. Agora tem campo por item e vale na soma — e
  continua fora do custo, como a coluna sempre disse: o custo é do que saiu do estoque, não do
  que sobrou na assadeira.

- 🔑 **O tamanho da porção, e a conta nos DOIS sentidos** (`fichas_tecnicas.porcao_qtd`,
  migração 065, 12/09/2026, pedido do dono: *"hoje temos somente a quantidade de porções, mas
  podemos ter ao contrário: informar os gramas/kg/un e ele calcular quantas porções rende"*).
  Faltava exatamente esse dado: `porcoes` é contagem pura, e de contagem não se deduz tamanho.
  ⚠️ **Na unidade do RENDIMENTO**, não numa própria: porção em G numa ficha que rende em L é
  conta que ninguém fecha, e `rendimento_um` já está gravado ao lado.
  ⚠️ **Nulo é resposta** ("ninguém informou") e é o padrão. A tela mostra o valor derivado
  (`rendimento ÷ porcoes`) como sugestão do campo, sem gravar palpite.
  ⚠️ **Não mexe em `porcoes`**, que continua sendo o que divide o custo: derivá-la em consulta
  mudaria o custo por porção de toda ficha existente no instante em que alguém informasse um
  tamanho.
  ⚠️ **Na tela, mexer num recalcula o outro — na digitação, não num efeito.** Efeito sobre os
  três campos criaria ida e volta (porções mexe no tamanho, que mexe nas porções). E trocar o
  rendimento mantém o TAMANHO e refaz as porções: é o que a cozinha fixa — mais massa não muda
  a fatia, muda quantas fatias saem.
  ⚠️ **A armadilha que custou uma suíte inteira acusando o INSERT certo**: `obter` monta a
  resposta **campo por campo**. `SELECT f.*` trazia a coluna nova, o INSERT gravava o valor, e
  a leitura o deixava de fora — sintoma "grava certo e volta nulo". Campo novo em ficha entra
  em quatro lugares: modelo de entrada, INSERT do `criar`, `_copiar_ficha` e **o dicionário do
  `obter`**.


- 🔑 **Duplicar a receita para OUTRO produto** (`POST /fichas/{id}/duplicar`, 12/09/2026,
  pedido do dono: *"tenho Bolo de Morango e Bolo de Banana, a base da receita é a mesma, então
  gostaria de duplicar e ajustar, retirando o que não vai e adicionando o que precisa"*). Sem
  isto a segunda receita era redigitada item por item — e é aí que uma entra com 200 G de
  farinha e a outra com 250, sem ninguém ter decidido nada.
  🔑 **A cópia já existia: era `nova-versao`.** Ela copia cabeçalho, itens e o ARQUIVO da foto
  desde 01/09; a única coisa que faltava era o produto de destino. Então o código virou um
  `_copiar_ficha(cur, f, id_produto, id_usuario)` que as duas rotas chamam — escrever a
  segunda cópia à mão seria garantir que um dia uma delas esquecesse o fator de correção.
  ⚠️ **Nasce em RASCUNHO, e o destino pode já ter ficha**: a cópia entra como a versão
  seguinte e a vigente continua valendo até alguém homologar a nova. É a mesma regra de
  `nova-versao`, e a janela DIZ isso antes de confirmar, com a versão que vai sair.
  ⚠️ **A guarda que `descendentes_da_ficha` não pega**: se a receita copiada usa uma sub-ficha
  **do produto de destino**, a cópia nasceria dizendo que o bolo leva bolo. Não é ciclo de
  estrutura (são duas fichas diferentes, e o detector não acusa nada), então a checagem olha o
  PRODUTO por trás da sub-ficha e recusa com essa frase.
  ⚠️ **O destino também vira produção própria**, como em `criar`: sem isso o bolo novo teria
  receita e não apareceria na agenda de produção.
  ⚠️ **A busca do destino lista só PRODUZIDOS** (decisão do dono no mesmo dia, depois de a
  primeira versão não filtrar). O receio era repetir o caso em que um recorte fez "o prato que
  se queria virar invisível", já que `KIT` também aceita ficha. Medido antes de decidir: **zero
  kits** na base e as 46 fichas todas em produzidos — o filtro não esconde nada e tira da frente
  600 insumos, revendas e utensílios que nunca serão destino de receita. É o mesmo recorte da
  tela de CRIAR a ficha (`fonteProduzidos`), então as duas buscas respondem igual.
  ⚠️ O recorte vai como query do SERVIDOR (`tipo=PRODUZIDO` no `extra`), nunca como peneira no
  navegador: filtrar depois cortaria a página trazida e a busca diria "nenhum resultado" para um
  prato que existe na página seguinte. E a guarda de tela continua valendo, porque o servidor
  aceita os dois tipos — no dia em que houver kit com ficha, tirar a string devolve o anterior.
  ⚠️ **O botão aparece em rascunho também**, ao contrário de "criar nova versão": copiar não
  muda esta ficha, e a base de uma receita nova costuma estar na que ainda se está escrevendo.
  ⚠️ **Produto de destino EXISTENTE.** Cadastrá-lo na janela pediria tipo, unidade, categoria
  e setor — um cadastro inteiro dentro de uma janela de cópia. Quem duplica já tem o bolo de
  banana cadastrado; quem não tem, cadastra em Produtos, que é onde essas perguntas moram.
  ⚠️ A suíte de fichas foi de 55 para 71 checagens: a cópia item a item (mesmas quantidades,
  unidades e fatores), a origem intacta, a segunda cópia caindo na v2, as duas recusas e o
  404. E a bateria do navegador dirige a janela até a ficha nova, com o ingrediente à vista —
  confirmar que o botão existe não diz que a receita veio junto.


- 🔑 **A ficha técnica ganhou FOTO do prato pronto** (01/09/2026, pedido do dono). A coluna
  `fichas_tecnicas.foto_url` **existe desde a etapa 3 e nunca tinha sido usada** — não houve
  migração. A ficha é seguida por quem está de pé na cozinha, e *"está pronto?"* é uma pergunta
  **visual**: nenhuma descrição de montagem responde o que a imagem responde. Ela aparece no
  cartão do prato, vira miniatura na lista de fichas e **sai no PDF**, que é o papel que fica
  pendurado.
  🔑 **A foto é a EXCEÇÃO da regra "ficha homologada não se edita".** A ficha publicada é
  congelada porque mexer nela mudaria custo histórico; a foto não entra em conta nenhuma. E o
  prato só pode ser fotografado DEPOIS de pronto, que é depois de homologado — a trava
  obrigaria a abrir uma versão que não difere em nada, e cada versão carrega histórico de
  custo. Mesmo raciocínio do nome do inventário, editável com a contagem fechada: rótulo não
  mexe em item nem em razão.
  🔑 **A nova versão leva a foto, e `arquivos.copiar` duplica o ARQUIVO — não a URL.** Copiar só
  a URL deixaria as duas fichas apontando para o mesmo arquivo, cujo `dono` é a versão VELHA — e
  `salvar_imagem` apaga as versões anteriores do mesmo dono. Trocar a foto da versão 1 apagaria
  a da versão 2, que ninguém tocou, e a imagem sumiria da tela sem nada explicando. A suíte
  cobra exatamente esse caminho.
  ⚠️ **No PDF ela sai AO LADO do resumo, não abaixo.** A caixa do resumo tem 106 mm e a página
  em retrato tem 186: sobrava metade da largura vazia, e a foto embaixo empurraria os
  ingredientes para a segunda página — que é justamente a que ninguém pendura.
  ⚠️ **`larga_max` porque foto de celular vem DEITADA**: a 34 mm de altura ela passa dos 78 mm
  da coluna e estoura a tabela. O `_figura` saiu de dentro do código da logo, que já fazia
  altura fixa com largura proporcional e já tolerava imagem ilegível — os dois usam o mesmo
  helper agora.
  ⚠️ **Ver a foto NÃO depende de `fichas.custos`**: ela não é dinheiro. Quem manda a foto
  precisa de `fichas.editar`.
  ⚠️ **O `dono` do arquivo é a FICHA, não o produto** (`ficha-{id}`): duas versões do mesmo
  prato podem ter fotos diferentes, e é a montagem que muda entre elas.
  🔑 **O cartão aparece TAMBÉM na tela de CRIAR, e a primeira versão o escondia ali.** A ficha
  nova não tem id e a foto não teria para onde ir — então o cartão simplesmente não existia em
  `/fichas/nova`. Só que é EXATAMENTE ali que a pessoa está com a foto na mão, e ela concluiu
  que o sistema não tinha o campo (foi assim que o dono o encontrou faltando, no mesmo dia).
  Agora a imagem fica guardada no estado e sobe logo depois do `POST /fichas`, com prévia local
  (`URL.createObjectURL`, revogada na limpeza) enquanto não há nada no servidor.
  ⚠️ **Falhar o envio da foto NÃO é "não foi possível salvar"**: a ficha já existe daquele
  ponto em diante, e a frase genérica mandaria cadastrar tudo de novo — criando uma segunda
  ficha do mesmo prato. O `try` é só do upload, e a mensagem diz o que aconteceu e onde
  reenviar.
  ⚠️ **E a checagem do estado vazio mudou de lugar por causa disso**: "diz quando não há
  nenhuma" era afirmado na tela da ficha recém-criada — que agora nasce COM foto. O único lugar
  onde o vazio é garantido é a tela de criar, antes de escolher o arquivo. Mesma família do
  teste que descreve o estado do dia.
  🔑 **O seletor de arquivo do NAVEGADOR não conta como botão** (01/09/2026, segunda correção
  no mesmo dia). A primeira versão usava o `<input type="file">` cru: ele tem a cara do sistema
  operacional, muda em cada máquina e não se parece com nada mais do sistema — o dono olhou a
  tela e **não achou o botão**, com o campo bem ali. Agora é o corte da tela de Empresa: input
  `hidden` e um `.btn btn-secundario` que o clica ("Escolher imagem" na ficha que ainda não
  existe, "Enviar imagem" na que existe sem foto, "Trocar imagem" com foto).
  ⚠️ **E o teste passava assim**, porque perguntava só se o input EXISTIA — e input escondido
  responde "sim" do mesmo jeito. Passou a exigir o botão da casa e o campo fora da vista.
  ⚠️ Casar por `button.btn` DENTRO do cartão, não por texto solto na página: o rótulo "remover"
  ficou igual ao da empresa, e a checagem que procurava "remover foto" quebrou no instante em
  que os dois passaram a falar igual.
  ⚠️ **A suíte apaga a foto ANTES de arquivar a ficha**: arquivar não apaga o arquivo (nem
  deveria — ficha arquivada continua respondendo pelo histórico), e sem isso cada rodada
  deixaria mais duas imagens na tabela `arquivos`.
  ⚠️ **O corpo multipart precisa do CRLF antes do fecho da fronteira.** Sem ele o servidor não
  acha o campo e devolve 422 "Field required" — que se lê como rota errada, não como teste
  errado. Custou meia hora na primeira versão do helper da suíte.

- 🔑 **A ficha técnica se imprime** (`GET /exportar/ficha/{id}.pdf`, botão em `/fichas/[id]`,
  29/08/2026). A ficha existe para ser SEGUIDA, e quem segue está de pé na cozinha — não na
  frente do monitor. Sem o papel, a receita fica presa numa tela que ninguém leva para perto
  do fogão.
  🔑 **Ver a ficha e ver o CUSTO são permissões diferentes, e o PDF não podia ser a porta
  lateral disso.** Sem `fichas.custos` nenhuma coluna nem linha de dinheiro entra no arquivo —
  quem esconde é o servidor, como já era no JSON. Um PDF é justamente o que SAI da tela e
  circula; se o dinheiro vazasse por aqui, a regra do router de fichas viraria enfeite. A
  suíte cobra isso nos dois formatos.
  ⚠️ **O modo de preparo não é tabela** — é o texto que se lê enquanto se cozinha. `csv_de` e
  `pdf_de` ganharam `notas=[(rótulo, texto)]`, que fecham o documento depois dos ingredientes,
  na ordem em que se usa. No PDF a quebra de linha vira `<br/>`: o `Paragraph` do reportlab
  ignora a quebra crua e um preparo numerado sairia em bloco corrido.
  ⚠️ **Coluna sem informação SAI da ficha** — mesma regra da folha de contagem, que só mostra o
  local quando a contagem cobre mais de um. Numa receita simples "Qtd líquida" e "Observação"
  vêm vazias em todas as linhas e "Fator correção" é 1,00 repetido: três colunas mortas
  empurravam o documento para PAISAGEM. Sem elas a ficha cabe em **retrato**, que é o formato
  de quem vai pendurar o papel. Elas voltam sozinhas na receita que as usa — quem descasca
  cebola tem fator de correção, e aí a coluna é a informação mais importante da linha.
  ⚠️ **`exportacao.quantidade_br` existe porque texto MONTADO à mão escapa da formatação**: o
  resumo dizia `Rendimento;2.0000 UN` — ponto decimal e quatro zeros no meio de um CSV que usa
  vírgula em todo o resto. O valor virava string antes de passar pelo formatador, e nenhuma das
  duas formatações o alcançava. Os zeros à direita saem: "1,0000 UN" não informa mais que
  "1 UN", só sugere uma precisão que não existe ali.
  ⚠️ **`formatoPadrao` na janela**: o padrão é planilha porque a maioria dos relatórios é para
  CONFERIR, mas a ficha e a folha de contagem têm o papel como destino — abrir em "planilha"
  ali faz escolher errado por inércia.

- 🔑 **O nome do arquivo carrega o nome do REGISTRO** (`exportacao.slug`, 29/08/2026).
  `botane-ficha-431.pdf` obriga a ABRIR o arquivo para saber de que prato ele é — e quem baixa
  cinco fichas seguidas fica com cinco números na pasta de Downloads. Agora sai
  `botane-ficha-bolo-de-cenoura-v2-20260829.pdf`.
  ⚠️ **A versão entra junto na ficha**: duas versões do mesmo prato são dois documentos
  diferentes, e sem ela a segunda sobrescreveria a primeira.
  ⚠️ Acento vira letra sem acento e o resto vira hífen — nome de arquivo atravessa Windows,
  e-mail e nuvem, e cada um estraga um caractere diferente. Com teto de 45 caracteres.
  ⚠️ Vale também para a folha de contagem (`inventario-camara-fria`) e para a folha do produto.

- **`fonteDaLista()`** serve a janela a partir de uma lista já carregada (as receitas da
  produção). Mesma janela, outra origem.

- 🔑 **O custo do insumo passou a ser da LOJA** (31/08/2026, primeiro passo da segunda loja).
  `custos.custo_do_insumo` somava `estoque_saldos` inteiro, sem filtrar `id_unidade`: o café que
  a matriz comprou a R$ 40/kg e a filial a R$ 52/kg valia **R$ 45,30 nas duas — e nenhuma pagou
  isso**. Não ficava contido: alimenta a ficha, o custo **CONGELADO** do item de venda e a baixa
  por vínculo, ou seja contaminava ficha, CMV teórico, margem e food cost das duas ao mesmo
  tempo. E era silencioso — nenhum valor ficava absurdo, só errado, e gravado.
  A loja atravessa agora `custo_do_insumo` → `custo_da_ficha` (e as sub-fichas) → 
  `custo_teorico_do_produto` → `kits.custo`. Quem GRAVA passa a loja: importação de venda,
  reconciliação do cardápio, baixa do Vincular e previsão de produção.
  ⚠️ **Sem `id_unidade` a conta continua sendo a da REDE, e é proposital**: há caminhos que
  perguntam o custo fora de uma operação de loja — prévia de ficha, relatório consolidado — e
  para eles a média geral é a melhor resposta disponível.
  ⚠️ **A reserva é o último preço do FORNECEDOR, e ela é da rede** (decisão do dono): preço
  negociado vale para as duas lojas, e é o que deixa a filial nova calcular ficha e CMV antes de
  ter recebido o insumo. Cair no médio da OUTRA loja seria voltar a misturar o que o filtro
  separa, e sem dizer que misturou.
  🔑 **A loja nova nasce com um LOCAL, principal.** Sem local nada se movimenta, e a mensagem
  era "Local não encontrado", que não diz o que fazer. O nome é genérico ("Estoque") de
  propósito: é para ser renomeado, não para fingir que se sabe como a casa chama a prateleira.
  🔑 **E `/locais` não filtrava por loja** — filtrava por "o que a pessoa pode VER"
  (`ve_unidade`), que para quem enxerga todas devolve tudo. Assim que a filial existiu, o
  administrador passou a ver os locais das duas na mesma lista, **com dois "Estoque" marcados
  como principal**, e SETE checagens caíram em quatro suítes. Elas estavam certas: a segunda
  loja provou. ⚠️ Mesma correção que vendas e inventários já precisaram — **toda lista de coisa
  que tem `id_unidade` nasce com essa dívida**.

- 🔑 **A logo e a foto da ficha PODIAM SUMIR na troca, e a janela era de duas transações**
  (02/09/2026, pedido do dono: *"garantir que a imagem da ficha técnica não seja perdida, a logo
  da empresa por vezes foi perdida também"*). Gravar uma imagem eram **três** transações: ler a
  URL atual; inserir a nova **e apagar a antiga**; e só então apontar o registro para a nova.
  Falhando a última — a API reiniciada, a requisição abortada, um erro no meio —, a antiga já
  não existia e o registro continuava apontando para ela: a imagem sumia da tela e do PDF, com
  o link quebrado e nada explicando. Agora inserir, apontar e apagar são **uma transação só**.
  ⚠️ `arquivos.salvar_imagem` deixou de existir e virou duas peças: **`ler_enviada`** (valida e
  devolve os bytes, sem tocar no banco) e **`gravar(cur, …)`**, que insere no cursor de quem
  chama. `remover` e `copiar` passaram a aceitar o cursor pela mesma razão.
  ⚠️ **`gravar` não apaga nada** — quem apaga é `remover`, chamado pelo dono do registro DEPOIS
  de a URL nova estar gravada, no mesmo cursor. Era o `salvar_imagem` apagando por conta própria
  que abria a janela.
  ⚠️ **Os bytes são lidos ANTES da transação**: ler 2 MB da rede com uma conexão do pool presa
  é prendê-la pelo tempo do ENVIO, não pelo tempo do banco.
  🔑 **Mas a perda que de fato aconteceu foi outra: as SUÍTES apagavam a logo do cliente.**
  `smoke_exportacoes` e `verificar.mjs` sobem uma logo de teste por cima e depois chamam
  `DELETE /empresa/logo`, com o comentário *"a real é a que o cliente subir"* — só que a real já
  estava lá. A marca sumia da barra superior e do cabeçalho de todo PDF emitido depois, e quem
  rodou a bateria não tinha como ligar uma coisa à outra. `comum.preservar_logo` (registrado no
  **`atexit`**) e o `restaurarLogo` em `aoTerminar` devolvem os BYTES que encontraram. Mesma
  lição do `preservar_credenciais` e do `devolver_o_modo_original`: **suíte devolve o que
  encontrou**, nunca um estado "limpo" que ela supõe ser o certo.
  ⚠️ **Sem logo também é um estado a devolver**: não havendo nenhuma antes, o restauro APAGA a
  de teste em vez de deixá-la lá.
  ⚠️ **A URL muda a cada envio** (o sufixo aleatório é o que invalida o cache do navegador), e
  por isso a checagem compara os **bytes**, nunca o endereço.
  ⚠️ **E `limpar_dados.py` deixava as fotos órfãs.** `arquivos` não entra no TRUNCATE de
  propósito — é lá que mora a logo, que é cadastro e fica —, mas a foto do prato tem
  `dono = 'ficha-<id>'` e as fichas saem: sobravam megabytes apontando para nada, e o
  `RESTART IDENTITY` ainda faz a numeração recomeçar, então uma ficha nova herda o id de uma
  cujo arquivo continua ali. Agora o script apaga só o que é de ficha; a logo não é tocada.

- **`services/kits.py`** (19/08/2026): combo/kit — a linha única do PDV que vale por vários
  produtos. `KIT` já era um tipo previsto em `produtos.tipo` e nunca tinha sido implementado:
  o combo não é produzido (sem ficha) nem estocado (sem custo médio), então entrava no CMV
  teórico **sem custo**. ⚠️ A composição aponta para **produto**, não para ficha (ao
  contrário de `ficha_itens`): ficha é uma VERSÃO, e o combo preso a uma versão continuaria
  calculando pela receita velha depois de a cozinha homologar a nova. Cada componente resolve
  o custo pela regra dele. Componente sem custo **não zera** o combo — o que se sabe entra e a
  origem vira `kit_parcial`, para o buraco aparecer em vez de sumir. Ciclo recusado na
  gravação, com trava de profundidade por segurança (igual às fichas).

- **A folha da produção** (`/producao/[id]`, `estoque.previsao_producao`): clicar no nome da
  linha abre o que a produção VAI precisar — por unidade, no total, o que existe no local de
  onde vai sair e o que falta. Roda a MESMA conta da produção (rendimento, conversão de
  embalagem, local de cada insumo); prever com outra regra seria prever outra coisa.
  ⚠️ A previsão é sempre de AGORA, nunca a de quando se agendou. ⚠️ Sub-ficha aparece como o
  PRODUTO dela, não explodida — é isso que a produção consome de fato.
  ⚠️ Resolver `id_local` como a produção resolve (cai no principal): sem isso o saldo era
  procurado num local nulo e a folha dizia que faltava tudo.

- **Agenda de produção** (`producao_agenda` + `services/producao_agenda.py`): o PLANO, que
  não mexe no estoque — quem mexe é a produção, quando a linha é cumprida. ⚠️ A quantidade
  produzida pode sair diferente da planejada (a cozinha rendeu outra coisa) e as duas ficam
  registradas. Agendar o mesmo produto no mesmo dia **soma** em vez de duplicar: quem agenda
  de novo aumenta o lote, não abre outra ida ao fogão. Produto `NA_HORA` não se agenda.
  ⚠️ A sugestão repõe até o **máximo**, não até o mínimo — produzir só até o mínimo deixa a
  casa raspando o limite no dia seguinte.

- **`tests/cenario_cafeteria.py`**: a casa inteira funcionando uma vez, com números conferidos
  no papel (frete rateado, embalagem convertida, médio ponderado, ficha, sub-ficha, produção,
  perda, transferência, inventário, venda e o fechamento das identidades). 57 checagens.
  ⚠️ Mede **delta** da apuração e soma só os produtos do próprio cenário — a base pode ter
  outra coisa.

- 🔑 **A ficha em RASCUNHO custeia a venda — e a origem DIZ isso** (02/09/2026, pedido do dono).
  O prato com receita ainda não homologada entrava no item de venda com custo **ZERO**: o CMV
  teórico saía subestimado, a margem alta demais e o food cost bom demais, **sem nada
  denunciando** — o item nem contava como "sem custo" na leitura de quem olhava o número. A
  cozinha escreve a receita muito antes de alguém homologá-la, e o prato já está sendo vendido
  nesse meio tempo, que é exatamente quando o número importa.
  ⚠️ **A homologada vem PRIMEIRO, sempre.** O rascunho é a reserva e só responde quando não há
  versão aprovada vigente — senão homologar uma receita não mudaria o custo de nada.
  ⚠️ **Vale só para CUSTEAR. A PRODUÇÃO continua exigindo ficha homologada**: ali a receita move
  mercadoria de verdade no razão, e seguir uma versão não aprovada baixaria estoque errado.
  ⚠️ **O custo continua CONGELADO no item de venda.** O rascunho muda depois, então duas vendas
  do mesmo prato podem ficar com custos diferentes — e está certo: cada uma guarda o que se
  sabia na hora dela. A suíte cobra que homologar depois **não reescreva** a venda anterior.
  ⚠️ Origens novas: `ficha_rascunho`, `ficha_rascunho_parcial` e `ficha_rascunho_sem_custo` —
  espelhando as três que já existiam. `ORIGEM_CUSTO` (front) as nomeia em português.
  ⚠️ **O aviso é obrigatório, e é o que o pedido dizia** ("avisa que tá em rascunho ainda"):
  `GET /vendas/{id}` devolve `itens_ficha_rascunho` e a tela mostra o aviso ANTES dos números,
  como já fazia com o item sem custo. Sem ele, o custo de uma receita em rascunho seria
  indistinguível do de uma aprovada. A resposta da importação também conta — e a frase só cita
  o número **quando ele não é zero**, senão vira ruído em toda importação.

- **O custo da ficha é congelado no item de venda** (`venda_itens.custo_ficha_unitario`):
  corrigir receita hoje não reescreve o CMV teórico do mês passado.

- Compras contam só `ENTRADA_NF` e `ENTRADA_MANUAL`; produção e transferência são
  transformação interna e se anulam na conta.

- 🔑 **A suíte pegava "a primeira ficha HOMOLOGADA" e caía numa de produto INATIVO.** Produto
  com movimento vira inativo em vez de sumir, e a ficha dele fica: a base tinha **57** fichas
  homologadas apontando para produto desativado. Agendar produção numa delas devolve 400 "está
  inativo" — e o POST não era conferido, então a agenda ficava vazia e a falha aparecia **três
  checagens adiante**, dizendo que a agenda não abre a folha. Duas correções, e as duas valem
  como regra: **filtrar pelo produto ATIVO** e **conferir o POST que monta a precondição**.

- 🔑 **O que REALMENTE foi usado, insumo a insumo** (`consumos`, migração 073, 16/09/2026,
  pedido do dono: *"na lista de insumos, ter uma nova coluna com o que realmente foi usado. Por
  padrão é a mesma quantidade, mas o usuário pode alterar, inclusive a unidade — por exemplo, na
  receita vão 5 ovos, mas por um acaso usei 6."*).
  🔑 **O razão SEMPRE foi capaz disso; o que faltava era a porta.** A produção já gravava o que
  saiu, e o custo do produzido já era "o que realmente saiu, não o teórico da ficha" — só que a
  quantidade vinha calculada da receita, sem ninguém poder corrigi-la. Quem usava seis ovos
  lançava cinco, e o sexto sumia do controle até aparecer no inventário como falta sem causa.
  ⚠️ **A correção viaja pela LINHA da receita (`id_item`), não pelo produto.** A mesma ficha pode
  listar o mesmo insumo duas vezes (a manteiga da massa e a de untar), e corrigir "a manteiga"
  mexeria nas duas.
  ⚠️ **A unidade passa pela mesma `converter_para_estoque`** (embalagem do produto, depois
  grandeza). Sem caminho, é recusa: aceitar 1:1 faria "usei 2 CX" baixar duas unidades. A tela só
  oferece as unidades que a conversão conhece — oferecer o resto seria convidar a recusa.
  ⚠️ **Zero é aceito e NÃO vira movimento.** "Não usei" é resposta legítima (acabou, substituí), e
  uma linha de quantidade zero no razão diria que algo se moveu.
  ⚠️ **Correção de linha que a ficha não tem é RECUSA**, com a frase "a receita mudou desde que
  esta folha foi aberta": gravar seria gravar uma produção diferente da que a pessoa viu.
  ⚠️ **Só viaja o que foi TOCADO na tela.** Mandar todas as linhas faria o número ARREDONDADO da
  tela virar o gravado — 0,626 KG no lugar de 0,62642 — e marcaria toda produção como corrigida.
  Linha não tocada é a receita, e a receita o servidor já sabe calcular.
  🔑 **`producoes.consumo_ajustado` é um AVISO, não um dado novo**: tudo o que ele diz já está nos
  movimentos, bastando comparar com a ficha. Ele existe para a comparação não precisar ser feita —
  produção que se afasta da receita com frequência é ficha errada, e isso é uma pergunta que
  alguém tem de fazer olhando a lista. O movimento também carrega "· quantidade corrigida" na
  observação, para quem conferir o razão seis meses depois sem a ficha ao lado.

- 🔑 **A folha da produção é da COZINHA, não do escritório** (`/producao/{id}`, 16/09/2026,
  pedido do dono: *"na tela que lista a produção, onde são listados os insumos, podemos focar mais
  na produção que nos custos — quem vai ver esta tela precisa saber as quantidades e o modo de
  preparo, e não os custos. Dar mais foco nisto e disponibilizar a impressão desta tela, para que
  seja passada para a produção."*). Três mudanças, e elas andam juntas:
  🔑 **O modo de preparo entrou** (`previsao_producao` passou a trazer `modo_preparo`,
  `tempo_preparo_min`, `alergenos` e a observação da ficha). Sem ele a folha era meia folha: a
  pessoa levava a lista de ingredientes e abria a ficha noutra tela para saber o que fazer com
  eles. ⚠️ `whitespace-pre-line` na tela: o preparo é escrito em passos, e texto corrido apaga a
  ordem que alguém escreveu.
  🔑 **O custo saiu da tabela.** Era uma coluna ao lado das quantidades, disputando a mesma
  leitura — e quem está na bancada não decide nada com ele. Continua na tela, numa linha ao pé,
  para quem tem `fichas.custos`. E o QUANTO produzir virou o maior texto da página: é a única
  coisa que se lê de longe, com as mãos ocupadas.
  ⚠️ **O custo NÃO é impresso** (`nao-imprimir`). A folha é passada de mão em mão na cozinha;
  mandar o custo do prato junto é distribuir margem por engano.
  🔑 **E a impressão só funcionou depois de desfazer a GRADE do esqueleto.** `@media print`
  escondia o `aside`, mas o esqueleto é `lg:grid-cols-[276px_minmax(0,1fr)]` — esconder o menu não
  tira a coluna dele, e o conteúdo ia parar na faixa de 276px com as colunas da direita cortadas.
  Na folha isso comia justamente a coluna "Total", que é a que a bancada vai pesar, **e o papel
  não denuncia o corte como a tela denuncia, com a barra de rolagem**. Agora `@media print` põe
  `.esqueleto { display: block }`, solta o `max-width` do miolo e torna `.overflow-x-auto`
  visível. ⚠️ Junto saiu o `break-inside: avoid` do cartão INTEIRO, que empurrava lista longa para
  a página seguinte e cortava quando ela não cabia em nenhuma: a unidade que não se parte é a
  LINHA.

- 🔑 **Os MODOS de rendimento da ficha** (`ficha_modos`, migração 072, 16/09/2026, pedido do
  dono: *"no cadastro de ficha posso cadastrar o padrão — o Cookies Flat rende 8,535 KG em 65
  porções, a receita toda. E podemos criar mais modos de rendimento para diferentes setores, com
  um nome, e este será o modo selecionado ao agendar ou produzir. Modo padrão é produzir a receita
  toda para estoque; podemos ter um Modo Consumo, com o setor Bar e 30 porções; ou outro onde as
  porções são menores."*).
  🔑 **O que o modo muda não é ESCALA, é a PORÇÃO.** Produzir 30 em vez de 65 sempre funcionou: a
  quantidade é livre e o consumo é proporcional. O que não existia era a mesma massa render *outra
  coisa* — os mesmos 8,535 KG em 130 unidades menores, que é outro custo unitário e outra contagem
  de estoque. É isso que merece cadastro com nome.
  ⚠️ **`ficha_locais` VIROU `ficha_modos`, não convive com ela.** A tabela da migração 066 já era
  um modo sem nome, escolhido por adivinhação a partir da prateleira. Duas réguas para a mesma
  pergunta divergem na primeira correção — e o rendimento DIVIDE o consumo: divergir aí custa
  ingrediente, não estética. A migração RENOMEIA (preserva ids, FKs e o CASCADE) e batiza cada
  linha antiga com o nome da prateleira dela.
  ⚠️ **A ficha continua sendo o Modo padrão, e ele NÃO vira linha**: materializá-lo custaria uma
  linha por ficha da base para não mudar comportamento nenhum.
  ⚠️ **A unidade do rendimento continua sendo a da FICHA.** Modo é a mesma receita rendendo outra
  coisa, não outra receita — deixar cada modo declarar a própria unidade abriria a porta para a
  ficha render em KG e o modo em UN, que é exatamente a ponte que a produção pagou caro para
  atravessar.
  🔑 **A ordem de `modo_da_producao`**: (1) o modo ESCOLHIDO — decisão de gente ganha de qualquer
  regra; (2) o modo desta PRATELEIRA — o comportamento da 066, que continua valendo para quem
  nunca vai escolher nada; (3) o modo deste SETOR — a prateleira do Bar herda o "Consumo — Bar"
  sem repetir o cadastro em cada prateleira dele; (4) a ficha.
  ⚠️ **Modo que não é desta ficha é RECUSA, não silêncio**: cair no padrão produziria com outro
  rendimento do que a tela mostrou, e ninguém veria.
  ⚠️ **Sumiu o índice único por (ficha, local)**: com modos, a mesma prateleira pode ter "Padrão
  da vitrine" e "Mini da vitrine" — era esse índice que impedia exatamente o que o dono pediu. O
  que não se repete agora é o NOME, que é por onde a pessoa escolhe.
  ⚠️ **Substituir DESATIVA o que sumiu, não apaga**: produções e linhas de agenda apontam para o
  modo que usaram, e apagar a linha levaria junto a resposta para "por que este lote rendeu 130?".
  O `PUT` casa pelo NOME (`ON CONFLICT (id_ficha, lower(nome))`), então um modo que só mudou de
  rendimento continua sendo o mesmo modo para quem aponta para ele.
  🔑 **A agenda e a produção GRAVAM o modo** (`producao_agenda.id_modo`, `producoes.id_modo`). Sem
  isso, agendar o "Modo mini" e cumprir a linha três dias depois sairia pelo rendimento padrão: a
  quantidade certa saindo da receita errada, e a diferença só aparecendo na contagem.
  ⚠️ **A `quantidade_sugerida` é preenchida na ESCOLHA, na tela, não na resposta do servidor** —
  vinda de lá ela sobrescreveria o que a pessoa está digitando a cada tecla.
  ⚠️ **O seletor de modo só aparece quando a ficha TEM modos.** Quase nenhuma tem, e um seletor de
  um item é um controle que não controla nada — é o que mantém a tela idêntica para quem não usa.

- 🔑 **O custo da ficha se ajusta ENQUANTO se digita** (`POST /fichas/previa-de-custo`,
  15/09/2026, pedido do dono: *"na ficha técnica, ao ir preenchendo os dados dos insumos, os
  valores demonstrados poderiam já ir ajustando na tela"*). Até então o custo só aparecia depois
  de salvar: quem montava uma receita escrevia no escuro e, se o número saísse estranho, tinha de
  descobrir sozinho qual linha o causou.
  ⚠️ **Recebe os ITENS, não um id** — como a prévia do rendimento, e pela mesma razão: numa ficha
  nova não há nada gravado para consultar.
  ⚠️ **A conta é a MESMA da ficha gravada.** O miolo saiu para `custos._custos_das_linhas` e os
  dois caminhos passam por ele; calcular no navegador seria a segunda versão da cascata de custo
  — a que converte unidade, desce em sub-ficha e escolhe entre custo médio, último preço e
  referência —, e ela divergiria na primeira correção.
  ⚠️ **Uma linha por item, na MESMA ordem em que chegaram**: a tela casa pelo índice, e devolver
  um subconjunto faria o custo aparecer na linha errada — pior do que não aparecer.
  ⚠️ A permissão é `fichas.custos`: a rota só devolve dinheiro.

- 🔑 **Só se agenda para prateleira onde o preparo MORA** (15/09/2026, pedido do dono: *"quando
  agendo uma produção, os setores/prateleira deveriam ser somente as que o produto pertence"*, e
  depois a regra geral: *"acho que em todo o sistema só podemos adicionar produtos para os quais
  eles têm cadastro"*). A lista da casa inteira deixava agendar para um canto em que o preparo
  nunca esteve — e não é erro que a tela pegue: aparece semanas depois, na contagem, como sobra
  num lugar e falta em outro.

- 🔑 **A quantidade da produção e o rendimento da ficha falavam unidades diferentes**
  (15/09/2026, relatado pelo dono: *"a ficha do COOKIES FLAT produz 65 porções, coloquei para
  produzir 2 e no estoque só entraram 2 UN"*). A quantidade está na unidade de **estoque** do
  produto (UN de cookie); o rendimento, na da **receita** (8,535 KG de massa). `qtd / rendimento`
  dividia unidade por quilo: 2 ÷ 8,535 = **0,234 receita** — 23% dos ingredientes para fazer dois
  cookies, quando o certo era 2/65 = 3,08%. Sete vezes e meia de manteiga, farinha e chocolate
  saindo do estoque, e o custo do cookie inflado na mesma medida (R$ 72,74 a unidade).
  A ponte mora em **`estoque._rendimento_em_estoque`** — quantas unidades de estoque UMA receita
  rende — e a ordem é: (1) as duas unidades são a mesma; (2) as **porções** (do destino, em
  do modo que está valendo, senão da ficha); (3) a grandeza (KG↔G, L↔ML). ⚠️ **Sem nenhuma das três é
  recusa**, com a frase mandando preencher as porções: produzir com fator inventado é o que
  custou sete vezes o ingrediente certo, e o erro só aparece no inventário do mês seguinte.
  ⚠️ **A prévia (`/producao-agenda/necessario`) usa a MESMA ponte** — prever com outra regra
  seria prever outra coisa, e a folha da bancada pediria sete vezes mais do que a receita precisa.

- 🔑 **Dá para pedir em PORÇÕES ou em RECEITAS** (15/09/2026, pedido do dono: *"na produção
  podemos ter como informar se vamos produzir X porções ou X rendimentos — a ficha tem rendimento
  de 10 KG sendo 60 porções; informar 2 rendimento gera 120 porções"*). `medida=PORCOES` (o
  padrão, e como sempre foi) é a unidade de estoque do produto; `medida=RECEITAS` são voltas
  inteiras da ficha. As duas contas sempre existiram — uma é o inverso da outra (`_quanto_produzir`);
  o que faltava era a pessoa poder dizer **qual das duas está digitando**. Sem isso "2" era
  ambíguo, e foi essa ambiguidade que fez uma produção inteira entrar como duas unidades.
  ⚠️ **O razão grava SEMPRE a unidade de estoque.** `RECEITAS` é um jeito de dizer quanto, não
  outra unidade de medida: gravar "2" com a etiqueta de receita faria o saldo do cookie contar
  receitas e o inventário da prateleira contar cookies.
  ⚠️ **A agenda traduz NA PORTA** (`estoque.quantidade_de_estoque`, chamado pelo router): quem
  agenda "2 receitas" deixa 130 UN no plano, e daí para dentro — resumo do dia, folha da bancada,
  produção que fecha a linha — ninguém precisa lembrar de traduzir. A primeira consulta que
  esquecesse produziria dois cookies.
  🔑 **A TELA nasce em RECEITAS; o SERVIDOR continua em PORCOES** (16/09/2026, pedido do dono:
  *"coloca como padrão a Receita na medida de produção"*). É assim que a cozinha pensa: ninguém
  decide fazer 130 cookies, decide fazer duas receitas. ⚠️ Mas o padrão do servidor não pode
  acompanhar — quem **não** manda o campo (a venda que produz na hora, a linha da agenda sendo
  cumprida, qualquer script) fala a unidade de estoque, e trocar o padrão de lá reinterpretaria
  todos eles de uma vez, calado. As duas telas mandam o campo sempre, e o padrão de cada uma é o
  mesmo: um por aba seria armadilha.

## Armadilhas já pagas

- 🔑 **Não dava para saber QUAL commit estava no ar, e isso custou uma ida e volta.** `VERSAO` é
  texto fixo, a lista de rotas só muda quando alguém cria endpoint, e correção de comportamento
  (um prazo de socket) não deixa rastro de fora — era impossível separar *"a correção não
  funcionou"* de *"a correção não foi publicada"*. `GET /saude` agora devolve **`impressao`**
  (hash do próprio código-fonte) e a **última migração aplicada**. O mesmo cálculo roda aqui:
  `cd api && python -c "import impressao; print(impressao.CODIGO)"`.
  ⚠️ **As pontas de linha são normalizadas antes do hash** (`

` → `
`): o repositório é
  clonado com CRLF no Windows e LF no contêiner, e sem isso o mesmo commit daria impressões
  diferentes — a ferramenta feita para responder "é o mesmo código?" responderia sempre "não".
  🔑 **Lista BRANCA, não lista negra.** A primeira versão excluía o que eu sabia nomear e contou
  **136 arquivos aqui contra 2.014 na produção**: o buildpack instala as dependências DENTRO da
  pasta da API, com um nome que ninguém previu, e o hash passou a incluir biblioteca de terceiros
  — comparando outra coisa que não o nosso código, e nunca batendo com o cálculo local. Lista
  negra depende de adivinhar tudo o que pode aparecer; branca só depende de saber o que é meu.
  A suíte cobra um **teto** de arquivos, não só um piso: com piso só, os dois casos passariam.
  ⚠️ **`arquivos/` e `uploads/` ficam de fora**: são dados de operação (o `.eml`, a logo) e mudam
  sozinhos com o uso — dentro do hash, a impressão mudaria sem ninguém ter publicado nada.

- **Ficha homologada não se edita** (mudaria custo histórico) — só nova versão. Ciclo de
  sub-ficha é recusado na gravação, e o cálculo ainda tem trava de profundidade por segurança.

- **`fichas.custos` filtra o JSON, não só a tela**: sem a chave, nenhum campo de dinheiro
  sai do servidor. Ao mexer no router de fichas, manter isso.

- **`custos.converter_para_estoque()` é a única regra de conversão** (20/08/2026):
  mesma unidade → **embalagem do produto** (`produto_unidades`, depois `um_compra/fator_compra`)
  → grandeza → `(None, "desconhecida")`. Ficha, produção e nota de entrada passam **todas** por
  ela. Antes só a nota consultava a embalagem: a mesma caixa valia 12 na entrada e 1 na ficha,
  e a produção baixava 1 pacote onde a receita pedia uma caixa de 12 — some com 11 do razão sem
  ninguém ver. Sem conversão conhecida a ficha **avisa** e a produção **recusa**; 1:1 calado é
  o que não pode acontecer. A ficha devolve `qtd_estoque`/`conversao` por item, e a tela mostra
  "no estoque 12 PCT".

- **Duas naturezas de produzido** (`produtos.modo_producao`, migração 021, 24/08/2026):
  `PARA_ESTOQUE` (a massa de pizza: produz, guarda, sai depois) e `NA_HORA` (o café passado:
  a venda produz e baixa no mesmo lançamento, e o saldo volta a zero). ⚠️ Sem o `NA_HORA` a
  casa venderia mil cafés e o pó continuaria inteiro no razão — ninguém registra produção de
  café a café. O par entrada/saída fica visível no razão de propósito.

## Fichas criadas pelo Claude (24/09/2026)

🔑 **Pedido do dono:** *"disponibilizar a criação de Fichas Técnicas pelo Claude, pois
ela tem muitas fichas em outros arquivos, e isto facilitaria muito a importação."*
Três ferramentas no conector (`services/mcp_ferramentas.py`): `criar_ficha_tecnica`
(`POST /fichas`), `atualizar_ficha_tecnica` (`PUT /fichas/{id}`, só rascunho) e
`nova_versao_da_ficha`. Todas pela MESMA rota da tela, com as mesmas recusas.
- ⚠️ **Nasce RASCUNHO e a homologação NÃO está no conector**, de propósito. Rascunho já
  custeia o prato no CMV (degrau reserva da cascata), então a importação serve na hora;
  homologar é o que libera PRODUZIR e congela a receita, e numa leva de dezenas de
  fichas lidas de arquivo um "10" que era "100" só aparece quando alguém olha — na tela,
  com o custo do lado. Se o dono pedir, é uma ferramenta a mais, sobre
  `POST /fichas/{id}/homologar` (permissão `fichas.homologar`).
- 🔑 **O roteiro mora na DESCRIÇÃO da ferramenta**: prato tem de ser PRODUZIDO/KIT;
  conferir `fichas_tecnicas` antes (criar de novo abre versão 2, não corrige); ingrediente
  vira `id_insumo` por `buscar_produtos`, perguntando antes de criar insumo; ler
  `ficha_tecnica` depois e avisar `itens_sem_custo`.
- ⚠️ `itens` SUBSTITUI a lista no `atualizar` (é o `_gravar_itens` da rota). A ordem do
  array vira a `ordem` — o campo não é exposto.
- Cobertura: bloco `7g` do `smoke_conector_claude.py`.

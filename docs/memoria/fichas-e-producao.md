# Fichas técnicas e produção

> Extraído do CLAUDE.md original (seções "O que já existe" e "Armadilhas já pagas").
> Consultar antes de mexer nesta área do sistema.

## O que já existe

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

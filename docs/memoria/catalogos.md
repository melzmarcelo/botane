# Catálogos

> A capa do que o **site de reservas** apresenta ao cliente: nome, período e situação.
> Leia antes de mexer neste módulo.

## O que já existe (migração 079, 21/09/2026)

🔑 **Pedido do dono:** *"vamos iniciar pelo cadastro de catálogos. Onde teremos o cabeçalho do
catálogo, origem — neste momento somente vamos ter PDF —, o nome dele no site do cliente, o
período de publicação, a situação: rascunho, ativo, inativo."*

🔑 **A correção que veio no mesmo dia, e que valeu por duas:** *"foi um erro meu de digitação.
A origem neste momento não seria PDV, e sim **PDF**, onde seria importado um PDF que seria
apresentado no **site de reservas**. O menu de catálogo fica **dentro de reservas**, onde
somente será demonstrada quando utilizado reserva."*
⚠️ **PDF é ARQUIVO; PDV é o caixa**, e vive em `services/pdv/`. As três letras parecidas
custaram a primeira versão inteira deste módulo — escrita inteira em cima da sigla errada,
com o catálogo pendurado no cardápio do PDV Legal, que não tem nada a ver.
🔑 **A lição não é "confira a sigla".** É que uma origem com UMA opção só não dá pista
nenhuma de estar errada: não há segunda entrada para comparar, nada quebra, e a suíte passa
verde sobre o engano. O que denunciou foi o dono reler o próprio pedido.

⚠️ **É só o CABEÇALHO.** Os itens do catálogo são a próxima fatia, e a tela diz isso em vez de
deixar a pessoa procurando onde se acrescenta um prato. Criar as duas de uma vez obrigaria a
decidir agora como o item se liga ao produto — decisão que fica melhor depois de a capa
existir e ser usada.

- **Tabela `catalogos`**, rotas em `routers/catalogos.py`, regra em `services/catalogos.py`,
  tela em `web/app/(app)/catalogos/`, camada de service em `web/lib/catalogos.ts`.
- **Permissões:** `catalogos.ver` e `catalogos.editar`, no módulo **Reservas**. ⚠️ **Salão
  fica de fora**, embora as outras chaves de Reservas o incluam: garçom atende telefone e
  marca mesa; publicar o que a casa mostra no site é de quem responde pelo cardápio.
  ⚠️ As chaves são concedidas **uma a uma**, não por `modulo = 'Reservas'` — senão a migração
  reconcederia as três chaves da 068 a quem alguém tivesse tirado de propósito.

- 🔑 **O módulo passa pela porta de `parametros.reservas_ligado`** (migração 068). Desligado,
  o catálogo **não existe**: o item some do menu (`soComReservas`, como os outros três) e as
  rotas recusam com **409**, dizendo onde se liga.
  ⚠️ **A trava do servidor não é redundância da do menu.** Esconder o item é conforto; o que
  impede uma casa sem reservas de ganhar catálogo é a recusa em `_unidade`. É a regra da casa
  desde sempre: nada de checagem só na tela.
  ⚠️ **409, não 403**: não é falta de permissão, é módulo desligado — e a frase diz o caminho,
  porque recusar sem dizer manda a pessoa procurar num menu que justamente não mostra o item.
  ⚠️ **`/opcoes` também passa pela porta.** Ela não devolve dado da loja, mas uma tela que
  não deveria abrir não deveria conseguir ler nem o vocabulário.

## As decisões que o dono tomou, e o que cada uma custa

- 🔑 **De cada LOJA**, não da empresa. Acompanha Reservas e a regra 5 do projeto: cada casa
  publica o seu, com nome e período próprios. ⚠️ Fosse da empresa, a primeira filial com
  cardápio diferente pediria migração para separar — e separar depois é mais caro que juntar.
  Toda consulta filtra `id_unidade`, e é essa linha que impede a filial de alterar o cardápio
  da matriz. É a lição que `listar_fechamentos` do CMV pagou caro.

- 🔑 **Vários ATIVOS ao mesmo tempo são PERMITIDOS** (*"vários, sem trava nenhuma"*). Por isso
  **não há** índice único sobre `situacao = 'ATIVO'` nem restrição de períodos sobrepostos.
  ⚠️ **A consequência fica escrita para não surpreender depois**: quem for publicar no site
  precisa de uma regra que escolha ENTRE os ativos, e essa regra ainda não existe — ela é da
  fatia do site, não do cadastro. A suíte afirma que vários ativos convivem, justamente para
  que ninguém "conserte" isso com um índice único achando que é defeito.

## O PDF, que é o que o site exibe (migração 080, 21/09/2026)

🔑 **Pedido do dono:** *"criei o catálogo, agora tenho que poder carregar o PDF, neste caso
para ele ser exibido."*

- 🔑 **O arquivo mora no BANCO, não em disco**, e quem cuida é `api/arquivos.py` — o mesmo
  lugar da logo. Não é preferência: o disco do App Platform é EFÊMERO, `api/uploads/` some a
  cada deploy, e a logo já sumiu assim uma vez. Um cardápio que desaparece na publicação seria
  pior — o site continuaria anunciando um catálogo no ar, sem nada para mostrar.
  ⚠️ **Em `catalogos` fica só a URL**; os bytes ficam em `arquivos`, e quem lê recebe um
  endereço sem saber de onde ele vem. No dia em que o Spaces entrar, só aquele módulo muda.

- ⚠️ **O `content-type` é só o que o NAVEGADOR diz.** `ler_pdf` confere os primeiros bytes:
  todo PDF começa com `%PDF-`, e quem renomeia um `.exe` para `.pdf` para aí. É a mesma
  desconfiança que `ler_enviada` tem com a imagem.
  ⚠️ **10 MB, não os 2 da logo**: o cardápio é ilustrado, e recusar o arquivo da casa por um
  limite pensado para um logotipo seria recusar o caso de uso inteiro.

- 🔑 **O nome ORIGINAL é gravado à parte.** A URL leva sufixo aleatório (senão o navegador
  serve o arquivo velho do cache) e não diz mais qual PDF é aquele — quem confere se subiu o
  certo precisa reconhecer o próprio arquivo. O tamanho também fica gravado: lê-lo exigiria
  trazer os bytes do PDF só para contar, uma vez por linha da lista.

- 🔑 **A rota que serve é PÚBLICA**, como a da logo: o site de reservas exibe o PDF sem token,
  e o navegador não manda cabeçalho de autenticação numa `<embed>`. O nome carrega sufixo
  aleatório, então a URL não é adivinhável.
  ⚠️ **PDF pode conter JavaScript**, e a rota vive no MESMO domínio da aplicação. Por isso ele
  sai com `Content-Security-Policy: sandbox` — sem script, sem formulário, sem acesso ao que é
  da casa — e `X-Content-Type-Options: nosniff`.
  ⚠️ **`Content-Disposition: inline`, porque o pedido é EXIBIR.** `attachment` forçaria
  download, e o site precisa mostrar o cardápio, não entregá-lo.

- ⚠️ **Gravar o novo, apontar para ele e apagar o velho são UMA transação.** É a lição que a
  logo pagou: a versão antiga gravava numa e apagava noutra, e um erro no meio deixava o
  registro apontando para um arquivo que já não existia.
  ⚠️ **Excluir o catálogo leva o arquivo junto** — senão os bytes ficariam no banco sem dono
  nenhum apontando para eles, invisíveis e crescendo.
  ⚠️ **Tirar o PDF NÃO apaga o catálogo**: trocar o cardápio é rotina, e apagar a capa junto
  perderia o nome, o período e o histórico.

- ⚠️ **Ativo sem PDF é avisado na lista, não escondido** (*"sem PDF — o site não tem o que
  exibir"*). É o estado em que a casa anuncia um cardápio e não há o que mostrar.

## As decisões de desenho

- 🔑 **"No ar hoje" NÃO é o mesmo que ATIVO, e é coluna própria na tela.** Um catálogo ativo
  cujo período terminou ontem não está publicado; mostrar os dois como iguais faria a casa
  procurar no site um cardápio que saiu do ar sozinho. Quem responde é o SERVIDOR
  (`_publicado_hoje`), porque é ele que sabe que dia é hoje na loja.

- ⚠️ **As duas pontas do período são OPCIONAIS, e querem dizer coisas diferentes.** Sem
  `publica_de` vale desde já; sem `publica_ate` vale sem prazo. O cardápio permanente da casa
  não tem período, e exigir datas dele obrigaria a inventar um "até 2099" que ninguém
  entenderia depois. A tela escreve o que cada vazio significa — sem isso a pessoa preenche
  uma data de fim inventada.

- ⚠️ **`origem` nasce com uma opção só e mesmo assim é COLUNA.** Hoje todo catálogo é um
  **PDF** importado e mostrado no site de reservas, e seria tentador não guardar o que não
  varia. Mas no dia da segunda origem — o cardápio montado item a item aqui dentro — os
  catálogos antigos precisam continuar sabendo de onde vieram; um DEFAULT posto naquele dia
  mentiria sobre o passado.

- 🔑 **O vocabulário (origens e situações) vem do SERVIDOR**, por `GET /catalogos/opcoes`.
  Escrever a lista na tela criaria a segunda cópia, e ela divergiria **calada** — é a lição
  das três listas de `TIPOS`. A suíte cobra as duas listas.

- ⚠️ **Nasce RASCUNHO.** Catálogo que nasce ativo é catálogo publicado antes de alguém
  conferir o que tem dentro.

- 🔑 **Só RASCUNHO se apaga; o resto se INATIVA.** Alguém leu aquele cardápio — apagá-lo tira
  do sistema o que a casa publicou, e é o tipo de coisa de que se sente falta meses depois,
  quando um cliente pergunta pelo prato que viu. O servidor recusa com 409 e a frase manda
  inativar; a tela nem oferece o botão fora do rascunho.

- ⚠️ **Campo ausente NÃO é campo nulo.** A tela manda o que mudou (`exclude_unset`); tratar o
  ausente como `None` apagaria o período de quem só mexeu na situação. Mas **limpar a data de
  propósito continua valendo** — é uma edição legítima ("passa a valer sem prazo") —, então
  as datas entram pelo que ESTÁ no dicionário, não pelo que é diferente de nulo.

- ⚠️ **O período se valida com o que FICA, não com o que veio.** Mandar só `publica_ate` numa
  edição precisa ser comparado com o `publica_de` já gravado; senão dá para inverter o
  período em duas gravações. A suíte cobra exatamente isso.

## Armadilhas já pagas

- ⚠️ **`sr-only` dentro de `overflow-x-auto` ESCAPA do clipping e rola a página.** O
  `<input type="file">` escondido de cada linha é `position: absolute`; sem ancestral
  posicionado, o containing block dele passa a ser o documento, e ele foi parar na coordenada
  que tinha dentro da tabela larga. Medido: **330px de rolagem lateral numa janela de 400** —
  e o `overflow-x-auto` estava correto o tempo todo (326 visíveis, 973 de conteúdo). A célula
  ganhou `relative`, e a bateria passou a medir se a página ROLA de fato
  (`window.scrollTo(9999,0)` e ler `scrollX`), não só o `scrollWidth`.
  🔑 **`scrollWidth` maior que a janela NÃO prova rolagem** — dentro de um scroller ele cresce
  sem que a página role. O teste honesto é tentar rolar.

- ⚠️ **A frase do nome repetido citava o nome DIGITADO, não o gravado.** O índice ignora a
  caixa (`lower(nome)`), então quem tentava "cardapio PERMANENTE" lia *"já existe um chamado
  cardapio PERMANENTE"* — e ia procurar esse nome na lista sem achar, porque lá está
  "Cardápio permanente". A frase agora traz o nome como está no banco e diz que a caixa não
  diferencia. Pego pela própria suíte, na primeira rodada.
  ⚠️ **Quem GARANTE é o índice único; quem EXPLICA é `_recusar_nome_repetido`.** A pergunta
  antes não substitui a restrição — é ela que não envelhece sob concorrência —, acrescenta a
  frase. É a mesma divisão que `mesas` pagou com um 500 e texto de Postgres na cara do
  usuário.

## O que vem a seguir

1. ~~A importação do PDF~~ — **feito**, migração 080.
2. A publicação no **site de reservas**: é o site que ainda não existe. ⚠️ É aqui que entra a
   regra que escolhe entre os vários ativos; ela não existe, e o cadastro não a inventa.
3. Eventualmente, **os itens do catálogo** item a item — se a casa quiser mais que o PDF.

⚠️ **Ao fechar qualquer uma delas, revise ESTA lista.** Lista de pendências envelhece pior
que decisão — a memória de Reservas passou uma semana dizendo que o que estava feito não
tinha começado.

## O produto ganhou foto e texto de vitrine (migração 083, 22/09/2026)

🔑 **Pedido do dono:** *"no cadastro de produtos, quando utilizando Reservas, criar uma nova
aba chamada Catálogo. Nesta aba teremos Foto e um campo para Informação Adicional."*

A regra mora em **Cadastros** — são colunas de `produtos` (`foto_url` e
`informacao_adicional`), e o detalhe está em
[`cadastros.md`](cadastros.md). O que interessa aqui é o destino:

⚠️ **Ainda NÃO há quem os mostre.** O catálogo de hoje é um PDF que a casa sobe inteiro; estes
dois campos são o começo do catálogo montado pelo sistema, produto a produto. Enquanto essa
vitrine não existir, eles são cadastro guardado — e a tela não promete o contrário.
🔑 **A porta é a mesma de tudo em Reservas**: a aba só aparece com `reservas_ligado`.

## A origem PRODUTOS: o cardápio montado aqui dentro (migração 084, 22/09/2026)

🔑 **Pedido do dono:** *"vamos adicionar a Origem Produtos. Quando for esta origem, ao listar
os catálogos, ao clicar sobre vai abrir uma nova página para configuração. Neste, podemos criar
Categorias (exemplo: Menu Principal) e suas SubCategorias (exemplo: Pra Dividir), cada item
terá o Nome, Descrição e uma foto. Após isto, podemos vincular os produtos disponíveis no PDV
para a subcategoria. Somente produtos ativos."*

🔑 **É a segunda origem que a 079 previu**, com estas palavras: *"no dia em que entrar a segunda
origem — o cardápio montado item a item aqui dentro — os catálogos antigos precisam continuar
sabendo de onde vieram"*. Por isso `origem` era coluna desde o primeiro dia, e nada precisou
ser reescrito. ⚠️ `PRODUTOS` **não substitui** `PDF`: são dois jeitos de publicar um cardápio,
e a casa escolhe por catálogo.

### O modelo, e as duas decisões que o definiram

- 🔑 **Subcategoria é OPCIONAL** (decisão do dono): categoria pode ter produto direto. Cardápio
  de verdade tem os dois casos — "Menu Principal" se divide em "Pra Dividir" e "Pratos", mas
  "Bebidas" costuma ser uma lista só. ⚠️ Obrigar a subcategoria faria a casa criar uma com o
  mesmo nome da categoria só para pendurar os itens, e o site mostraria o título duas vezes.
- 🔑 **O item sempre sabe a categoria; a subcategoria é que pode faltar.** `catalogo_itens` tem
  `id_categoria` obrigatório e `id_subcategoria` nulo — assim a consulta do cardápio é uma só
  nos dois casos.
- 🔑 **Quem garante que a subcategoria é DAQUELA categoria é o BANCO**, por uma chave composta
  (`FOREIGN KEY (id_subcategoria, id_categoria)`), não a rota. ⚠️ E com `id_subcategoria` nulo
  a chave não é cobrada (`MATCH SIMPLE`, o padrão) — que é exatamente o item solto.
- 🔑 **O mesmo produto PODE estar em mais de uma lista** (decisão do dono): uma porção serve a
  "Pra Dividir" e a "Menu Principal". O que se impede é a repetição DENTRO da mesma lista.
  ⚠️ **São dois índices únicos parciais, e a razão é `NULL`**: num índice comum, `(NULL, 42)`
  nunca colide com outro `(NULL, 42)` — o parcial separa o mundo com subcategoria do mundo sem.

### "Produtos disponíveis no PDV"

⚠️ **NÃO é só `integrado_pdv`** — é a mesma regra da aba Catálogo do produto (083), e pela
mesma razão: aquela marca é sobre ESCRITA, e "com `codigo_pdv` e desmarcado" é o produto que
veio de lá e a casa não quer que o Botané mexa. Ele é vendido no balcão todo dia.
⚠️ **E a recusa é na ROTA, não só na lista da tela.** A lista é conforto; quem garante que só
entra produto ativo e vendido no balcão é o servidor — regra 4 da casa.

### Armadilhas pagas

- ⚠️ **`/produtos-disponiveis` era engolida por `/{id_catalogo}`**, e o sintoma foi um 422
  dizendo que *"produtos-disponiveis" não é um número inteiro*. Rota de UM segmento só tem de
  ser declarada ANTES da que tem parâmetro — como `/opcoes` já fazia. 🔑 O mais instrutivo: o
  comentário que eu havia escrito ali dizia exatamente isso, e a linha seguinte o violava.
- ⚠️ **`<Link>` do Next não navega com `a.click()` por `evaluate`**: quem trata o clique é um
  listener do router, e o clique sintético não passa por ele. Sonda de navegação precisa de um
  clique de verdade, pelo ponteiro.
- ⚠️ **Componentes da casa têm nomes próprios de propriedade**, e chutar custa uma volta:
  `Etiqueta` usa `cor` (não `tom`), `CabecalhoTela` usa `explica` (não `descricao`) e `Vazio`
  recebe só `children`.

### O site mostra o cardápio (22/09/2026)

🔑 **Pedido do dono:** *"agora devemos apresentar o catálogo na tela. Usar como exemplo estes
dois prints."* Os prints vieram de outro cardápio online: o primeiro é a lista de categorias —
título, descrição e uma foto grande com "ACESSAR" por cima; o segundo é o miolo — uma tira
horizontal de subcategorias redondas e, abaixo, os itens com nome à esquerda, preço à direita
e descrição embaixo.

🔑 **Decisão do dono, perguntada antes de desenhar:** a cara é a do SITE — oliva e areia, como
o protótipo —, e os prints entram como **estrutura**. ⚠️ Eles são pretos; pular de uma capa
clara para uma tela preta faria o cliente achar que saiu do site. Se um dia a casa quiser o
escuro, o caminho é escurecer o site inteiro, não uma tela.

🔑 **Decisão do dono: o PREÇO aparece**, e sai de `produto_precos` pela mesma cascata do PDV —
o da loja primeiro, o da casa como segundo degrau. ⚠️ **Uma segunda regra de preço aqui faria
o site cobrar diferente do balcão.** ⚠️ **Produto sem preço sai SEM preço, não com zero**:
zero é um número, e número no cardápio é promessa. E o rodapé *"preços sujeitos a alteração"*
só aparece quando há preço na tela.

- 🔑 **`/publico/{loja}/catalogos` passou a devolver as DUAS origens**, com `origem` dizendo
  onde o site deve abrir: o PDF em outra aba, o de produtos dentro do site.
- ⚠️ **Capa sem conteúdo continua fora da lista, e cada origem tem o seu conteúdo**: o PDF é o
  arquivo; o de produtos são os ITENS VIVOS. Um cardápio publicado e vazio seria um cardápio
  que não abre.
- 🔑 **O `id` entra na resposta pública, e é exceção consciente à regra "nada de id interno"**:
  sem ele o site não tem como pedir o cardápio de volta. Não é segredo — é a chave de algo que
  a casa decidiu publicar, como o sufixo do PDF também é. ⚠️ O catálogo de PDF continua sem
  id, porque ali ele não serviria a nada.
- ⚠️ **Produto desativado SOME do site**, e continua aparecendo marcado na tela de
  configuração. São papéis diferentes da mesma informação: lá a casa precisa descobrir que
  publicou algo que saiu de linha; aqui o cliente não pode pedir o que não existe.
  ⚠️ E o catálogo que fica vazio por isso sai da lista sozinho.
- ⚠️ **Seção vazia não sai** — uma categoria sem item vivo viraria um título com nada embaixo.
- 🔑 **Uma consulta só, e a árvore é montada em memória.** Uma consulta por categoria
  transformaria um cardápio de dez seções em dezenas de idas ao banco — e este é o caminho que
  o público percorre.

🔑 **O nome de VITRINE existe desde a migração 085**, e foi o que resolveu o problema que esta
seção registrava: o cardápio mostrava "BATATA RÚSTICA" onde o impresso diz "Batata Rústica".
`produtos.nome_catalogo` é o nome como o cliente lê; nulo cai no nome do cadastro, que continua
em CAIXA ALTA porque lá dentro isso é certo. A consulta da vitrine resolve com
`coalesce(nullif(btrim(p.nome_catalogo), ''), p.nome)` — em branco é o mesmo que não ter.
⚠️ **A tela de configuração do cardápio mostra o nome de vitrine PRIMEIRO**, com o do cadastro
ao lado em cinza: ali se olha o cardápio, não o cadastro — mas quem veio procurar o produto
precisa reconhecê-lo. Ver `cadastros.md`.

⚠️ **Sem foto, a bolha da subcategoria fica VAZIA.** A primeira versão punha as duas primeiras
letras do nome ali, e o que aparecia era "Pr" e "Sa" soltos dentro de um círculo: parece
defeito, não desenho. O nome já está escrito logo abaixo.

## A ordem dos itens e o recolher das seções (22/09/2026)

🔑 **Pedido do dono:** *"ao cadastrar os produtos, permitir a ordenação deles, e os novos ir
adicionando no fim da lista. Permitir recolher a categoria e subcategoria para a tela não
ficar tão longa."*

### A ordem

- ⚠️ **Antes, todo item nascia com `ordem = 0`** e a lista caía na ordem alfabética do
  desempate — um cardápio não é lista telefônica. Agora cada novo entra com
  `max(ordem) + 10` **da lista dele**, e "a lista dele" é a da subcategoria, ou a dos soltos
  da categoria: são duas filas diferentes na tela.
- 🔑 **O passo é 10, não 1**, para sobrar espaço entre vizinhos no dia em que alguém quiser
  encaixar um no meio sem reescrever a lista inteira.
- 🔑 **Reordenar manda a lista INTEIRA renumerada**, não "sobe um". Mandar só o que se moveu
  deixaria o servidor adivinhando o resto, e dois cliques rápidos chegariam fora de ordem — a
  segunda gravação partiria de um estado que a primeira já mudou. ⚠️ E trocar só os dois
  vizinhos deixaria empates quando duas listas antigas tivessem a mesma ordem; empate na
  ordenação vira posição que depende do acaso da consulta.
- ⚠️ **Cada id é conferido contra a LOJA** antes de gravar: sem isso, um id de outra casa
  entraria na lista e seria reordenado junto.
- 🔑 **Subir e descer, não arrastar.** Arrastar é agradável no mouse e ruim no toque, e esta
  tela também se usa no celular — onde o arrasto disputa com a rolagem da página. ⚠️ O
  primeiro não sobe e o último não desce: botão que não faz nada ensina a duvidar dos outros.
- ⚠️ **`PUT /catalogos/itens/ordem` é declarada ANTES de `/itens/{id_item}`.** `ordem` é um
  segmento só, e o FastAPI casa rotas na ordem — embaixo, ela seria lida como um id e
  responderia 422 dizendo que "ordem" não é um número. É o mesmo tropeço de
  `/produtos-disponiveis`, na mesma sessão, duas horas antes.

### O recolher

- ⚠️ **As seções nascem ABERTAS.** Um cardápio que abre todo fechado esconde o que a pessoa
  veio conferir e cobra um clique por seção antes de qualquer trabalho.
- ⚠️ **Fechada, o miolo não é DESENHADO** — e não apenas escondido por CSS. Uma categoria com
  trinta produtos continuaria montando trinta linhas invisíveis, e a tela que se queria
  encurtar seguiria pesada.
- 🔑 **A contagem fica no botão** (`▸ abrir (12)`). Seção fechada sem número é uma caixa que
  não diz o que guarda, e a pessoa abre uma por uma só para achar o que procura.
- 🔑 **Recolher vale para quem só LÊ também**: o botão está fora do `podeEditar`, porque a
  tela longa incomoda igual.
- ⚠️ **O `Cartao` ganhou uma correção por causa disto**: ele desenhava o miolo com `p-5` mesmo
  recebendo `null`, e sobrava uma faixa vazia de ~50px por cartão recolhido — meia tela de
  nada com dez categorias. Agora, sem conteúdo, não há caixa. Vale para a casa inteira.

## O catálogo que exige cadastro (migração 086, 24/09/2026)

🔑 **Pedido do dono:** *"adicionar a validação do cliente ao acessar o catálogo, colocar no
cadastro do catálogo se exige cadastro."* Caixa `exige_cadastro` no formulário do catálogo,
catálogo a catálogo; nasce DESLIGADA (o que já estava no ar continua abrindo igual).
- ⚠️ **Quem garante é o SERVIDOR.** Na lista pública, o que exige cadastro vem com `id` e
  SEM `arquivo_url`; o `GET /publico/{u}/catalogos/{id}` (produtos) responde **403**. O
  conteúdo só sai por `POST /publico/{u}/catalogos/{id}/abrir` com telefone + primeiro nome
  de um cadastro existente (403 "faça seu cadastro" se não há; 409 se o nome não confere).
  Esconder só o botão seria validação de enfeite: o link estaria na resposta.
- ⚠️ **Limite conhecido:** o endereço do PDF em si (`/arquivos/...`) continua público — quem
  já o tem abre sem cadastro. A validação é de ACESSO pelo site, não sigilo do arquivo.
- ⚠️ **O PDF vira LINK, não `window.open`**: abrir aba depois de esperar o servidor é popup
  para o celular. Depois de identificada, `destravarCatalogos()` troca os botões dos PDFs
  fechados por `<a>` de verdade; no primeiro, a tela de identificação mostra "Abrir …".
- A identificação é a MESMA da reserva (ver `reservas.md`): quem se identificou num catálogo
  não repete o telefone para reservar, e vice-versa — só nesta visita (sem localStorage).
- Cobertura: `4c` do `smoke_publico.py`.

## Visível nas lojas (migração 087, 24/09/2026)

🔑 **Pedido do dono:** *"no cadastro do catálogo, podemos ter um Visível nas Lojas, aí o usuário
marca onde ficaria visível."* Tabela `catalogo_lojas (id_catalogo, id_unidade)`.
- `catalogos.id_unidade` continua a DONA (quem edita, pela loja do seletor do sistema);
  `catalogo_lojas` diz onde o CLIENTE vê. As consultas públicas filtram por `EXISTS` nela.
- ⚠️ A 087 semeia cada catálogo existente com a PRÓPRIA loja — sem isso os cardápios no ar
  sumiriam no deploy. Catálogo novo sem `lojas` nasce só na dona.
- ⚠️ Pelo menos uma loja, e só loja ativa (422). As caixas só aparecem na tela com mais de uma
  loja com Reservas ligado (`/catalogos/opcoes` devolve `lojas`).
- O preço do cardápio é o da loja em que o cliente ESTÁ (já era `produto_precos` por loja).

## Tradução para inglês e alemão (migração 103, 29/09/2026)

🔑 **Decisão do dono:** *"Claude Haiku, categorias também e o site nos três idiomas."* O estudo
(24/09) está em `reservas.md`. Código: `services/traducao.py`, `routers/traducao.py`,
`web/components/traducoes.tsx`, `catalogos/[id]/traducoes-do-catalogo.tsx`, e o site
(`site/index.html`, seção de idiomas).

- Colunas `_en`/`_de` em `produtos` (`nome_catalogo`, `informacao_adicional`),
  `catalogo_categorias`, `catalogo_subcategorias` (nome e descrição) e `catalogos` (nome).
  ⚠️ O texto de origem do produto é o **nome de vitrine** (`nome_catalogo`, e o `nome` se ele
  estiver vazio), não o nome do cadastro.
- 🔑 **Corrigido à mão não é sobrescrito**: `traducao_editada text[]` guarda as COLUNAS editadas
  na tela, e a tradução automática as pula. "Gerar de novo" (`forcar`) limpa a marca.
- 🔑 **Só retraduz quando o português muda**: `traducao_origem` é o sha256 do texto de origem.
  Salvar sem mexer no texto não chama a Anthropic — e a tela mostra "o português mudou" quando
  o hash não bate.
- 🔑 **Traduz ao SALVAR, e salvar nunca quebra por causa disso**: `traducao.tentar` roda num
  SAVEPOINT e engole o erro (sem chave, API fora, JSON ruim). Ganchos em `routers/catalogos.py`
  (catálogo, categoria, subcategoria, item vinculado) e no fim de `produtos.atualizar` (só se o
  produto está em algum catálogo e o texto mudou).
- 🔑 **A chave da Anthropic é cadastrada no SISTEMA**, em Integrações ▸ Tradução (pedido do dono,
  29/09/2026: *"trocar a informação da chave no servidor por ela ser cadastrada no sistema — aí o
  cliente pode configurar a sua chave"*). Mora em `integracoes` (serviço `ANTHROPIC`, id_unidade
  nulo, o índice parcial da 012), cifrada por `segredos` e **só mascarada** na API — o mesmo
  molde do SMTP. Permissão `admin.integracoes`. Em branco mantém a guardada; "Testar a chave"
  faz uma chamada mínima e traduz o erro da Anthropic (401 chave, 400 sem crédito, 429 limite).
  ⚠️ **Não existe mais `ANTHROPIC_API_KEY` no ambiente** — nem no `.do/app.yaml`: a primeira
  versão (mesmo dia) a lia do servidor, e quem paga a conta não tem acesso ao painel.
- Sem chave (ou com "traduzir ao salvar" desmarcado) a tradução fica desligada — e a tela diz,
  com o link para Integrações. Modelo configurável na mesma tela (padrão
  `claude-haiku-4-5-20251001`). Os campos seguem editáveis à mão.
- ⚠️ `smoke_traducao` guarda a linha `ANTHROPIC` da casa no início e a REPÕE no fim (roda sem
  chave e cadastra uma falsa) — a mesma lição do `preservar_credenciais` do Omie.
- O cartão "Inglês e alemão" do catálogo conta o que falta (sem tradução OU com o português
  mudado) e traduz tudo em lotes de 25 — é o caminho para o cardápio que já existia.
- Público: `?idioma=en|de` em `/catalogos`, `/catalogos/{id}` e `/catalogos/{id}/abrir`
  (outro idioma é 422). 🔑 **Faltou tradução → português**, nunca vazio (`traducao.escolher`).
- ⚠️ PDFs de catálogo ficam fora: não dá para traduzir o arquivo.
- Permissões: vê quem vê catálogo ou produtos; corrige quem edita catálogo ou produtos.
- Cobertura: `smoke_traducao.py` (25) — ⚠️ com o Claude TROCADO por resposta fixa; nenhuma
  chamada de verdade à Anthropic sai da bateria. Fase 13 da bateria do navegador (o cartão e a
  janela de uma seção) e `web/scripts/verificar-idioma-site.mjs` (o site em PT/EN/DE, 20).

## Pedidos pelo catálogo (migração 101, 28/09/2026)

🔑 **Pedido do dono:** *"o cliente poder realizar pedidos diretamente na tela de catálogo,
criando esta opção ao criar um catálogo do tipo Produtos; um carrinho de compras para enviar
pedidos ao sistema; uma tela com pedidos, um painel para acompanhar e aviso na tela inicial. O
pagamento não será pelo sistema."* Estudo e decisões em [`docs/pedidos-estudo.md`](../pedidos-estudo.md)
(seção 0). Código: `services/pedidos.py`, `routers/pedidos.py`, rotas no fim de
`routers/publico.py`, telas `web/app/(app)/pedidos/`, cartão `catalogos/[id]/pedidos.tsx`,
`pedidos-do-dia.tsx` no Início, e o carrinho em `site/index.html`.

- ⚠️ **O pedido NÃO vira venda** (decisão do dono): a casa lança no PDV e a venda chega pela
  busca de sempre. Aqui só a MARCA "lançado no PDV" (`lancado_pdv_em`, `cupom_pdv`) — não é
  situação. Com o cupom, `_ligar_venda` acha a venda importada (`vendas.documento`) na leitura:
  ligação para conferir, nada muda em estoque, receita ou CMV.
- 🔑 **Configuração do CATÁLOGO** (`catalogo_pedidos_config`), só origem PRODUTOS (PDF é 400).
  Retirada/entrega, taxa, mínimo, antecedência mínima (minutos) e máxima (dias), formas de
  pagamento e o texto sobre o pagamento. Permissão: a do catálogo (`catalogos.editar`).
- 🔑 **Preço do SERVIDOR.** O cardápio público passou a mandar `id` do ITEM (`catalogo_itens.id`)
  e `pedidos` (nulo quando não aceita). O site manda item + quantidade; o valor sai da mesma
  cascata do cardápio (loja → casa). Nome e preço congelados em `pedido_itens`.
- ⚠️ **Idempotência pelo banco** (regra 8): `ux_pedido_chave (id_unidade, chave)`; o site gera a
  chave e a TROCA a cada mudança no carrinho — senão o segundo pedido idêntico devolveria o
  primeiro. Número do balcão por loja (`ux_pedido_numero`), com `pg_advisory_xact_lock`.
- 🔑 **Quando**: nulo = agora + antecedência mínima, e a casa tem de estar aberta; encomenda
  confere antecedência, dias à frente, bloqueio e a janela do dia (`reservas_agenda`, com a
  exceção do dia). ⚠️ Hora sem fuso vinda do site é a hora da CASA (`FUSO_DA_CASA`).
- 🔑 **Confirmar com troca**: item que já estava mantém o preço do envio; item NOVO entra pelo
  preço vigente do catálogo. `pedido_historico.detalhe.pedido_pelo_cliente` guarda o original;
  `alterado` marca o pedido. WhatsApp `PEDIDO_CONFIRMADO` (o único, por decisão do dono).
- Situações NOVO → CONFIRMADO → ENTREGUE, + RECUSADO e CANCELADO (motivo que o cliente vê). O
  cliente cancela só enquanto NOVO. Pago é registro (Pix, cartão, dinheiro, outro).
- Permissões `pedidos.ver` e `pedidos.operar` (Admin, Gerente, Salão), escondidas do catálogo de
  papéis com o Portal desligado (`routers/papeis.py`).
- Alertas `pedidos.parados` (NOVO há 15 min, crítico) e `pedidos.sem_pdv`.
- ⚠️ **`preservar_reserva` (tests/comum.py) passou a levar os pedidos**: eles apontam para
  `reserva_clientes` com `ON DELETE SET NULL`, e apagar/repor o cliente deixaria todo pedido real
  sem dono. E a reposição passou a embrulhar `jsonb` em `Json` (o histórico).
  🔴 **E esqueceu o import do `Json` em `preservar_reserva`** (estava só em
  `preservar_credenciais`): de 28 a 29/09/2026 a reposição estourou em TODA rodada, a
  transação desfazia a tentativa e a loja 1 LOCAL ficou com o cenário do último teste — a
  configuração de reserva de antes de 28/09 se perdeu na base de casa (o ar não roda suíte).
  O aviso em maiúsculas saía, mas o `rodar_tudo` só mostra o resumo de cada suíte.
- ⚠️ Achado junto: `catalogo_itens` faltava em `limpar_dados.OPERACAO` desde a 084 — a guarda
  recusava a limpeza inteira. ⚠️ **`limpar_dados.py` não tem `--help`**: rodá-lo com qualquer
  argumento mostra a prévia e ESPERA confirmação — não usar para "ver a ajuda".
- Cobertura: `smoke_pedidos.py` (48), fase 13 da bateria do navegador, e
  `web/scripts/verificar-pedido-site.mjs` (o carrinho no site, 10).

## Cardápio Vivo, fase 1 (migração 113, 14/10/2026)

🔑 **Pedido do dono (14/10/2026):** o cardápio da mesa como feed de rede social — um prato por
tela, com vídeo ou foto — e, para a gestão, a atenção de cada prato cruzada com venda e margem.
Estudo, decisões (15 perguntas respondidas) e roteiro por fase em
[`docs/cardapio-vivo-estudo.md`](../cardapio-vivo-estudo.md). Fase 1 = acesso por mesa, feed,
modo VITRINE, cadastro e eventos. Fase 2 (PEDIDO, chamados, fidelidade, painel Atenção × Vendas)
e fase 3 (A/B) não começaram.

- Código: `services/cardapio_vivo.py`, `routers/cardapio_vivo.py` (dois routers: `router` de
  dentro e `publico`), `routers/produto_cardapio.py`, `models/cardapio_vivo.py`; web em
  `app/c/[loja]/[[...mesa]]` (público), `app/c/previa/[catalogo]`, `components/cardapio-vivo/`,
  `app/(app)/cardapio-vivo/`, `catalogos/[id]/cardapio-vivo.tsx`, `produtos/[id]/cardapio-vivo.tsx`.
- 🔑 **Nada de cadastro novo de prato**: o feed é o catálogo PRODUTOS que `cardapio_config.id_catalogo`
  aponta (um por loja). Vídeo e restrições no PRODUTO; destaque e esgotado no ITEM; dia/horário na SEÇÃO.
- ⚠️ **Esgotado revoga a decisão 6 de 28/09** ("não haverá pausa"). O item fica no feed, marcado,
  sem botão; `esconder_esgotado` da loja o tira. (A resposta do dono veio cortada — confirmar.)
- 🔑 **A URL da mesa leva TOKEN** (`mesas.token`, DEFAULT na coluna + NOT NULL). ⚠️ O primeiro
  rascunho só fazia UPDATE nas mesas existentes — a mesa criada depois nascia sem QR; a suíte pegou.
- ⚠️ **O modo PEDIDO é recusado (409) na fase 1**, na config e nas exceções. A resolução
  loja ← salão ← mesa e a queda para VITRINE fora do horário já existem e são testadas.
- 🔑 **Eventos por `sendBeacon` com `text/plain`** (o único tipo sem preflight entre origens —
  em casa web e API são portas diferentes). A rota lê o JSON à mão e valida no Pydantic. Freios:
  lote ≤ 64 KB/60 eventos, 3.000 por sessão, 240 lotes/10 min por origem (em memória). O produto é
  descoberto pelo item, só dentro do catálogo apontado. Hora = a do servidor menos `idade_ms`.
- 🔑 **Retenção (LGPD)**: `cardapio_vivo.laco` uma vez por dia depois das 3h agrega o dia anterior
  em `cardapio_agregados_dia` e apaga o bruto além de `retencao_meses` — agregando ANTES, por loja
  (refazer o dia inteiro depois de apagar o bruto de uma loja zeraria o resumo dela).
- 🔑 **Mídia**: vídeo convertido no upload por `imageio-ffmpeg` (binário dentro da wheel) para MP4
  H.264, 720p no lado MENOR, mudo, ≤ 15 s, ~2 MB, `+faststart`; capa WebP do primeiro quadro.
  `/arquivos/{nome}?w=` devolve a imagem redimensionada em WebP (larguras fechadas, cache em
  memória). ⚠️ **Vídeo exige `Range`** — o Safari do iPhone não toca sem 206.
  ⚠️ **Ainda no banco**, não no Spaces: o dono aprovou Spaces + CDN, mas o bucket e as credenciais
  não existem. A troca é só em `arquivos.py`.
- ⚠️ `/c/...` pula o service worker e a `MarcaNaAba` (é o celular do cliente, não da casa).
- ⚠️ O aviso de cookies ficava no rodapé e tapava nome e preço do primeiro prato — foi para
  baixo da barra de categorias. "Não medir" desliga a medição neste aparelho.
- ⚠️ Puppeteer não mostra o corpo de um `sendBeacon`: a verificação embrulha
  `navigator.sendBeacon` na página para guardar cópia dos lotes.
- Cobertura: `smoke_cardapio_vivo.py` e `web/scripts/verificar-cardapio-vivo.mjs`.
- 🔑 **Complemento do dono no mesmo dia** (migração 114, ver seção 0b do estudo): Hub (avaliação
  no Google e Wi-Fi, dados no cadastro da LOJA, botões ligados no Cardápio Vivo), favoritos no
  aparelho (por loja), nove eventos novos, "sessão engajada" e "atenção estimada" com teto de
  60 s, e `cardapio_resumo_dia` (sessões abertas/engajadas e cliques do Hub). Objetivo de negócio
  e margem do item, e o painel, ficaram para a fase 2. Cobertura: 93 na API, 29 no navegador.
  ⚠️ O botão "♥" do topo tem `aria-label="Meus favoritos"`, igual ao diálogo — a verificação
  procura `[role="dialog"]`.
- 🔑 **O site de reservas abre o FEED** (pedido do dono, 14/10/2026: *"quando coloco um cardápio
  como cardápio vivo, ao acessar pelo site reservas, ficaríamos naquela mesma estrutura"*). Revoga
  a decisão 4 do estudo ("o site continua como está e ganha o link"). `GET /publico/{loja}/catalogos`
  traz `cardapio_vivo` (o catálogo que `cardapio_config` aponta naquela loja), e o `abrirCatalogo` do
  site leva a `/c/{loja}` em vez da tela de seções. Clique, QR da mesa (`&catalogo=`) e F5 passam
  todos por ali. O idioma vai junto (`?idioma=en`), e o feed o prefere ao do navegador.
  ⚠️ **Antes de ir, o site volta a `#inicio` e esquece o catálogo aberto**: sem isso, o "voltar" do
  celular caía em `#cardapio`, que reabria o feed, e a pessoa ficava presa sem voltar ao site.
  ⚠️ O endereço do sistema web (`WEB`) segue a mesma regra da `API` no site: decidido pelo hospedeiro.
- 🔑 **No computador, o feed é uma COLUNA de celular** (até 480 px, laterais escuras; pedido do dono,
  mesmo dia: *"não ficou bem visualmente na web, no mobile sim"*). Esticado no monitor, a foto
  vertical virava recorte ampliado e os controles iam para cantos opostos.
  ⚠️ **O `transform` no `<main>` não é enfeite**: ele faz as camadas `fixed inset-0` (detalhe,
  favoritos, seleção) ficarem presas DENTRO da coluna, sem mexer em cada uma. A foto passou a pedir
  `sizes="(min-width: 768px) 480px, 100vw"` — pela largura do monitor, baixava o dobro sem ganho.

- **Falta na fase 1**: tela das exceções por salão/mesa (a API existe; só fazem sentido com o
  PEDIDO), Spaces, e medir o Lighthouse ≥ 85 num `next build`.

## Cardápio Vivo, fase 2 (migração 115, 15/10/2026)

Detalhe no estudo, seção 8. O que pegou no caminho:
- ⚠️ **CHECK sobre coluna com `ON DELETE SET NULL` trava a exclusão do pai.** A primeira
  versão exigia `id_mesa` no modo MESA; apagar a mesa zeraria o id e estouraria a CHECK. Virou
  `mesa_nome` congelado.
- ⚠️ **`preservar_reserva` embrulhava em `Json` só `dict`**; os adicionais são LISTA em jsonb, e
  lista também é o que volta de `text[]` (`mesas.caracteristicas`). Agora decide pelo TIPO da
  coluna (`information_schema`), não pelo valor.
- ⚠️ Na verificação do navegador, "Adicionar ao pedido" existe no prato E no detalhe: clique
  sem escopo pega o de trás do diálogo.
- ⚠️ `Textos` do feed era literal (`as const`); o modo PEDIDO troca rótulos e o tipo foi
  alargado para `string`.
- Pedido da mesa vai à coluna Mesas e, confirmado, à "lançar no PDV" como os do site. O
  pedido de teste da verificação FICA (pedido não se apaga pela rota).

## Cardápio Vivo, fase 3 (migração 116, 15/10/2026)

Detalhe no estudo, seção 9 (testes A/B de mídia e ordem, sugestões de destaque).
- ⚠️ **`% 2` dentro de SQL com parâmetros quebra o psycopg2** ("argument formats can't be
  mixed"): a conta da variante usa `mod(…, 2)`. Pego pela suíte no primeiro POST.
- ⚠️ `URLSearchParams.size` não existe no Safari antigo — o idioma sumiria do endereço do
  feed. Usa-se `toString()`.
- 🔑 A verificação no navegador descobre o braço de uma sessão pedindo o feed com `?sessao=`,
  nunca recalculando o hash fora do banco.
- 🔑 **O teste A/B é da LOJA, não do catálogo** (15/10/2026, varredura da segunda loja).
  `cardapio_testes.variantes` filtrava só por `id_catalogo`. Mas um catálogo pode estar visível
  em duas lojas (`catalogo_lojas`) e ser o Cardápio Vivo das duas: o teste aberto na matriz
  mudava o feed da filial, onde ninguém abriu teste, e o resultado (que conta só os eventos
  da loja do teste) nunca via essa exposição. Agora recebe `id_unidade`. Coberto pela seção 2
  do `smoke_cardapio_testes.py`. ⚠️ **Aplicar o vencedor continua valendo para as duas**: ele
  muda o CATÁLOGO (a mídia preferida, a ordem), e o catálogo é um só. Isso é o modelo, não
  vazamento.

## A reforma do cadastro (15/10/2026)

🔑 **Pedido do dono:** *"o cadastro de catálogos não está muito intuitivo e fácil de realizar.
Analise uma melhor estrutura."* Análise apresentada e aprovada (*"pode seguir nesta sequência"*),
com as três recomendações aceitas: o que é do produto continua no produto, setas (não arrastar)
mais um "mover para", e o Cardápio Vivo escolhido também na aba Publicação.
O diagnóstico: cada fase pendurou o seu cartão onde coube, e a tela seguia a ordem em que as
coisas foram construídas, não a ordem em que se monta um cardápio.

- **Lista em cartões** (`catalogos/page.tsx`): um selo só (no ar / ativo, fora do período /
  rascunho / inativo), "Cardápio Vivo", pratos e o que falta (`resumo` e `cardapio_vivo` na
  resposta da lista, `services/catalogos._CAMPOS`), e **Abrir**. Nada se edita na lista.
- **Novo catálogo em dois passos** (`novo-catalogo.tsx`): o TIPO (montado com produtos primeiro,
  rótulos em `APRESENTA_ORIGEM`, valores do servidor), depois só o nome. Nasce RASCUNHO e ABRE.
- **Todo catálogo tem página**, inclusive o de PDF: abas Arquivo e Publicação. O de produtos:
  Cardápio (abre aqui), Publicação, Pedidos, Idiomas. A aba vai na URL (`?aba=`).
- **Aba Cardápio**: seções à esquerda (faixa que rola de lado no celular), a seção escolhida à
  direita. Sem escolha, abre a primeira seção que TEM pratos. Linha do prato enxuta (foto, nome
  de vitrine, preço, ★, esgotado, o que falta, ↑↓); o resto na **gaveta do prato**
  (`Gaveta` em `components/ui`). ⚠️ Foto, nome de vitrine, descrição, vídeo e restrições na
  gaveta gravam no PRODUTO, com a permissão `cadastros.produtos`, e a gaveta diz que valem em
  todo cardápio. Adicionais continuam só no cadastro do produto.
- **"+ pratos" com seleção múltipla**; o que já está na lista aparece travado ("já está aqui").
  Uma chamada de vincular por prato: é ela que confere ativo/PDV/repetido.
- **Seção**: foto, horário do Cardápio Vivo, traduções e excluir na janela dela. O campo numérico
  de ordem saiu: setas, que regravam a ordem de todas as irmãs (`reordenarSecoes`).
- **"O que falta"**: sem foto (e sem vídeo), sem descrição, sem preço ou inativo, de todas as
  seções numa lista — conserta-se e o prato sai dela.
- **Mover de seção**: `PUT /catalogos/itens/{id}/lugar`. Mover NÃO é tirar e pôr: o item leva
  destaque, esgotado, objetivo e margem e entra no fim da lista nova. Só dentro do mesmo catálogo;
  repetido no destino é 409 com frase.
- O conteúdo do catálogo traz `preco` (loja → casa, a mesma cascata do site e do feed).
- ⚠️ **`usePilhaDeJanelas` registra a janela UMA vez** (o `aoFechar` vai num ref). Com a
  dependência no callback, cada render tirava e repunha a janela na pilha, e uma gaveta com uma
  confirmação dentro voltava ao TOPO: o Esc fecharia a gaveta, não a pergunta.
- Cobertura: `smoke_catalogo_produtos.py` (preço, resumo, mover) e as fases 11 e 13 da bateria do
  navegador (criação em dois passos, PDF, publicar, cartões, abas, gaveta, lote, o que falta, mover).

## Vários Cardápios Vivos por loja (migração 117, 15/10/2026)

🔑 **Pedido do dono:** *"hoje podemos ter somente 1 cardápio vivo, poderíamos ter mais de um.
Exemplo: no Botané vai ter um que é o da cafeteria, e ela pode configurar outro que é destinado
ao Catering."* É a parte (a) de três; (b) traz o site para dentro do Next com um layout só e
(c) põe tudo em `reservas.botanedeliecafe.com.br`.

Decisões do dono (as recomendações aceitas):
- 🔑 **Um PRINCIPAL por loja**, que o QR da mesa abre; os outros, só pelo link
  (`/c/{loja}?cardapio={slug}`). O primeiro Cardápio Vivo da loja nasce principal; marcar outro
  desmarca o anterior (índice único parcial). Tirar o principal deixa a mesa sem cardápio — a
  frase avisa.
- 🔑 **A aparência é da CASA**, uma só para o site inteiro: `cardapio_config` ficou com cores,
  fonte, logo, Hub, esconder esgotado e retenção. Cada Cardápio Vivo (`cardapio_vivos`, chave
  `(id_unidade, id_catalogo)`) tem o nome no link, o principal e o comportamento: modo,
  confirmação, horário do pedido e garçom.
- **O catering pede como ENCOMENDA**, reusando a configuração de pedidos pelo site do catálogo.
  ⚠️ Ainda não: sem mesa o feed é sempre VITRINE. O carrinho de encomenda entra no feed na (b),
  junto com o site.

O que pegou:
- ⚠️ **`cardapio_config.id_catalogo` NÃO é zerado pela 117**, e as colunas de comportamento ficam
  sem uso: o contêiner antigo convive um ou dois minutos com o novo no deploy e ainda as lê —
  zerar faria a mesa responder 404 nesse minuto. Nada desta versão em diante as lê ou grava.
- `config()` devolve `id_catalogo` CALCULADO (o do principal): o painel de atenção, os testes A/B
  e o pedido da mesa continuam olhando o cardápio da mesa, como antes.
- O feed responde `vivo` (catálogo, slug, principal) e o lote de eventos manda `catalogo`; o
  servidor confere os itens contra o catálogo DESTE Cardápio Vivo. A seleção guardada no aparelho
  é por cardápio (`cardapio-{slug}`): a do catering não aparece na da mesa.
- O site manda `?cardapio=` quando o Cardápio Vivo não é o principal (`vivo` na lista pública).
- Uma janela só para configurar (`components/janela-cardapio-vivo.tsx`), usada pela tela do
  Cardápio Vivo (cartão "Os Cardápios Vivos") e pela aba Publicação do catálogo.
- Testes: `tests/comum.py` ganhou `preservar_cardapio_vivo` (as DUAS tabelas) e `gravar_cardapio`
  (o formato de antes, repartido nas duas rotas); as verificações do navegador usam
  `scripts/cardapio-vivo-comum.mjs`. Cobertura nova: seção 11d do `smoke_cardapio_vivo.py` e a fase
  13 do `verificar.mjs`.

## Um endereço e um layout só: o site dentro do app do sistema (15/10/2026)

🔑 **Pedido do dono:** *"mesmo sendo o mesmo sistema, o site de reserva e cardápio ficou
parecendo dois sistemas separados. Gostaria que tudo estivesse com o mesmo layout, e na mesma
URL."* Parte (b) de três (ver a seção da 117).
- 🔑 **O site NÃO foi reescrito em React** (escolha aprovada pelo dono): as 2.900 linhas guardam
  fluxos que os clientes usam (reserva, fidelidade, carrinho). 🔑 **`site/index.html` é a FONTE**
  — o dono confirmou que é a pasta publicada em `reservas.*` — e `web/public/portal/index.html` é
  uma CÓPIA idêntica que o app do sistema serve em `/portal` (o feed volta para lá e leva a
  encomenda pelo `sessionStorage`, que é por domínio). `smoke_site_sincronizado.py` recusa as
  duas diferentes. A API continua `sistema.../api` nos dois lugares (com CORS no `reservas`).
  ⚠️ A primeira versão desta mudança tinha posto a fonte na cópia e a API em `/api` relativa —
  desfeito quando o dono lembrou que o `reservas` no ar é a pasta `site/`.
- `web/proxy.ts` (o "middleware" do Next 16): em `reservas.*`, `/` abre o site, `/c/` passa e o
  resto redireciona a `/`; em qualquer domínio, `/portal` abre o site. ⚠️ O redirecionamento
  monta o destino pelo `Host` pedido — `request.url` é o endereço interno atrás do roteador.
- 🔑 **A aparência é da CASA e vale para os dois**: `/publico/{loja}/casa` traz `marca` (cores,
  fonte, logo — a mesma do feed), e o site aplica (`aplicarMarca`). A cor de fundo só vale no
  tema claro.
- ⚠️ **A fonte "a do site" era a Fraunces**, e a tela do Cardápio Vivo chamava a Newsreader
  assim. A 118 põe FRAUNCES como padrão e converte quem estava em NEWSREADER (que tinha
  escolhido "a do site"). ⚠️ O `db_updater` roda de novo a migração cujo checksum muda — a 118
  não se edita depois de promovida.
- A tela de entrada do feed (Hub) ganhou a cara da página inicial do site (capa, medalhão,
  botões) e o botão "Reservas, fidelidade e contato"; a marca no topo do feed volta ao site
  (`enderecoDoSite()`: `/` em `reservas.*`, `/portal` nos outros).
- As verificações do site (`verificar-pedido-site`, `verificar-idioma-site`) passaram a testar
  `http://127.0.0.1:3100/portal` — o servidor da porta 3200 não é mais preciso.
- 🔑 **A encomenda do catering**: sem mesa, num catálogo que aceita pedido pelo site, o feed
  responde `encomenda` e a "Minha seleção" ganha "Fazer encomenda". A seleção é gravada no
  carrinho do SITE (`sessionStorage["botane.carrinho"]` — a mesma aba, porque é o mesmo
  endereço) e o site abre em `/portal?loja=&encomenda={catálogo}#carrinho`. O site carrega o
  cardápio SEM mandar de volta ao feed (`abrirCatalogo(c, { semFeed })`), e o "‹ cardápio" do
  carrinho devolve ao feed (`aberto.doFeed`). ⚠️ O pedido do site não tem adicionais: as escolhas
  vão na observação do item, e a casa confere o preço delas ao confirmar. Na mesa, o pedido
  continua o da mesa. Cobertura: `web/scripts/verificar-encomenda-feed.mjs` (6).
- ✅ (c) feita em 16/10/2026: a regra de ingress de `reservas.*` no app `botane` passou do
  componente estático para o `web` (sem DNS — ver `docs/deploy.md`). Na 1.1.100 o botão do
  cardápio no site deixou de ir a `sistema...`: `WEB = location.origin` (só a porta 3200 de casa
  vai à 3100). ⚠️ Desfazer a virada exige desfazer isto — o estático não tem `/c/`.

### O feed com a cara do site (16/10/2026)

🔑 **Pedido do dono, já no ar em `reservas`:** *"quando entro na primeira página está com uma
formatação e quando vou para o cardápio vivo é outra… até a logo no título da página está
mudando. Vamos manter como se estivesse tudo no mesmo ambiente."*
- **A aba**: `/c/{loja}` gera título e ícone no SERVIDOR (`generateMetadata`, lendo
  `/publico/{loja}/casa` com cache de 1 min): o nome da casa e a logo da marca — o que o site
  põe na aba dele. Era "Cardápio" com o ícone do sistema. `theme-color` = cor da casa (era preto).
  ⚠️ O `icons` da página vence o `app/icon.svg` da raiz (conferido no HTML servido).
- **As letras**: Karla no corpo e DM Mono no preço (`.cv-corpo`, `.cv-mono` em `globals.css`),
  as do site; o feed herdava a Inter do sistema. A serifa continua a da casa (`--cv-serif`).
- **As cores**: o topo é um degradê da cor da casa (era véu preto), a categoria ativa é a pílula
  clara com a letra na cor da casa, o fundo enquanto carrega é o areia (era cinza-escuro), o
  prato sem foto usa a capa do site, e o véu sob o texto puxa a cor da casa — mas continua
  ESCURO, porque é ele que deixa o nome legível sobre qualquer foto.
- **No computador**: a coluna do feed é a FOLHA do site — 440 px, cantos de 18 px, a mesma sombra,
  sobre o areia. Os pratos passaram de `h-[100dvh]` para `h-full` da coluna, que no computador
  é a tela menos 48 px.
- ⚠️ Com logo, o topo do feed mostra SÓ a logo (e, na mesa, "Mesa X" e o salão): o nome da casa,
  e depois o do cardápio, saíam cortados ("Botan…", "Cardá…") entre o medalhão e os botões a
  400 px. A aba já diz o nome da casa. Sem logo, volta o nome por extenso.
- Cobertura: `verificar-cardapio-vivo.mjs` confere título, ícone e letra (34).

### Só consulta: a vitrine sem a "minha seleção" (migração 119, 16/10/2026)

🔑 **Pedido do dono:** *"no modo da mesa, ter uma opção vitrine só consulta, sem minha seleção."*
- `cardapio_vivos.selecao` (padrão `true`). Na tela, o "Modo na mesa" tem TRÊS escolhas — Só
  consulta, Vitrine (com "minha seleção") e Pedido —, gravadas em duas colunas: só consulta é
  `modo = VITRINE` + `selecao = false`.
- ⚠️ **Chave, não terceiro `modo`**: o modo continua VITRINE para os eventos, os testes A/B e as
  exceções por mesa/salão (113), que não precisaram mudar. No PEDIDO a seleção É o carrinho e o
  feed responde `selecao: true` sempre — inclusive fora do horário, quando o pedido cai para vitrine.
- O feed sem seleção: some a estrela do topo, o botão "Adicionar" de cada prato e o "adicionar"
  da janela do prato (que mostra o preço no lugar). Favoritos ficam — são sinal de interesse.
- Vale também pelo link (sem mesa): o Cardápio Vivo só consulta não oferece encomenda.
- Cobertura: `smoke_cardapio_vivo.py` 11d2 e `verificar-cardapio-vivo.mjs` 5c.

### O telefone de exemplo (16/10/2026)
⚠️ O exemplo nos campos de telefone era `(47) 99910-5033` — um número que pode existir. Pedido do
dono: tudo com 9. Virou `(99) 99999-9999` no site, no cadastro da loja e no WhatsApp.

## Cartões de conteúdo no feed (migração 120, 16/10/2026)

🔑 **Pedido do dono:** *"quando estamos em formato de feed, gostaria de colocar algo entre os pratos
que vai além de pratos — um cardápio de massas, e antes postar um vídeo, texto ou foto com uma
introdução, bem como seções entre os pratos"*. Proposta aprovada com três respostas: abertura de
seção **automática**, vídeo **subido no sistema**, cartões **só no feed** (site e PDF sem mudança).
- `catalogo_cartoes`: `id_categoria` nulo = **abertura do cardápio**; senão o cartão é da lista
  (seção ou subdivisão) e fica **antes do prato `antes_do_item`** — nulo, ou o prato fora da tela
  (horário, esgotado escondido, tirado do cardápio: `ON DELETE SET NULL`), vai ao FIM da lista.
  ⚠️ Posição colada no prato, não número de ordem: as setas e o vencedor do A/B de ordem mexem
  nos pratos, e o cartão vai junto sem ninguém tocar nele.
- ⚠️ **Cartão não é item**: item é produto (preço, PDV, A/B, eventos por produto); um `id_produto`
  nulo em `catalogo_itens` espalharia o caso especial por tudo. Tabela própria.
- **Abertura de seção automática**: seção/subdivisão com foto OU vídeo ganha tela própria (nome e
  descrição) antes do primeiro prato. Vídeo novo em `catalogo_categorias/subcategorias.video_url`
  (janela da seção), que ganha da foto. Sem foto nem vídeo, não há abertura.
- **A sequência é montada NA TELA** (`components/cardapio-vivo/sequencia.ts`), não no servidor:
  os pratos chegam filtrados e reordenados, e o cartão cola no que sobrou. Com filtro de restrição
  ligado, só pratos. ⚠️ Seção sem prato direto (tudo em subdivisões): o cartão "no fim" dela vai
  logo depois da abertura, senão nunca apareceria.
- Feed: `cartao-feed.tsx`, classe `cv-conteudo` (⚠️ NÃO `cv-item`: as verificações contam os
  pratos por ela). O observador lê `data-pos` (posição na sequência) para prato e cartão.
  Sem mídia, o fundo é a capa da casa e o texto vai ao centro; com mídia, ao pé, sobre o véu.
- Mídia do cartão: foto OU vídeo (a última enviada troca a outra); vídeo pela mesma conversão do
  prato. Cartão vazio (só vídeo, antes do vídeo) grava e NÃO aparece no feed.
- Medição: `viu_cartao` (id_cartao), `viu_secao` (id_categoria + id_subcategoria, colunas novas
  em `cardapio_eventos`), `clicou_cartao` (o "Ver o prato"). O cartão de outro cardápio vira nulo,
  como o item. O editor mostra vistas, segundos médios e cliques dos últimos 30 dias.
- Editor: painel "Abertura no Cardápio Vivo" acima das seções; "+ cartão" ao lado de "+ pratos";
  o cartão aparece NA lista dos pratos, no lugar dele (`cartoes-do-catalogo.tsx`,
  `janela-cartao.tsx`). Criar deixa a janela aberta para pôr a mídia. Aviso (não trava) acima de
  um cartão a cada 4 pratos — a recomendação dada ao dono.
- Tradução: entidade `cartao` em `services/traducao.py` (título = nome, texto = descrição), no
  automático e no "traduzir o catálogo". A correção à mão (16/10/2026) fica na janela do cartão
  ("traduções"; `Traducoes` com rótulos Título/Texto). ⚠️ O título traduzido cabe em 120 letras
  (coluna da 120): a rota `/traducao/cartao/{id}` recusa acima disso com 422, em vez de deixar o
  banco estourar.
- `limpar_dados.py`: `catalogo_cartoes` sai junto dos itens (aponta para eles; sem isso o
  TRUNCATE era recusado).
- Cobertura: `smoke_cardapio_cartoes.py` (35) e `web/scripts/verificar-cartoes-feed.mjs` (13).
- ⚠️ **Texto longo não se corta** (16/10/2026, a abertura do Catering no ar: 465 letras com quebra a
  cada ~30, cortada pelo `line-clamp-6`). Acima de 220 letras ou 6 linhas o cartão usa letra de
  15 px e véu na altura toda; o bloco de texto nunca sobe por baixo do topo (7rem) e, no limite,
  rola dentro do cartão. Sem mídia, `justify-[safe_center]` centraliza sem cortar o começo.
  As quebras de linha que a casa digitou são mantidas (o outro cartão dela é uma citação em versos).

### O idioma, um só para o site e o feed (16/10/2026)
🔑 **Pedido do dono:** *"ao selecionar o idioma na primeira página, leva para as demais; mas se
selecionar dentro do catálogo, ao voltar, se perde a seleção. E manter o mesmo estilo de seleção
em todas as páginas."*
- O feed passou do `<select>` para a MESMA pílula PT · EN · DE do site
  (`components/cardapio-vivo/seletor-idioma.tsx`), no topo do feed e no alto da capa do Hub (o
  lugar dela no site).
- 🔑 **A escolha mora na ABA, na chave do site** (`sessionStorage["botane.idioma"]`): site e feed
  estão no mesmo endereço, então o que se escolhe num vale no outro. Ordem no feed: `?idioma=` do
  link (gravado na aba), depois a aba, depois o navegador.
- ⚠️ Antes, no computador, as opções do `<select>` herdavam a letra clara do feed e saíam branco
  sobre branco (no celular a lista é do sistema). A pílula acaba com isso.
- Cobertura: `verificar-idioma-site.mjs` seção 5 (ida e volta site ↔ feed).

## Anúncios no Cardápio Vivo, fase 1 (migração 121, 16/10/2026)

🔑 **Pedido do dono:** *"um plano de anúncios no meio do cardápio"* — texto, foto ou vídeo; período e
dias; externo (outra marca) ou da casa (o catálogo do Dia dos Namorados); links; formas e tempo de
exibição; métricas; *"nada pesado… algo bem orgânico"* e, depois, variações e um ritmo que aprende.
Proposta em três fases aprovada, com as respostas: **a casa cadastra e apresenta o RELATÓRIO** ao
parceiro (sem acesso de anunciante); **na mesa e pelo link**; ritmo de partida **5º prato / 8 de
distância / máximo 2 (1 na mesa)**, ajustável; **grupo de controle de 10%** pode (fase 2).
- `cardapio_anuncios` é da LOJA. ⚠️ Anúncio ≠ cartão (120): o cartão é editorial e fixo; o anúncio
  tem período (datas, dias, horário, dias especiais — a regra `_secao_visivel` das seções) e a TELA
  decide onde entra. Origem CASA ("Da casa") ou EXTERNO ("Patrocinado · marca", anunciante
  obrigatório): propaganda tem de ser reconhecível. Botão: abrir catálogo da casa (o feed dele, se for
  Cardápio Vivo; senão o site com `?catalogo=`), ir a um prato deste cardápio, ou link (outra aba).
- **O ritmo é da casa** (`cardapio_config.anuncio_*`, tela Anúncios). ⚠️ Colunas FORA do `_PADRAO` da
  configuração: o "Aparência" grava só as dele e não volta o ritmo ao padrão (testado).
- `sequencia.ts` → `intercalarAnuncios`: o 1º depois de N pratos, M pratos entre eles, no máximo K
  (o servidor já manda o K da mesa), nunca o mesmo duas vezes, sempre ANTES de um prato (nunca no
  fim). Sorteio por PESO com semente = sessão anônima: a mesma visita vê a mesma ordem ao redesenhar.
  Com filtro de restrição: nenhum. O anúncio que leva ao PRÓPRIO catálogo não aparece nele. A prévia
  do cadastro não mostra anúncio.
- Medição: `viu_anuncio` / `clicou_anuncio` com `id_anuncio` (anúncio de outra loja vira nulo).
  "Pulou" = menos de 1,5 s na tela. ⚠️ O toque que troca de página manda o lote ANTES de navegar.
- **Relatório** (`/cardapio-vivo/anuncios/{id}/relatorio`): pessoas (sessões), aparições, tempo médio,
  tocaram, taxa de toque, passaram direto; por dia, por canal (mesa × link) e por hora; impressão do
  navegador ("Imprimir / salvar em PDF"). ⚠️ Vem do bruto: o que passou da retenção (13 meses) sai.
- **Aberturas de seção configuráveis** (mesmo pedido: "isto poderia ser configurado"):
  `cardapio_vivos.aberturas` AUTOMATICA / SO_VIDEO / NUNCA e `abertura` por seção. ⚠️ No modelo da
  seção o campo é OPCIONAL (nulo = não muda): renomear pela janela antiga não religa o que a casa
  desligou.
- ⚠️ `justify-[safe_center]` (o centro do cartão só de texto, 1.1.104) NÃO gerava CSS: o texto ficava
  no alto. Virou um envoltório `my-auto`, que centraliza e não corta o começo do texto longo.
- `limpar_dados.py`: `cardapio_anuncios` sai com os itens (o botão aponta para um).
- Cobertura: `smoke_cardapio_anuncios.py` (34) e `web/scripts/verificar-anuncios-feed.mjs` (12).
- **Fases 2 e 3: feitas na 1.1.112** (migração 125, 20/10/2026) — ver a seção própria, no fim.

## Análise de integridade, visualização e processo (17/10/2026)

🔑 **Pedido do dono:** *"agora que temos o cardápio completinho, uma análise para melhorar a
integridade dos dados, melhor visualização, possíveis melhorias no processo e atualização do
Ajuda"*. O manual ganhou a seção `cardapio-vivo` (17) e a parte de catálogos refeita. Da proposta,
o dono aprovou os três de integridade (*"pode seguir nessa ordem: 1, 2 e 3"*), feitos na 1.1.108:
- **1. Excluir leva a mídia.** `catalogo_conteudo.midias_do_conteudo` junta foto, vídeo e capa da
  seção, das subdivisões e dos cartões (que o CASCADE leva); `excluir_categoria/subcategoria` e
  `catalogos.excluir` apagam cada uma no mesmo cursor. Antes saía só a `foto_url` (e, do catálogo,
  só o PDF). ⚠️ Na junção das subdivisões, `foto_url` sem alias é AMBÍGUA (500 pego pela suíte).
- **Arquivos sem dono** (`services/arquivos_orfaos.py`, `/empresa/arquivos-orfaos`, cartão na tela
  Empresa, `admin.empresa`): quem aponta é descoberto pelo `information_schema` (toda coluna de
  texto com `url` no nome, tabela base), não por lista escrita à mão; nada com menos de 1 dia; o
  apagar refaz a conferência e grava auditoria. Na base local: 235 de 373, 4,7 MB.
- **2. A medição diz de qual Cardápio Vivo veio** (migração 122): `cardapio_eventos.id_catalogo`,
  NO EVENTO (a sessão anônima é a mesma ao passar da mesa para o catering), sem FK como os outros
  ids do evento. Preenche o passado pelo item/cartão/seção e depois pela sessão de um cardápio só.
  Atenção × Vendas e o resultado do A/B filtram `coalesce(e.id_catalogo, X) = X` (o evento sem
  cardápio é anterior e conta, como contava); o relatório do anúncio ganhou `por_cardapio`.
- **3. Anúncio "com problema".** `listar` calcula `avisos` (as mesmas regras de `do_feed` e de
  `acaoDoAnuncio`): sem conteúdo, catálogo do botão apagado ou fora do ar, prato do botão fora do
  cardápio ou de catálogo que não é vivo, nenhum cardápio onde aparecer, só-mesa fora do principal.
  Com aviso, a situação vira `COM_PROBLEMA`; `fora_do_horario_agora` é só informativo.
- Ficaram como proposta: A/B e Atenção por cardápio (não só o principal), o "O que falta" com
  traduções e cartões, prévia com anúncios, esgotado que volta sozinho, Spaces, anúncios fases 2/3,
  e o resumo diário de cartões/seções/anúncios (hoje só pratos — somem na retenção).
- ⚠️ `verificar-cardapio-testes.mjs` falhou uma vez em "a ordem sugerida passa a valer para todos"
  logo após "Aplicar B" e passou ao rodar de novo — corrida entre o clique e o GET do feed.
  Corrigido na 1.1.109: o roteiro espera o feed mudar (até 10 s) antes de conferir.

## As propostas da análise, entregues (1.1.109, 19/10/2026)

- **Atenção × Vendas e Testes A/B por Cardápio Vivo.** `?id_catalogo=` no painel e nas sugestões
  de destaque, `id_catalogo` no corpo do teste novo; sem ele, o principal.
  `cardapio_atencao.cardapio_do_painel` só aceita Cardápio Vivo DA LOJA (404 com frase).
  ⚠️ O evento sem cardápio (anterior à 122) conta só para o PRINCIPAL (`coalesce`); nos outros o
  filtro é `e.id_catalogo = X` exato. A resposta traz `cardapio` e `cardapios`; a tela mostra o
  campo *Cardápio* (`escolha-cardapio.tsx`) só com dois ou mais. O teste A/B lista o nome do
  cardápio quando a loja tem mais de um.
- **"O que falta" com cartões e traduções.** `GET /traducao/catalogo/{id}/pendentes` ganhou
  `por_tipo` (`pendentes_por_tipo`, a MESMA regra da contagem). O painel junta: pratos (como
  antes), cartões vazios ("não aparece") ou com botão para prato inativo (`faltasDoCartao`), e o
  que está só em português (nomes, e o atalho para a aba Idiomas). O contador do botão soma os três.
- **Prévia com anúncios**: `GET /cardapio-vivo/previa?anuncios=true`; na mesa (teto da mesa,
  só-mesa entra) quando o catálogo é o principal. A prévia não tem medidor, então não conta
  impressão. A tela do Cardápio Vivo tem a caixa "com os anúncios de agora" (`?anuncios=1` no iframe).
- **Esgotado que volta sozinho** (migração 123, `catalogo_itens.esgotado_ate`). 🔑 A conta é NA
  LEITURA (`esgotado AND (esgotado_ate IS NULL OR esgotado_ate > now())`, no feed, no conteúdo e
  na marca); o `reter` da madrugada só limpa a linha. `esgotado_volta: AMANHA` = 4h do próximo dia
  da casa (antes das 4h, as 4h de hoje); `MANUAL` ou ausente = até alguém tirar — ⚠️ ausente fica
  como era de propósito: o conector e quem já chamava a rota não mudam de comportamento. A gaveta
  pergunta antes de marcar, com "volta sozinho amanhã (4h)" como padrão.
- **Resumo diário de anúncios, cartões e aberturas** (migração 124, `cardapio_conteudo_dia`),
  feito por `agregar_dia` junto com os pratos. O relatório do anúncio soma o resumo nos dias
  ANTES do primeiro evento bruto da loja (`_somar_resumo`) e devolve `resumido` com a frase:
  pessoas contadas POR DIA, sem distribuição por hora. Cartões e aberturas só são guardados — as
  telas deles olham 30 dias, dentro de qualquer retenção.
- **1.1.111 (20/10/2026): o editor do catálogo lê o resumo.** `GET /catalogos/{id}/cartoes?dias=`
  aceita SÓ 30, 90 ou 365 (422 no resto) — ⚠️ com 30 o resumo nunca entra, porque a retenção
  mínima é 1 mês = 30 dias; foi por isso que o período virou escolha. `catalogo_cartoes._somar_resumo`
  soma, nos dias antes do primeiro bruto da loja, vistas, `soma_ms` e cliques; os segundos médios
  saem de `soma_ms ÷ vistas` DEPOIS da soma (média de médias erraria). Seção do resumo que o bruto
  não tem nasce na lista; `id_sub = 0` volta como `id_subcategoria` nulo. Na tela: o campo
  `#cartoes-periodo` ("Atenção dos") no painel Abertura no Cardápio Vivo, o aviso `#cartoes-resumido`
  e — novo — a atenção da abertura de cada seção no cabeçalho dela (`[data-abertura-atencao]`):
  a API já devolvia `aberturas` desde a 120 e nenhuma tela mostrava.
- Ficaram: Spaces + CDN (medido em 20/10/2026: a Cloudflare do App Platform já faz o papel de CDN — ver
  `infra-e-deploy.md`) e anúncios fases 2/3 (feitas na 1.1.112). O manual foi conferido na 1.1.110.

## Anúncios, fases 2 e 3 (migração 125, 1.1.112, 20/10/2026)

🔑 O que a proposta aprovada em 16/10 deixou para depois: o ritmo que aprende, a relevância, o grupo
de controle e as variações. Pedido do dono na hora de seguir: *"pode seguir no 6 7 e 8"*.
- **Ritmo que aprende** (`cardapio_config.anuncio_recuo`, ligado por padrão) mora na TELA
  (`sequencia.ts → intercalarAnuncios`, opção `reacoes`): PULOU (< `PULOU_MS` = 1,5 s, o mesmo do
  servidor) dobra o intervalo até o próximo; dois IGNOROU (parou e não tocou) encerram os anúncios da
  visita; TOCOU não muda nada. 🔑 Só existe reação para anúncio JÁ visto, e ele está antes de onde a
  pessoa está: refazer a sequência muda só o que vem depois, e o sorteio (mesma semente, mesma ordem
  de chamadas) não mexe nos que já passaram. ⚠️ O "pulou" é avisado mesmo abaixo dos 300 ms que o
  evento exige (`Medidor.aoVerAnuncio`): passar voando É o pulou.
- **Relevância**: `cardapio_anuncios.secoes` (categorias; nulo = todas) — antes de um prato dessas
  seções o peso no sorteio TRIPLICA (`PESO_DA_RELEVANCIA`). O anúncio de ação PRATO combina sozinho
  com a seção do prato dele. Não restringe: fora delas ele aparece com o peso normal.
- **Grupo de controle** (`cardapio_config.anuncio_controle`, 0–50, padrão 10): `do_feed` recebe a
  sessão e calcula `SQL_CONTROLE` (hashtext da sessão + ':anuncios', mod 100) — abaixo do percentual,
  `anuncios` vazio e `grupo_anuncio = CONTROLE`; senão EXPOSTO. Sem sessão (recusou a medição, prévia)
  ou sem anúncio válido = nulo, fora da comparação. ⚠️ **O grupo é GRAVADO em cada evento**
  (`cardapio_eventos.grupo_anuncio`, vindo do lote): mudar o percentual não reescreve o passado.
  `GET /cardapio-vivo/anuncios/efeito` compara engajadas (`SQL_SESSAO_ENGAJADA`), adicionaram e pratos
  vistos, com o `_proporcoes` dos A/B (116). ⚠️ "Exposta" = PODIA ver.
- **Variações** (`cardapio_anuncio_variantes`, até `MAX_VARIANTES` = 3 além da original): título,
  texto e rótulo do botão, com tradução própria (`traducao` tipo `anuncio_variante`). A mídia e o
  destino são do anúncio. Sorteio `SQL_VARIACAO` (sufixo diferente do controle: os dois não andam
  juntos), posição 0 = a original. O evento leva `id_variante` (sem chave estrangeira: aplicar ou
  apagar não apaga a medição; id que não é daquele anúncio vira nulo). O relatório ganha `variantes`
  (cada texto × a original pela taxa de toque; vencedora = a que bate a original com p < 0,05 e maior
  taxa). Aplicar (`POST …/variantes/aplicar`) copia texto e traduções para o anúncio e APAGA todas as
  variações — fim do teste; nulo = fica a original. ⚠️ O resumo do dia (124) não separa por variação.
- ⚠️ **Bateria**: com o controle em 10% por padrão, um teste de navegador que espera anúncio falharia
  em uma rodada de cada dez. `verificar-anuncios-feed.mjs` grava `anuncio_controle: 0` e
  `anuncio_recuo: false` no cenário, e testa os dois na seção 1b. O `smoke_cardapio_anuncios.py`
  restaura as seis colunas de regras no fim.
- Cobertura: `smoke_cardapio_anuncios.py` 73 (25 novas, 5e e 5f) e `verificar-anuncios-feed.mjs` 26.

## Excluir catálogo e apagar a medição de um período (1.1.113, 20/10/2026)

🔑 Pedido do dono: *"cria um botão para poder excluir cardápios e realizar a limpeza de dados de
determinado período"* — o "Catering" de teste e a medição de teste só saíam por SQL
(`.tmp/limpeza_producao.sql`, que deixou de ser necessário).
- **Excluir** (`services/catalogos.excluir`): RASCUNHO direto (como era); INATIVO só com
  `?confirmar_nome=` igual ao nome (sem ligar para maiúsculas); ATIVO nunca — 409 "tire do ar".
  ⚠️ Revoga a regra "só rascunho se apaga" de 21/09 — decisão do dono. `GET /catalogos/{id}/exclusao`
  é a prévia (seções, pratos, cartões, pedidos, testes, anúncios, eventos, se é Cardápio Vivo). O
  banco leva em cascata seções, itens, cartões, `cardapio_vivos`, `cardapio_testes`, lojas e config
  de pedidos; `pedidos` e `cardapio_anuncios.acao_catalogo` ficam com NULL. A medição do catálogo
  (`cardapio_eventos` e `cardapio_conteudo_dia` por `id_catalogo`, sem chave estrangeira) é apagada
  à mão no mesmo cursor, junto da mídia. Tela: `janela-excluir-catalogo.tsx` (aba Publicação,
  `#catalogo-excluir`, nome em `#excluir-catalogo-nome`).
- **Medição de um período** (`cardapio_vivo.medicao_do_periodo` / `apagar_medicao`,
  `GET /cardapio-vivo/medicao` e `POST /cardapio-vivo/medicao/apagar`, `catalogos.editar`, auditado):
  eventos da LOJA no período, os três resumos por dia (`agregados`, `resumo`, `conteudo`) e as
  sessões que ficaram sem evento. ⚠️ Sessão com evento em outro dia FICA. Não toca em anúncios,
  testes, chamados nem pedidos (`pedidos.id_sessao` não tem chave estrangeira). Tela:
  `medicao-do-periodo.tsx`, no fim do Cardápio Vivo.
- Cobertura: `smoke_catalogos` (+8), `smoke_cardapio_vivo` 11b (+7) e `verificar.mjs` 11z (+5).


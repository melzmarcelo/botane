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

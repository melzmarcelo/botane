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

1. **A importação do PDF** — hoje `origem` diz `PDF` e o arquivo ainda não sobe. A capa
   existe para receber esse anexo.
2. **Os itens do catálogo** — como cada prato entra, e como ele se liga ao produto daqui.
3. A publicação no **site de reservas**. ⚠️ É aqui que entra a regra que escolhe entre os
   vários ativos; ela não existe, e o cadastro não a inventa.

⚠️ **Ao fechar qualquer uma delas, revise ESTA lista.** Lista de pendências envelhece pior
que decisão — a memória de Reservas passou uma semana dizendo que o que estava feito não
tinha começado.

# Geral / não classificado

> Extraído do CLAUDE.md original (seções "O que já existe" e "Armadilhas já pagas").
> Consultar antes de mexer nesta área do sistema.

## O que já existe

- `api/db_scripts/`: 001 acesso+empresa, 002 permissões e papéis de fábrica, 003 empresa inicial.

- **Loja atual em `seguranca.unidade_atual(cur, ctx)`** (19/08/2026): estava copiado em SETE
  routers, e a cópia ficou para trás quando o seletor passou a existir. A escolha vem do
  cabeçalho **`X-Unidade`** (não do corpo: vale para GET e nenhuma tela precisa repassá-la),
  validada com `ctx.ve_unidade` — mandar o cabeçalho não dá acesso a loja nenhuma.

- ⚠️ **Voltar tem de parecer um controle**: era `class="rotulo"` (10,5px, maiúsculas, cinza) e
  lia como legenda. Virou `.link-voltar`, pílula com borda e seta.

- ⚠️ **`.campo` é `width:100%` e vence a utilitária de largura do Tailwind.** `w-[110px]` num
  input com `campo` não faz nada — a largura tem de ir na COLUNA (`<th>`), e com `min-w` além
  do `w`: em `table-layout: auto` o navegador ignora a largura sugerida quando falta espaço.

- **`web/scripts/base-vazia.mjs`** passa por todas as 26 telas com a base ZERADA e diz qual
  quebra. ⚠️ Tela com zero registro é o estado que ninguém testa e que o cliente vê no primeiro
  dia: divisão por zero, `lista[0]` e `.toFixed()` em nulo só aparecem ali — e aparecem na frente
  de quem está conhecendo o sistema. Não cria nada; roda depois de `limpar_dados.py`.

- ⚠️ **`.campo` tem `font-size: 15px` e vence a utilitária** — abaixo de 16px o Safari do
  iPhone dá **zoom ao focar** e a tela salta a cada campo. Use `.campo-toque` (16px + alvo
  maior) em tela de uso no aparelho. `scripts/celular.mjs` fotografa e checa corte lateral.

- ⚠️ **`innerText` não enxerga valor de campo.** Depois que a escolha virou input, "o nome
  aparece na tela" ficou falso no teste e verdadeiro no monitor — `verificar.mjs` tem
  `textoVisivel()`, que junta `innerText` com o valor dos inputs.

- ⚠️ **Digitar por um HANDLE some no vazio quando a tela recarrega.** A checagem nova do
  Vincular ficou três rodadas falhando com "a busca não seleciona": a fusão do bloco anterior
  dispara `window.location.reload()`, e o recarregamento chegava DEPOIS, desmontando a janela
  recém-aberta. Digitar num input descartado **não dá erro nenhum** — o texto some, o Tab cai
  em campo vazio e a falha aparece como defeito da busca. Duas correções, e as duas valem como
  regra: **esperar a navegação pendente** (`waitForNavigation(...).catch(() => {})` depois da
  ação que recarrega) e **digitar de DENTRO do documento**, conferindo o valor antes de seguir.

- ⚠️ **Um bloco de tela que depende de rede vai num `try`.** Uma exceção custa as checagens do
  resto da rodada; um `checar` que falha custa uma linha — e o `catch` leva junto a URL e o
  texto da janela, senão a falha diz só "timeout" e não onde.

- ⚠️ **`elementHandle.click()` também estoura o `protocolTimeout`** — e não só o `p.click`.
  Limpar o campo de busca com `(await p.$(campo)).click()` derrubou a rodada inteira num ponto
  sem defeito nenhum: ele rola o elemento e espera ele ficar estável. Focar de DENTRO do
  documento (`p.evaluate(() => input.focus())`) e seguir com `p.keyboard` faz a mesma coisa sem
  depender de layout.

- ⚠️ **Procurar no DOCUMENTO INTEIRO uma string que também mora na casca.** A checagem "a lista
  de lojas só aparece depois de escolher restringir" usava
  `body.innerText.includes(apelido_da_filial)` — e o apelido aparece no **seletor de loja da
  barra superior**, então ela era verdadeira antes de a lista existir e o teste acusava a tela
  de mostrar o que ela não mostrava. Medir pelo **id do elemento** (`#loja-<id>`), que só existe
  onde interessa. É a armadilha do "primeiro elemento que casa" pela outra ponta.

- ⚠️ **`p.click` do puppeteer estourou o `protocolTimeout` na barra superior** — ele rola o
  elemento e espera ele ficar estável, e a dança derrubou a rodada inteira num ponto sem
  defeito. Clique de DENTRO do documento (`p.evaluate(... .click())`) faz a mesma coisa sem
  depender de layout. ⚠️ E a tela do Perfil se alcança pelo ENDEREÇO: encenar o clique num
  link que fecha o próprio menu ao ser clicado só acrescenta interação frágil.

- ⚠️ **A agenda é lista de TAREFA, não histórico**: linha produzida some dela. O que já foi
  feito aparece em "Produções recentes" — misturar faria a agenda crescer para sempre e
  esconder o que falta no meio do que já foi. `?status=PRODUZIDA` traz o histórico, para
  conferir plano contra realizado.

- 🔑 **`irPara` re-lançava `ProtocolError: … timed out` e derrubava a rodada inteira** num
  `goto` comum, depois de 280 checagens verdes. O laço já tratava "detached Frame" — é a mesma
  família: navegação que não termina limpa. Três tentativas continuam sendo o teto, então um
  travamento de verdade ainda estoura, só que depois de o sistema ter tido chance. **Uma
  exceção custa as trezentas checagens seguintes; um `checar` que falha custa uma linha.**

- 🔑 **A lista das TABELAS DE APOIO pagina, e o registro da rodada cai fora da primeira
  página.** "Poucos por natureza" era suposição — a base tem dezenas de setores, e um nome que
  começa com T fica na página 2. A checagem acusava a tela de não oferecer "editar" numa linha
  que ela nem mostrava. A suíte passou a aumentar a página para 100 antes de procurar, que é o
  que uma pessoa faria. ⚠️ E a afirmação "salvar troca o nome sem criar outro registro" passou
  a ser feita pelo SERVIDOR: ela é sobre o ESTADO, não sobre o que cabe na tela.

- ⚠️ **Sono fixo depois de abrir a CONTAGEM derrubou a rodada três vezes num dia** (01/09/2026).
  Os 2,2 s bastavam com dez linhas e pararam de bastar com uma contagem de centenas: a checagem
  media a tela ainda em branco e acusava a contagem de não ter campo nenhum. Virou espera pelo
  campo de digitar. ⚠️ E o passo seguinte fazia `c.focus()` sem guarda: com a tela vazia era
  `Cannot read properties of null`, e a rodada INTEIRA morria ali — **um `checar` que falha
  custa uma linha; uma exceção custa as trezentas checagens seguintes.**

- 🔑 **O mesmo em `locais_estoque` — e aqui NÃO se apaga** (10/09/2026). A matriz tinha **256
  locais ativos com 4 de verdade** (`CANTO DO BAR`, `CENTRAL REL` e parentes, das mesmas duas
  suítes). O estrago é maior que o dos setores: o seletor de local do produto oferece TODOS os
  da loja, que é o defeito que a tela já pagou uma vez ("o seletor oferecia 93 locais").
  🔑 **Nenhum dos 252 podia ser apagado, e o banco é quem diz**: todas as chaves para
  `locais_estoque` são `NO ACTION` (`estoque_movimentos`, `estoque_saldos`, `estoque_lotes`,
  inventários, notas, produções, transferências e `produtos.id_local_padrao`), e os 252 eram
  referenciados pelo razão — 719 lançamentos. A saída é DESATIVAR, que é o que o próprio
  `DELETE /locais/{id}` da API faz: some das telas, o razão fica inteiro.
  ⚠️ **É o contrário do que valeu para os setores**, e a diferença está nas chaves: lá são
  `SET NULL`/`CASCADE` e apagar passa em silêncio; aqui são `NO ACTION` e o banco recusa. Ler a
  regra de exclusão antes de escolher entre apagar e desativar é o que separa os dois casos.
  ⚠️ **`ESTOQUE` aparece 201 vezes e NÃO é resíduo de local**: é o primeiro local que nasce com
  cada loja, e o que acumulou foram as **unidades** (202 na base, 1 ativa). Como local é
  escopado por loja, essas 201 não sujam a lista da matriz — o resíduo de verdade era só o dela.

- 🔑 **Suíte que cria tabela de APOIO tem de desativar o que criou** (10/09/2026). `setores`
  não pagina no dia a dia porque se supõe curta — e a base local tinha **309**: 7 de verdade e
  o resto criado por rodada de bateria. Quem engordou: `smoke_estoque` ("Confeitaria <marca>",
  41 vivas), `smoke_relatorios` ("Bar rel" e "Confeitaria rel", 39 de cada) e a `verificar.mjs`
  em rodadas que falhavam antes da renomeação. As três passaram a desativar; medido depois de
  três baterias inteiras, os ATIVOS ficaram em 7.
  ⚠️ **O sintoma não parece resíduo.** Com mais de cem linhas, a checagem da tabela de apoio
  deixou de achar a PRÓPRIA linha (caiu para a segunda página) e acusou a tela de não oferecer
  editar. Escolher "100 por página" foi a correção anterior, e ela some assim que a base cresce
  mais um pouco — a de agora vira a página até achar.
  ⚠️ **Desativar, não apagar**: é o que a API oferece, e o local que aponta para o setor
  continua fazendo sentido sem ele. O que se apaga é resíduo VELHO, na mão e conferindo antes.
  ⚠️ **Conferir o que depende antes de apagar setor.** As chaves são `ON DELETE SET NULL`
  (produtos, locais) e `CASCADE` (`usuario_setores`): apagar nunca dá erro — dá SILÊNCIO, e um
  produto de verdade perde a classificação sem nada avisando. Na limpeza de hoje foram dois
  (dois chás do catálogo do Omie que estavam classificados em "BAR REL 602900", um setor de
  teste) e eles ficaram sem setor.
  ⚠️ **`limpar_dados.py --residuo-de-teste` NÃO serve para isto**: ele TRUNCA `setores`,
  `locais_estoque`, `categorias` e `papeis` inteiras, levando junto os de verdade.
  ⚠️ **`locais_estoque` tem o mesmo problema e continua aberto**: 119 locais ativos de resíduo
  ("CANTO DA CONF <marca>" e parentes), criados pelas mesmas suítes e nunca desativados.

## Armadilhas já pagas

- **`EmailStr` recusa domínio `.local`** (reservado). Por isso o admin é `@botane.com.br`.

- ⚠️ **Parâmetro NULL sem tipo dentro de `COALESCE` estoura no Postgres**: em
  `COALESCE(validade, '9999-12-31') = COALESCE(%s, '9999-12-31')`, um `None` vira `text` e dá
  "operador não existe: date = text". Entrada com lote **sem validade** dava 500 desde a etapa
  4 porque nenhum teste passava por esse caminho. Corrigido com `%s::date`.

- Teste que usa acento ou espaço na query precisa de `urllib.parse.quote` — o urllib recusa.

- `input[type=number]` no Chrome não seleciona conteúdo com `clickCount: 3` — no teste de
  navegador, limpar com ctrl+A, senão o valor entra colado (1 + 8 = 18).

## Stack e portas

- 🔑 **O painel abre com o que a cozinha DESTA pessoa tem para fazer** (`GET /inicio`, bloco
  `producao`, cartão **Para produzir**, 03/09/2026, pedido do dono). A agenda de produção
  existia desde a etapa de fichas, mas só na tela dela: quem entrava de manhã via o painel do
  mês e tinha de navegar até Produção para descobrir o que assar hoje. E, com Bar, Confeitaria e
  Cafeteria na mesma lista, quem é da Confeitaria percorria a agenda inteira para achar as duas
  linhas dela.
  🔑 **O bloco vem ANTES do corte do dinheiro, de propósito.** `GET /inicio` devolve cedo para
  quem não tem `cmv.painel`; pôr a produção depois desse `return` daria à cozinha um painel só
  de contagens — que é justamente o que o pedido veio corrigir. Hoje a cozinha abre o sistema e
  vê o que tem para produzir.
  ⚠️ **E isso não abriu valor nenhum.** O bloco carrega quantidade e data, nunca custo; a suíte
  cobra que nenhuma chave de linha contenha "custo" ou "valor", e que `dinheiro`, `dia` e
  `pesos` continuem vazios para quem não vê dinheiro.
  ⚠️ **Sete dias à frente, só `PLANEJADA`, de ontem em diante** — as mesmas regras da tela de
  agenda. Ler diferente faria as duas discordarem sobre o que está pendente.
  ⚠️ **Produto SEM setor aparece para todos**: ele não é de ninguém, e escondê-lo sumiria com a
  linha do painel da casa inteira, sem nada dizendo por quê.
  ⚠️ **A resposta diz se é recorte ou casa inteira** (`todos_setores`), e a tela usa isso na
  frase do vazio: "nada planejado" sem essa distinção se lê como "a casa não produz nada".
  ⚠️ **`new Date('aaaa-mm-dd')` é meia-noite UTC** — em Brasília, o dia anterior às 21h. A data
  da linha é fatiada do texto (`diaCurto`), nunca construída: senão a agenda de amanhã apareceria
  como hoje. Mesma armadilha que `lib/datas.ts` documenta, pela ponta da leitura.

- 🔑 **Dinheiro no painel já obedecia a permissão, e continua** (`cmv.painel`). Medido em
  03/09/2026 com um usuário de Cozinha: `dinheiro`, `dia` e `pesos` voltam nulos/vazios, e
  sobram as contagens e os alertas, que são texto sem valor. `/inicio/dia` e `/inicio/rede`
  exigem a mesma chave. Hoje a têm Administrador, Gerente e Contador; não a têm Cozinha,
  Conferente e Salão. ⚠️ **Quem quiser mudar isso mexe no PAPEL, não no código** — é a chave que
  decide, e ela é configurável na tela de Papéis.

- **O que falta na primeira parte está em [`docs/o-que-falta.md`](docs/o-que-falta.md)** —
  levantado em 25/08/2026 comparando o MAPEAMENTO item a item com o que existe. O maior item
  é a **carga inicial das fichas**: com zero fichas não há CMV teórico, nem variância, nem
  food cost. O documento também registra as três decisões em que a construção divergiu do
  mapeamento e por quê (a venda passou a baixar estoque, `modo_producao`, `KIT`).

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

- **`tests/cenario_semana.py`**: a operação de uma semana com um usuário por papel (gerente,
  conferente, cozinha, salão, contador) — quem pode o quê, e a conta fechando no fim. Com a
  baixa da venda no lugar, a **variância = perdas + ajustes** exatamente, e o food cost sai em
  30,6%. Foi ele que achou a falha acima. ⚠️ Mede **delta** da apuração e afirma só sobre os
  produtos que ele mesmo mexeu: a base é compartilhada com as outras suítes.

- ⚠️ **Foto de página inteira não pode derrubar a bateria.** `fullPage` estoura o
  `protocolTimeout` do Chrome numa tela longa; aconteceu com o painel de CMV e voltou a acontecer
  quando Integrações ganhou o segundo bloco de agenda — e levou junto as 280 checagens da rodada.
  `foto()` agora cai para a foto da JANELA e avisa; o `protocolTimeout` subiu para 60 s.

- ⚠️ **"A primeira `table.tabela` da página" media a tabela errada.** A checagem do custo inicial
  do Omie perguntava se havia linhas com um seletor que casa com QUALQUER tabela da tela de
  Integrações: ela dizia "há o que aplicar" quando a lista estava vazia. Casar por **id**
  (`#custos-iniciais`). É a armadilha do "primeiro elemento que casa" outra vez.
  ⚠️ E a afirmação virou uma **propriedade**, não o estado do dia: havendo o que aplicar, o
  gravar é um botão separado; não havendo, a tela DIZ por que a lista está vazia. Exigir o botão
  sempre acusava a tela de um defeito que era do dado — e passou a falhar no instante em que a
  base foi limpa.

- ⚠️ **Duas rodadas do `verificar.mjs` no mesmo arquivo de saída se atropelam.** As duas escrevem
  em `scripts/_saida-navegador.txt` e disputam a mesma API local: o resultado lido era o da
  rodada velha, com falhas que a nova já tinha corrigido. É a versão de dois processos da nota
  "rodar a suíte de API junto com a de navegador inventa falha".

- ⚠️ **Handle de elemento ENVELHECE, e `p.evaluate(fn, handle)` estoura o `protocolTimeout`.**
  O laço `for (const b of await p.$$("button")) { await p.evaluate(el => el.innerText, b) }`
  derrubou a rodada inteira num ponto sem defeito nenhum — a troca de loja recarrega a página
  (`window.location.reload()`), então os handles colhidos antes já não existem. O texto continua
  sendo o que identifica o botão; a procura é que tem de ser feita **de dentro do documento**,
  num `p.evaluate` só. Mesma família da nota abaixo.

- ⚠️ **Fixture com data fixa envelhece.** As notas simuladas nasceram em 16–20/08/2026 e uma
  semana depois já caíam fora da janela automática da busca — o teste dizia que a importação
  tinha parado. `cliente._aproximar_datas` traz as datas da fixture para a semana de hoje
  mantendo o intervalo entre elas. Vale também para a demonstração: sistema que só mostra nota
  do mês passado parece parado.

- ⚠️ **Suíte de navegador que quebra no MEIO deixa rastro que derruba a próxima.** A limpeza de
  notas roda no fim; uma quebra antes dela deixou uma nota manual órfã, e as rodadas seguintes
  falharam num ponto sem relação nenhuma com a causa. Antes de caçar bug numa suíte que
  começou a falhar sozinha, **procure a sobra da rodada anterior**.
  ⚠️ O perfil do Chrome do `verificar.mjs` agora fica em `web/scripts/_chrome-perfil` — no
  TEMP do C: (que vive no limite nesta máquina) o Chrome falha com erro de PROTOCOLO em pontos
  diferentes a cada rodada, não com "disco cheio", e isso se lê como teste instável.

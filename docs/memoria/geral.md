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

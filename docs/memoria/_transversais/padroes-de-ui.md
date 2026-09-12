# Padrões de UI

> Extraído do CLAUDE.md original (seções "O que já existe" e "Armadilhas já pagas").
> Consultar antes de mexer nesta área do sistema.

## O que já existe

- **Paginação**: as listas grandes devolvem o total em **`X-Total`** (via `count(*) OVER ()`,
  na mesma varredura) e o front usa `api.listar()`. ⚠️ O header precisa estar em
  `expose_headers` do CORS, senão o navegador não o entrega à tela.

- 🔑 **A janela (`Modal`) era do tamanho do CONTEÚDO, e conteúdo longo saía da tela sem
  rolagem nenhuma** (29/08/2026). A de exportação, com cinco filtros, passava de mil pixels:
  num notebook os últimos campos e o botão de baixar ficavam fora, **e não havia barra de
  rolagem em lugar nenhum** — porque `Modal` trava o `overflow` do corpo da página enquanto
  está aberta. O defeito era do componente, não daquela tela: valia para toda janela do
  sistema, e só apareceu quando uma delas cresceu.
  Agora o cartão é limitado pela altura da JANELA (`max-h-[calc(100dvh-4rem)]`), vira
  `flex-col`, e só o miolo rola (`min-h-0 flex-1 overflow-y-auto` — sem o `min-h-0` um filho
  de flex não encolhe abaixo do próprio conteúdo, e o `overflow` não teria o que rolar).
  ⚠️ **`dvh`, não `vh`**: no celular a barra de endereço entra na conta do `vh`, e o pé do
  cartão fica atrás dela.
  ⚠️ **`Modal` ganhou `rodape`**, que fica FORA da rolagem: botão de ação que rolou para fora
  da vista é botão que não existe, e quem não o acha conclui que a janela não tem saída. A
  contagem da prévia fica ao lado dele porque é o número que se olha imediatamente antes de
  clicar.
  ⚠️ **A bateria rodava a 1440×1000 e não pegaria isso.** A checagem nova MEDE numa tela de
  notebook de verdade (1440×760) e devolve o tamanho depois — altura generosa demais no teste
  esconde exatamente a classe de defeito que o teste existe para achar.

- **Aviso de ação flutua** (`components/aviso-flutuante.tsx`, 20/08/2026): sucesso e erro de
  AÇÃO saem por `useAviso()` e aparecem presos ao canto inferior — a mensagem ficava no topo e
  o botão de salvar está no fim de um formulário longo, então quem clicava não via confirmação
  nenhuma e clicava de novo. Sucesso some em 6 s; **erro fica até fecharem**. O aviso pode levar
  UMA ação ("cadastrar outro"), que é a resposta ao "cadastrei, e agora?".
  ⚠️ **Os dois somem sozinhos** (26/08/2026): sucesso em 6 s, erro em 14 — a frase do erro é
  mais longa. Antes o erro ficava até alguém fechar, e uma pilha que não se limpa acaba tapando
  a tela em uso. O que torna isso seguro é o aviso **parar de contar enquanto o ponteiro está
  em cima** (ou o foco dentro): o medo real era a mensagem sumir no meio da leitura. A barrinha
  embaixo mostra quanto falta — sem ela, o aviso sumindo parece a tela piscando.
  ⚠️ Erro de **carregamento** continua inline no cartão (é ele que explica a tela vazia) — a
  regra de bolso: mensagem com "Falha ao carregar" fica; o resto flutua.

- 🔑 **`localStorage` está VAZIO até alguém mexer no seletor de loja** (31/08/2026), e a tela da
  remessa foi a primeira a DECIDIR com base nele: `Number(unidadeAtual() || 0)` dava **zero**
  para quem nunca trocou de loja — que é a maioria —, e aí nem o botão de receber nem o de
  cancelar apareciam. Quem abrisse a própria remessa não tinha o que fazer com ela. O layout
  disfarçava o buraco porque só usava o valor para MARCAR a opção do `<select>`, com
  `?? eu.unidades[0].id` na frente.
  ⚠️ A resposta mora em `useSessao().unidade` e **espelha `seguranca.unidade_atual` passo a
  passo**: a escolhida no seletor, senão a matriz para quem enxerga todas, senão a de menor id.
  "O primeiro da lista" como reserva NÃO é o padrão do servidor quando a matriz não é a de
  menor id — o seletor mostraria uma loja e o pedido iria para outra.
  ⚠️ Ler `localStorage` no render é seguro **ali** porque `eu` nasce nulo: a primeira pintura do
  cliente é igual à do servidor, e o valor só aparece depois do `/auth/me`.

- 🔑 **4px de raio é canto vivo disfarçado** (30/08/2026). A tela é feita de caixas, e num
  raio tão curto nenhuma tem forma perceptível — só borda. `.cartao` foi para **14px** com
  **sombra dupla**: uma linha de 1px logo abaixo, que separa do papel, e um halo largo e
  claríssimo, que dá a altura. Sombra única e escura é o que faz uma tela parecer de 2012.
  Botão e campo foram para 9px — canto vivo dentro de cartão redondo são duas linguagens na
  mesma tela, e a mais dura é a que se nota.
  🔑 **E o aviso não era um balão, era uma LINHA**: barra de 2px à esquerda com o texto solto
  no fundo da página, lendo como mais um parágrafo com a cor trocada. Virou `.aviso` +
  `.aviso-{info,ok,erro}` — fundo tingido, borda da mesma família, 12px de canto. Entraram os
  tokens que faltavam (`--color-erro-claro`, `--color-alerta-claro`); o `erva-claro` já
  existia e servia só ao verde. ⚠️ A forma mora no CSS, não em oito utilitárias repetidas no
  componente: o aviso aparece em quase toda tela, e um balão diferente por página seria a
  primeira coisa a divergir.

- 🔑 **O banco declara TRÊS famílias de número, e a tela mostrava tudo como uma**
  (`lib/numeros.ts`, 10/09/2026, pedido do dono). Não é questão de gosto — está na escala
  das colunas: **valor** somável é `numeric(18,2)` (`custo_total`, `valor_total`,
  `preco_venda`), **custo unitário** é `numeric(18,6)` (`custo_unitario`, `custo_medio`,
  `ultimo_preco`, `custo_referencia`, `custo_ficha_unitario`) e **quantidade** é
  `numeric(18,4)`. O front achatava as três em duas casas.
  🔑 **`custo()` não inventa casa: para de esconder a que existe.** Medido na base: **846
  produtos** têm `custo_referencia` com dígito além da segunda casa e **128 saldos** têm
  `custo_medio` assim. Um adesivo a R$ 0,169020 aparecia como **R$ 0,17** — 0,6% de erro que
  reaparece multiplicado na ficha, exatamente o que `CASAS_CUSTO` existe para não deixar
  acontecer. Quem custa R$ 20,00 continua "R$ 20,00": o mínimo é duas casas e o Intl apara o
  zero à direita sozinho, então só quem tem fração aparece maior.
  ⚠️ **Valor continua em DUAS, e essa é a metade que não muda.** Na mesma linha de Saldos
  convivem "R$ 0,16902" (custo médio) e "-R$ 0,51" (valor em estoque) — famílias diferentes,
  precisões diferentes, de propósito. Trocar a segunda por seis casas seria inventar centavo
  que não existe numa conta que se soma.
  ⚠️ **`qtd` estava definido OITO vezes** — três casas em cinco arquivos, quatro em três — e
  `pct`, quatro. O mesmo saldo escrito de dois jeitos conforme a tela. Divergência assim não
  se acha lendo o código: acha-se quando alguém confere duas telas e conclui que uma delas
  mente. Agora `reais`, `custo`, `qtd`, `pct` e `inteiro` moram em `lib/numeros.ts`;
  `lib/cadastros.ts` reexporta `reais` porque trinta e cinco telas já o pedem de lá.
  ⚠️ **Quatro telas ficaram para trás naquela varredura, e foram fechadas em 12/09/2026**:
  Produção (duas quantidades com três casas fixas), a ficha (a quantidade que a receita tira
  do estoque, quatro casas), a remessa de transferência (um `numero` local, quatro casas) e o
  Vendas do dia (uma cópia de `inteiro`). As três primeiras **ignoravam o `casas_decimais_qtd`
  da loja** — mexer no ajuste não mudava nada nelas, que é o mesmo defeito que o ajuste tinha
  antes de ser ligado. ⚠️ Sobra uma, de propósito: o `fc` da ficha
  (`qtd_bruta / qtd_liquida`, `toFixed(3)`) é FATOR, não quantidade — não tem unidade e não é
  o que a loja configura.
  ⚠️ A variação do relatório do dono continua local, e está certo: ela leva **sinal**
  ("+3,2%" e "3,2%" dizem coisas diferentes) — só o "+" é dela, as casas vêm da casa.
  ⚠️ Ponteiro: a mesma régua valia para o PDF, que truncava em três casas —
  [`exportacao-e-relatorios.md`](exportacao-e-relatorios.md).
  🔑 **E dois dias depois a TELA voltou para duas casas** (12/09/2026, pedido do dono):
  `custo()` passou a ser `reais()` e todo dinheiro aparece com duas casas em toda tela —
  Saldos, Fichas, Produção, CMV, Compras, Ajustes, Produto > Custo, as trinta e poucas. O
  que se viu com as seis ligadas foi que a precisão aparecia onde ninguém a estava
  procurando: "R$ 0,169020" numa coluna de preços cansa a leitura de uma lista inteira para
  servir a uma conferência que se faz uma vez. ⚠️ **A precisão não sumiu, mudou de lugar**:
  o banco, a conta do servidor, o campo `CampoCusto` (que continua com seis, porque ele
  GRAVA) e a exportação — CSV e PDF seguem na escala da coluna, e é lá que se confere
  dígito. ⚠️ **O nome `custo()` ficou de propósito**, mesmo idêntico a `reais()`: é o que
  mantém a régua da exibição num lugar só. Trocar as chamadas por `reais()` espalharia a
  decisão por trinta arquivos e tornaria a volta atrás impossível de fazer sem varredura.
  ⚠️ **O efeito colateral aceito**: uma linha de "10 × R$ 0,17 = R$ 1,69" passa a não
  fechar aos olhos de quem multiplicar a mão. É o preço da leitura limpa, e foi decidido
  sabendo disso.

- 🔑 **`window.location` MENTE por um tempo, e duas escritas na URL se apagavam**
  (`lib/estado-na-url.ts`, 12/09/2026, achado ao investigar a checagem "filtrar volta para a
  primeira página"). `router.replace` do App Router é navegação suave: vai ao servidor buscar
  a árvore e só então a barra de endereço muda. Entre pedir e aterrissar — dezenas de
  milissegundos em produção, bem mais no `next dev` — `window.location.search` ainda é a URL
  ANTIGA, e quem montar a query a partir dali escreve em cima de um estado já trocado.
  🔑 **O caso medido, e ele é do usuário**: na página 2 de qualquer lista, digitar no filtro.
  O reset de página (`usePaginacao`) escreve `p: null` na hora; a busca (`useEstadoNaUrl`)
  escreve 300 ms depois e lê a URL — que ainda dizia `p=2`. Resultado `?p=2&busca=...`:
  página 2 de um resultado de uma página só, **lista vazia, sem nada explicando**.
  ⚠️ **Digitando devagar passava; colando, nunca** — por isso as quatro reproduções manuais
  de 11/09 deram certo e a checagem foi julgada "espera errada". A bateria digita instantâneo,
  que é o mesmo que colar um código na busca: o caso mais real que existe.
  🔑 **A correção é de raiz: a base da próxima escrita é o DESTINO do que ainda está em voo**,
  não a barra de endereço. O módulo guarda `{partida, destino}` da última escrita que pediu;
  enquanto a URL for uma das duas pontas, é o destino que descreve o estado. Qualquer outra
  coisa (outra tela, o voltar do navegador, tempo demais) descarta o rascunho.
  ⚠️ **O voltar do navegador é o único caso ambíguo**: ele devolve a URL exatamente à
  `partida`, que é indistinguível de "ainda não aterrissou", e o rascunho reaplicaria o que a
  pessoa acabou de desfazer. Daí o prazo de validade de 2 s — folgado para um `replace`,
  curto para qualquer pessoa ler a tela e decidir voltar.
  ⚠️ Vale para as catorze listas, não só Produtos: a escrita é a mesma para todas. E não
  resolve só o par busca/página — resolve a CLASSE, que é o próximo par de escritores.

- 🔑 **`type="number"` não serve para dinheiro** (`CampoMoeda` em `components/ui.tsx`,
  10/09/2026, pedido do dono). Era o que o preço de venda do cadastro de produtos usava, e
  traz três defeitos que só aparecem com gente digitando: no teclado pt-BR a vírgula não entra
  em parte dos navegadores (quem digitava "12,50" gravava **12**), o campo aceita "1e5" e
  "1.2.3", e a setinha de incremento aparece em cima de um preço, onde não quer dizer nada.
  Agora os centavos entram primeiro, como em caixa de banco: "1234567" vira **12.345,67**.
  ⚠️ **O cursor mora no FIM — na mudança E no foco.** Sem isso os dígitos se espalham pelo
  meio do número: medido, com "18,99" no campo e o cursor na posição 1, digitar "5" e depois
  "7" dava **1.578,99**, com o 5 e o 7 separados pelos dígitos velhos. O valor cresce pela
  direita, então o fim é o único lugar onde o cursor faz sentido — e é o que faz "selecionar
  tudo e digitar" substituir de verdade.
  ⚠️ **O "R$" fica FORA do campo**, como prefixo: dentro do valor ele seria apagável, e
  apagá-lo não muda nada — controle que aceita clique e não faz nada é pior que controle
  nenhum.
  ⚠️ **`Number()` cru não lê o que a máscara escreve.** "1.234,56" vira `NaN`, e o ponto de
  milhar seria lido como decimal — quem salva usa `moedaParaNumero`, quem carrega usa
  `numeroParaMoeda`. Havia três lugares assim na tela do produto (o corpo do produto, o preço
  da loja e o botão "Salvar preço daqui").
  ⚠️ **A bateria do navegador comparava `Number(campo) === 218`** e passou a acusar a tela de
  não mostrar um preço que ela mostra. O campo é mascarado: a checagem certa é pelo texto,
  `"218,00"` — é o que a pessoa vê, e é o formato que a máscara promete.

- 🔑 **Todo campo de dinheiro do sistema virou campo de dinheiro — em DUAS famílias**
  (10/09/2026, pedido do dono). Aplicar o `CampoMoeda` em tudo teria sido um erro: três dos
  campos gravam em `numeric(18,6)` (`ajustes.custo_novo`, o custo unitário da entrada e o
  valor unitário da nota manual), e a máscara de centavos fixa DUAS casas — truncaria o custo
  na digitação, reintroduzindo pela porta da frente o defeito que a varredura acabou de tirar
  da exibição. E o modelo centavos-primeiro é impraticável com seis: R$ 12,50 exigiria teclar
  "12500000".
  Então são dois componentes com o mesmo desenho e réguas diferentes: **`CampoMoeda`**
  (mascarado, duas casas) em `fornecedores.pedido_minimo`, `vendas/lancar.valor_unitario`,
  desconto e acréscimo da linha da nota e frete/desconto/outros da nota; **`CampoCusto`**
  (digitação livre, normaliza no blur, até seis casas) nos três de custo unitário.
  ⚠️ **A escala da coluna é quem decide, não o rótulo.** `nota_itens.valor_unitario` é 6 e
  `venda_itens.valor_unitario` é 2 — mesmo nome, famílias diferentes. Conferir no schema antes
  de escolher o componente.
  ⚠️ **`CampoCusto` normaliza no BLUR, nunca a cada tecla**: normalizar enquanto se digita
  apagaria a vírgula recém-digitada antes de virem os centavos. E ele leva `aoSair`, porque a
  tela de ajustes pede a prévia ao servidor quando o campo perde o foco.
  ⚠️ **`numero()` da nota manual era `Number(t.replace(",", "."))`** e devolve `NaN` para
  "1.234,56" — com o `|| 0` na frente, isso virava um zero CALADO e o total da nota fechava
  errado sem nada acusando. Agora ele delega a `textoParaNumero`, que decide o ponto pelo
  contexto: havendo vírgula, o ponto só pode ser milhar; não havendo, é decimal (quem digita
  "1.5" quer 1,5).
  ⚠️ **A bateria do navegador achava campos por ÍNDICE** (`input[type=number]`), e trocar o
  tipo do campo fez `numEstoque[1]` virar `undefined` — a suíte morreu com `TypeError`, longe
  da causa. Índice de lista muda quando a tela muda; rótulo, não. Mesma lição que o campo de
  preço já tinha ensinado neste arquivo.

- 🔑 **`casas_decimais_qtd` era ajuste MORTO, e agora `qtd()` o lê** (10/09/2026, pedido do
  dono). Ele existia em `parametros` desde a migração 001, o modelo da API o aceitava e a tela
  de Lojas o oferecia para editar — e **ninguém o lia**. Quem mexesse ali não via número nenhum
  mudar. Ajuste que não faz nada é pior que ajuste inexistente: ensina que a tela mente.
  🔑 **Viaja no `/auth/me`, pela mesma porta e pela mesma razão do `enviar_ao_pdv`**: é ajuste
  da loja ATUAL, toda tela precisa dele, e o `/me` já é carregado uma vez. Rota própria custaria
  uma requisição por tela para um número que não muda.
  ⚠️ **`qtd()` guarda o valor numa variável de MÓDULO, e isso é seguro por duas garantias que
  já existiam**: o layout de `(app)` segura toda tela enquanto o `/auth/me` não responde
  (`if (carregando)`), e trocar de loja no seletor recarrega a página inteira, de propósito.
  Não há tela pintada com o valor velho — nem no servidor, que não renderiza nada de dentro de
  `(app)` antes da sessão. Um contexto de React obrigaria a trocar `qtd(x)` por `fmt.qtd(x)` em
  dez arquivos para resolver o que essas duas garantias já resolvem.
  ⚠️ **A ordem no `ProvedorSessao` importa**: `definirCasasQtd` antes do `setEu`, porque é o
  `setCarregando(false)` que libera a pintura — definir depois faria a primeira tela sair com o
  padrão e o número mudar sozinho na frente de quem olha.
  ⚠️ **Zero é escolha legítima e arredonda só a EXIBIÇÃO** — 2,1875 KG aparece como "2", e o
  razão continua com 2,1875 gravado. A tela de Lojas escreve "0 a 6"; é isso que isso quer
  dizer. E pedir 5 ou 6 não inventa dígito: `quantidade` é `numeric(18,4)`, então o teto real
  continua sendo quatro.
  ⚠️ **A checagem MEDE a tela, não a gravação.** Gravar o parâmetro sempre funcionou — era a
  leitura que não existia, e uma checagem de "salvou?" teria passado durante os meses em que o
  campo esteve morto. A bateria do navegador troca o ajuste para 4, 2 e 0 e lê a mesma linha de
  saldo; `smoke_fundacao` garante que o campo CHEGA no `/me`.

- 🔑 **Espera de teste por um dado que PODE já estar na tela não é espera** (11/09/2026, achado
  ao devolver a bateria ao verde depois de recomeçar a base). A checagem "filtrar volta para a
  primeira página" esperava por uma LINHA contendo a marca dos produtos daquela fase. Com
  milhares de produtos na base eles nunca caíam na página 2, então a condição só ficava
  verdadeira DEPOIS de o filtro valer — e a espera funcionava por acidente. Numa base
  recém-limpa, com menos de cem produtos, eles **já estão** na página 2: a condição nasce
  verdadeira, o `waitForFunction` volta na hora, e a medição lê a tela ainda NÃO filtrada —
  rodapé "51–94 de 94", total inalterado. A checagem acusava a paginação de um defeito que era
  da espera.
  🔑 **A espera certa é pelo EFEITO**: a URL carregando `busca=`, e depois todas as linhas
  batendo com o termo. O que se espera tem de ser algo que só existe DEPOIS do que se está
  medindo.
  ⚠️ **Custou quatro reproduções manuais que passaram** — página 2, com 50 por página, saindo e
  voltando de outra tela, e até com o perfil de Chrome da própria bateria. Todas certas, porque
  todas criavam a situação do zero. Quem resolveu foi instrumentar a bateria no ponto exato da
  falha: o diagnóstico mostrou `url=?pp=50&busca=…` e 10 linhas — ou seja, o produto funcionava
  e o acréscimo de 2,5 s da instrumentação já fazia a checagem passar.
  ⚠️ **A segunda falha da mesma rodada era a mesma família**: o guarda `produtos > 10` usava a
  contagem da LISTA de pessoas, que inclui produto inativo, enquanto o cartão pinta só os
  ATIVOS. Numa base grande os dois números nunca se separavam; numa limpa, a pessoa aparece com
  doze e o cartão mostra sete, e a checagem cobrava um rodapé que não tinha o que paginar.
  ⚠️ **Base grande esconde defeito de teste.** Os dois passaram meses verdes porque o volume
  garantia por acaso o que a condição deveria garantir por construção.

## Armadilhas já pagas

- Componente `Aviso` renderiza `<p>`: não colocar dentro de outro `<p>` (erro de hidratação).

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

- 🔑 **"Guardar o que já tinha" pressupõe TER TIDO** (09/09/2026, relatado pelo dono: *"quando
  vou para a segunda ou terceira página adiante, ao entrar no produto e voltar para o grid, a
  parte de paginação some"*). Quem volta de um registro não teve: a tela é montada do ZERO. A
  página vem da URL (`?p=3`) — isso já funcionava —, mas o total não vem de lugar nenhum: a
  primeira busca já sai com `offset = 40`, o cabeçalho não vem por regra, o total fica em 0 e o
  rodapé se esconde inteiro. **E com ele some o caminho de volta para a página 2**: a lista fica
  presa naquela fatia, sem nada dizendo que existem outras.

  🔑 **A correção é `?com_total=1`**: quem não tem o total pede a contagem, mesmo fora da
  primeira página. **Quem sabe que precisa é o CLIENTE** — o servidor não tem como saber se
  aquela tela já viu o número antes —, e o custo só é pago quando falta, nunca a cada clique.

  ⚠️ **No backend o flag é lido por MIDDLEWARE** (`main._marcar_pedido_de_total` → um
  `ContextVar` que `paginacao.pagina` consulta), não por parâmetro de cada rota. São oito
  chamadas de `pagina()` em cinco routers; um parâmetro por endpoint seriam dezesseis lugares
  para acertar, e **a lista NOVA nasceria sem** — com o mesmo defeito e sem nada avisando. É a
  armadilha da lista de campos que já comeu a `marca` e depois o `custo_referencia` na fusão.
  O `ContextVar` é devolvido no `finally`: sem isso uma listagem herdaria o pedido da anterior e
  a contagem cara voltaria a rodar em toda virada de página, sem ninguém ver.

  ⚠️ **No front o pedido sai de `p.parametros`**, que TODA lista espalha na query — uma linha
  conserta as catorze e a lista nova nasce consertada. Repetir a condição em cada tela seria
  repeti-la errado numa delas.

  ⚠️ **Isto não vale para o `fator_compra`.** Mudar o fator de conversão NÃO reescreve custo
  nenhum, e não é defeito: todo custo guardado já é por unidade de estoque (razão, último preço
  do fornecedor e `custo_referencia`), e o fator só converte a QUANTIDADE da próxima nota. Quem
  mexe em custo gravado é a troca de UNIDADE (`troca_de_unidade`), porque aí o denominador muda.

- ⚠️ **Nada de `window.prompt`/`confirm`**: é a caixa do NAVEGADOR — fonte de sistema, botão
  em inglês, sem espaço para explicar o que a ação faz. O que não se desfaz pergunta pelo
  `Confirmacao` de `components/ui.tsx`, e o número que a ação usa fica num campo **na linha**,
  à vista antes do clique. Aplicado em: estornar movimento (razão e ajustes), estornar nota,
  fechar contagem, fechar e reabrir mês, cancelar venda e produzir da agenda.
  ⚠️ **Confirmação só onde mexe no razão ou fecha período.** Lançar a nota NÃO pergunta — a
  tela inteira é a conferência (itens, custos e destinos à vista) e um diálogo no caminho
  comum treina a clicar sem ler. Cancelar linha da agenda também não: é plano, não é razão.
  Cada diálogo diz **o que a ação faz**, não só "tem certeza".

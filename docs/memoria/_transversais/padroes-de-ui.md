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

- 🔑 **Campo de equivalência pergunta do lado que a pessoa PENSA** (cartão de unidades do
  produto, 12/09/2026). Uma coluna "Quantos UN" com `0,02` embaixo não diz que 0,02 é o
  inverso de 50; a linha inteira — `1 UN = [50] G` — diz, com as duas siglas à vista. Quem
  digita um fator invertido não erra por desatenção: erra porque a pergunta estava do lado
  contrário do que a cozinha sabe. ⚠️ A regra de quando virar é da grandeza das unidades, não
  do rótulo — a decisão e o caso do ovo estão em
  [`cadastros.md`](../cadastros.md).

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

- 🔑 **O período não é sempre "o mês", e o texto das telas dizia que era** (14/09/2026,
  relatado pelo dono: *"nas telas quando trata de período, sempre cita mês, mas caso o
  período for semanal, a descrição está errada — o CMV não é o mês que conta, e sim o
  período"*).
  🔑 **O NÚMERO já vinha certo**: o painel calcula por `periodos.periodo_do_dia`, que
  respeita o `ciclo_fechamento` da loja. Era só o texto ao redor dele — "o CMV do mês",
  "Perdas do mês", "o número deste mês" — que dizia mês numa casa que fecha toda semana.
  🔑 **As palavras passaram a vir do SERVIDOR** (`periodos.termos`), e isso não foi escolha
  nova: é o precedente que a própria tela de CMV já tinha escrito no comentário do
  fechamento — *"o nome do período vem do servidor. Ele é o único que sabe se '01/08' é o
  mês de agosto ou a semana que começou nele; remontar a frase aqui daria duas versões da
  mesma verdade."*
  ⚠️ **São QUATRO formas porque o português precisa das quatro**: "mês" e "dia" são
  masculinos, "semana" é feminina, e as preposições contraem (do/da, deste/desta,
  neste/nesta). Mandar só o substantivo obrigaria a tela a montar a contração — que é
  exatamente a segunda versão da verdade que o comentário acima recusa.
  ⚠️ **O `response_model` cortou o campo de novo.** `ApuracaoResponse` recorta o que não
  está nela, e `termos` sairia do serviço sem chegar à tela — calado. O aviso disso já
  estava escrito no mesmo arquivo, quatro linhas acima, no `ajuste_custo`. **Segunda vez
  nesta sessão** que a armadilha pega (a primeira foi `reservas_ligado` em `MeResponse`).
  ⚠️ **Três frases ficaram NEUTRAS em vez de seguirem o ciclo**, e ficaram melhores:
  "descobrir tarde demais" (alertas), "período fechado" (duplicados) e "não reescreve o que
  já passou" (vendas). Nem toda frase precisa do ciclo — algumas só precisavam parar de
  falar em mês.

- 🔑 **O layout passou por uma revisão medida contra a norma** (14/09/2026, pedido do dono:
  *"mais amigável e mais compatibilidade com as normas de UX… letras amigáveis e bonitas…
  a funcionalidade mais simples no dia a dia, tanto para computador quanto para celular"*).
  O estudo está em [`docs/ux-estudo.md`](../../ux-estudo.md), com o protótipo do antes e
  depois em `apresentacao/ux-prototipo.html`.

  🔑 **A tipografia se dividiu por FUNÇÃO.** `Newsreader` era o padrão do `body` e com isso
  carregava as CÉLULAS das tabelas: vinte linhas de nome de produto em serifada, negrito e
  sublinhado — e os nomes chegam do Omie em CAIXA ALTA, que é uma quarta ênfase. Agora o
  corpo é `Inter` e a serifada virou **opt-in** (`.prosa`), aplicada aos 52 parágrafos que
  explicam cada tela e à descrição de todo cartão. ⚠️ Título, campo e botão **já eram**
  Bricolage — o estudo tinha simplificado isso, e só ao aplicar ficou claro.

  🔑 **Três cores estavam fora da norma, e a primeira correção também estava.** `alerta`
  dava 4,06 (e pinta a etiqueta "rascunho", de 11px — a cor mais fraca no texto menor),
  `latao` 4,44, e a borda dos campos **1,69** contra os 3,0 da WCAG 1.4.11.
  ⚠️ **A borda foi corrigida DUAS vezes**: `#9aa78e` ainda dava 2,48, e quem avisou foi a
  guarda da bateria, não o olho. A cor final (`#748069`) dá 4,09 sobre o cartão e 3,25
  sobre o papel — os dois fundos em que um campo aparece.
  🔑 **E isso revelou que uma cor fazia dois trabalhos opostos**: `linha2` pintava a borda
  dos controles E o sublinhado do nome do registro. A borda precisa de contraste; o
  sublinhado aparece vinte vezes seguidas e precisa sumir de tão presente. Nasceu
  `--color-sublinhado`.

  🔑 **`.campo` foi para 16px em toda a casa.** A regra já estava escrita no próprio CSS, no
  `.campo-toque` — *"abaixo disso o Safari do iPhone dá zoom ao focar"* —, mas era opt-in e
  estava aplicada praticamente só na contagem de inventário. Nota, produto, ficha e reserva
  saltavam no celular do mesmo jeito.

  🔑 **Coluna vazia não custa largura — e a regra é do DADO.** Na lista de produtos,
  categoria, setor, unidade e preço vinham em branco em quase toda linha: cinco colunas de
  travessão comendo 40% da tela. Agora a coluna some quando está vazia em TODA a página e
  **volta sozinha** quando houver valor. ⚠️ Arrancá-las de vez seria otimizar para o resíduo
  da importação do Omie, que é passageiro.

  🔑 **No celular, as telas do dia a dia a um toque** (`components/barra-navegacao.tsx`).
  Trocar de tela eram cinco gestos (☰, esperar, achar o grupo, abrir, tocar) — e o efeito
  disso não é reclamação, é a pessoa parar de conferir o estoque no salão. ⚠️ Ela fica
  ACIMA do rodapé da versão, que continua existindo: aquele número é o que separa *"a
  correção não funcionou"* de *"a correção não foi publicada"*. ⚠️ E a folga do `main` subiu
  para `pb-28` no celular — com duas barras fixas, o último botão do formulário nasceria
  embaixo da navegação, e o defeito só apareceria no telefone.

  ### ⚠️ Quatro checagens que eu escrevi afirmando sem medir

  Vale mais que o defeito, porque é o padrão: **a fase nova produziu quatro checagens que
  não mediam o que diziam medir** — e o produto estava certo nas quatro.

  - **Renomear identificador não é substituir texto.** `barra` colidia com outra variável e
    o replace CEGO trocou também dentro das strings: a bateria passou a procurar
    `#barraDia-navegacao`, que nunca existiu. Quatro checagens falharam por duas rodadas
    acusando um componente correto, enquanto uma sonda isolada achava a barra na hora.
  - **`!== false` não é `=== true`.** Com a barra ausente o campo nunca era calculado, e
    `undefined !== false` é verdadeiro: a checagem passava exatamente nas rodadas em que as
    outras falhavam.
  - **Aceitar `"ausente"` é aceitar o estado da falha.** A checagem do computador dava por
    boa a mesma ausência que reprovava no celular.
  - **Medir elemento invisível dá zero.** A sonda pegava o primeiro `.link-acao` do DOM sem
    olhar se estava renderizado, e reprovava o alvo de toque por altura zero.

  E a precondição: medir a barra numa página que a fase anterior tinha deixado **fora do
  app** (a tela de sem-conexão do PWA) dava "ausente" e acusava o componente.

- 🔑 **O cabeçalho de tela virou componente, e o título ganhou definição**
  (`components/cabecalho-tela.tsx`, 14/09/2026).
  🔑 **Ele nasceu porque não existia**: as 55 telas repetiam a marcação na mão, e o
  resultado eram **oito classes diferentes para o mesmo `<h1>`** — `text-[26px]`,
  `text-[24px]`, `text-[30px]`, com e sem `leading-tight`, com e sem `break-words`. Não é
  desleixo: é o que sempre acontece quando a mesma peça é copiada em vez de compartilhada.
  ⚠️ **E `.titulo` era referenciada por três telas sem nunca ter sido definida** — elas
  renderizavam por acidente, caindo no estilo base do `h1`. O mesmo problema visto do outro
  lado: sem definição única, metade inventa a sua e a outra metade aponta para o vazio.
  Agora ela existe, com o tamanho da maioria, para a mudança não redesenhar tela nenhuma.
  ⚠️ **A frase explicativa é num nó de DOM só**: renderizar duas versões e esconder uma por
  breakpoint faria o leitor de tela ler a frase duas vezes.
  ⚠️ **Convertidas 4 das 55**, e de propósito: as demais têm variações que pedem olho, e
  afrouxar a regex sobre 55 arquivos é como edição mecânica dá errado.
  🔑 **Em 15/09/2026 o dono relatou que "em algumas telas o cabecalho falhou, por exemplo no
  painel do CMV" — e eram DOIS defeitos no mesmo lugar.**
  ⚠️ **O primeiro: a coluna do título era `min-w-0 flex-1`, e isso a deixa encolher até o
  nada.** O bloco de ações do CMV tem cinco controles (dois campos de data, o seletor de
  período e dois botões); o flex cedeu tudo para eles e o `<h1>` ficou com **2px de largura
  por 1.613px de altura** — uma letra por linha — em vez de a linha quebrar em duas. Com um
  piso (`min-w-[15rem]`) as ações descem para a própria linha quando não cabem ao lado, que
  era o comportamento esperado desde sempre. ⚠️ A bateria mede isso no CMV de propósito: é a
  tela com o maior bloco de ações do sistema, então é a que quebra primeiro.
  🔑 **E no mesmo dia ela foi para TODAS as telas** (*"colocar este saber mais em todas as
  telas que tenham o texto"*): a disciplina virou `components/explica-tela.tsx`, e as **35
  telas que montam o cabeçalho na mão** passaram a usá-la — se o controle só existisse nas 4
  que usam `CabecalhoTela`, a mesma frase apareceria de dois jeitos conforme a rota.
  ⚠️ **Cinco telas ficaram de fora, e é a parte que exige juízo:** a linha cinza abaixo do
  título que mostra o **e-mail do usuário**, o **período da conta**, a **origem da venda**, as
  **lojas de origem e destino** da remessa e o **nome de quem consome** tem exatamente a mesma
  cara da frase explicativa — e esconder o ASSUNTO da tela atrás de "saber mais" teria sido a
  leitura mecânica do pedido. A bateria guarda uma delas (`/consumo/{id}`), porque a próxima
  varredura mecânica vai encontrá-las de novo.
  ⚠️ **O `/cadastros` era o caso duvidoso** — a frase dele lista o que a tela tem dentro
  ("Setores, locais de estoque, categorias e unidades de medida"), e existia justamente porque
  "tabelas de apoio" não é o nome de nada que alguém procura. Ela foi recolhida assim mesmo
  porque **as ABAS logo abaixo nomeiam as quatro listas**: o que ficou escondido foi a lição,
  não a lista.
  ⚠️ **O segundo: a frase explicativa só se escondia no celular.** No computador ela custava
  duas linhas em toda tela, todo dia, para dizer o que quem trabalha na casa já sabe — e o
  estudo de layout já havia proposto recolhê-la (*"ela ensina na primeira semana e estorva na
  terceira"*). Agora vem fechada nos dois tamanhos, atrás de um **"saber mais"** que o mesmo
  controle fecha de volta ("ocultar"): botão que só sabe abrir deixa a tela no estado de que
  se estava saindo.

- 🔑 **O convite de instalar o app empurrava a página inteira 78px, TARDE** (14/09/2026).
  Ele vinha no topo do `main` e aparece quando o navegador dispara `beforeinstallprompt` —
  ou seja, depois de a página já estar sendo lida. Quem estava prestes a clicar numa linha
  clicava noutra.
  🔑 **Quem expôs foi a bateria, e por um caminho torto**: a checagem da rolagem ao virar de
  página começou a falhar depois de o cabeçalho encolher. A conclusão fácil — *"encurtei a
  página, a conta desregulou"* — estava errada. A sonda mostrou um elemento de 78px
  nascendo acima da lista DEPOIS de a rolagem ter sido calculada. ⚠️ E mostrou números
  diferentes a cada rodada (-8 numa, 169 noutra): **valor instável na mesma falha é a pista
  de que a causa é temporização, não cálculo.**
  ⚠️ **A correção foi no convite, não na tolerância do teste.** Ele foi para DEPOIS do
  conteúdo, onde não há nada abaixo para empurrar — e nenhuma linha de teste mudou, que é o
  sinal de que a correção acertou o lugar. Afrouxar a tolerância teria deixado a checagem
  verde e o defeito esperando para morder alguém no celular.

- 🔑 **O menu virou navegação, e não índice de livro** (15/09/2026, pedido do dono: *"pensando
  em layout, gostaria de um menu mais moderno"*). O diagnóstico não foi "está feio": a lateral
  levava a **25 telas em 6 grupos, todos recolhidos**, e mostrava **seis linhas numa coluna de
  900px** — cerca de 85% dela sem uso — enquanto **toda navegação custava dois cliques**. Ou
  seja: **o menu trocava espaço vertical que não usava por cliques que cobrava.**
  🔑 **A regra dos grupos recolhidos NÃO foi desfeita** — ela continua certa (sem ela, em dez
  minutos estão todos abertos e a lista não cabe na altura da tela). O que mudou foi tornar a
  árvore desnecessária para quem já sabe para onde vai. Três movimentos, nesta ordem de valor:
  * **Busca de telas com `Ctrl+K`** (`components/paleta-telas.tsx`): digita "invent", Enter,
    chegou — **zero cliques**. É a resposta moderna para 25 destinos.
  * **Atalhos fixados** (`lib/atalhos.ts`), no espaço que já estava vazio: a cozinha não abre
    as mesmas telas que o escritório, e o menu não sabia disso. Alfinete em cada linha, teto
    de cinco, guardados no navegador como a preferência de grupo aberto já era.
  * **Ícone em cada item e em cada grupo** (`lib/icones.ts`, 26 traçados próprios): era texto
    puro em MAIÚSCULAS de 11px, que lê como legenda de seção, não como navegação. O título de
    grupo desceu para caixa normal de 13,5px — o pedido de "letras amigáveis" onde ele mais
    aparece. ⚠️ **Nada de biblioteca de ícones**: uma fonte inteira para 26 desenhos é peso de
    download e uma dependência externa envelhecendo sozinha no meio da navegação.
  🔑 **Grupo que sobra com UM item vira item** (`montarMenu`): abrir uma pasta com um papel
  dentro é um clique que não compra nada. Vale para Compras, que nasce com um item só — e,
  mais importante, para quem tem permissão de UMA tela dentro de um grupo de seis.
  🔑 **A lista de telas saiu do `layout.tsx` para `lib/menu.ts`**, porque passou a servir a
  três peças (menu, busca e atalhos). ⚠️ **Lista de navegação duplicada é lista que diverge**:
  a tela nova entra numa e não na outra, e a busca vira uma coisa em que não se confia. Por
  isso a bateria prova, na sessão da COZINHA, que a busca não oferece "Empresa" — uma segunda
  lista seria o caminho natural para esse defeito nascer.
  ⚠️ **O alfinete é IRMÃO do link, nunca filho.** `<button>` dentro de `<a>` é HTML inválido:
  o navegador desmancha a árvore em silêncio e o leitor de tela anuncia um controle dentro do
  outro. A checagem `aside a button === 0` existe para isso.
  ⚠️ **Os atalhos são lidos no INICIALIZADOR do estado, não num `useEffect`** — e isso só é
  seguro porque o menu monta depois do `/auth/me` (a casca devolve `null` sem `eu`), então ele
  nunca participa da hidratação. Num efeito, eles apareceriam um quadro depois e empurrariam
  os grupos para baixo: exatamente o defeito do convite de instalação, logo acima nesta lista.
  ⚠️ **A busca não abre por cima de uma janela** (`haJanelaAberta()`, exportado de `ui.tsx`):
  com a janela de vincular produto aberta, um `Ctrl+K` distraído navegaria para outra tela e
  levaria junto o trabalho de dentro dela.
  ⚠️ **`.menu-raiz` deixou de existir.** Ela era o Início escrito como título de grupo, para
  ele não parecer um filho solto no topo; com ícone e sem indentação, a linha comum já diz o
  nível. ⚠️ E a barra do celular trocou os glifos de texto (◈ ▤ ❏ ☷) pelos mesmos ícones do
  menu — o Estoque da barra não parecia o Estoque da lateral, que é justamente a associação
  que a barra existe para criar.
  ⚠️ **E a bateria passou a rodar SEM cache de navegador** — descoberto ao mudar a largura da
  lateral. O perfil do Chrome é reaproveitado entre rodadas e, em desenvolvimento, o Next serve
  a folha de estilo sempre na MESMA URL enquanto o conteúdo dela muda: a rodada carregava o CSS
  da rodada anterior. Sem a classe nova, a grade virou UMA coluna, o menu (sticky, 100vh) passou
  a cobrir o conteúdo, e o clique no "Criar produto" — nas coordenadas certas — caiu no item
  "Painel de CMV". **A bateria acusou o cadastro de produto, que estava intacto.** 🔑 A lição
  tem a forma das outras desta lista: *CSS velho não falha, ele mente* — e o sintoma aparece
  a três telas de distância da causa. ⚠️ A mesma ilusão passou pela minha própria medição: a
  primeira conferência de "nenhum nome cortado" deu verde porque a lateral estava com 1440px
  de largura, e não com 276.
  ⚠️ **E a lateral foi de 240px para 276** (relatado no mesmo dia: *"alguns itens cortaram a
  descrição"*). O ícone e o alfinete comem largura: sobravam ~169px para o texto, e "Saldos e
  movimentos", "Exportação para o PDV" e "Papéis e permissões" não cabiam. **Nome de tela
  cortado obriga a pessoa a adivinhar o destino, que é o contrário do que um menu faz** — e a
  bateria agora abre todos os grupos e compara `scrollWidth` com `clientWidth` de cada nome,
  porque essa conta muda sozinha quando alguém acrescenta um ícone ou uma tela de nome longo.
  Protótipo aprovado antes de qualquer código: [`apresentacao/menu-prototipo.html`](../../../apresentacao/menu-prototipo.html)
  (os dois menus lado a lado, com contador de cliques).

- 🔑 **As peças de formulário foram redesenhadas** (15/09/2026, protótipo aprovado pelo dono:
  [`apresentacao/pecas-prototipo.html`](../../../apresentacao/pecas-prototipo.html) — os dois
  desenhos sobre a MESMA marcação, com as medidas da norma calculadas ao vivo na página).
  🔑 **O erro do campo passou a EXISTIR.** Ele não tinha onde morar: saía no balão flutuante do
  canto — longe do campo que o causou, sumindo em 6 segundos —, e quem digitava "doze" lia
  "quantidade inválida" do outro lado da tela e voltava a procurar qual dos quatro campos era.
  Agora `Campo` recebe `erro` e põe `aria-invalid` + `aria-describedby` **no controle, por
  clonagem**. ⚠️ Deixar essa ligação a cargo de cada tela seria deixar a cor e o anúncio livres
  para discordar — a pior forma de acessibilidade é a que parece pronta.
  ⚠️ **O balão do canto continua, e continua certo**: ele é para o que é da TELA ("produto
  criado", "falha ao carregar"). O que mudou foi parar de usá-lo para o que é de um campo.
  🔑 **O rótulo saiu do `.rotulo`.** Ele era a mesma classe do olho de seção, do `<th>` e da
  legenda de cartão — 10,5px, mono, MAIÚSCULAS, cinza —, e num formulário isso lê como etiqueta
  de arquivo, não como a pergunta que o campo faz. Virou `.rotulo-campo` (13,5px, caixa normal,
  cor do texto) em **39 lugares**. ⚠️ `.rotulo` continua certo onde nasceu; o que mudou foi
  parar de pedir a ele um trabalho que não era dele. ⚠️ **A bateria tinha 23 sondas que achavam
  campo por `span.rotulo`** — todas passaram a aceitar as duas classes, porque a pergunta delas
  sempre foi "existe um campo chamado X?", não "de que classe ele é".
  🔑 **O botão desabilitado era `opacity: .55`, e esse era o pior número da paleta**: branco
  sobre verde a **2,65:1**. O botão não ficava inativo, ficava ilegível — quem enxerga pouco não
  conseguia ler o que não podia fazer. Com cor própria (fundo `superficie2`, texto `suave`) dá
  **4,82:1** e continua obviamente inerte.
  🔑 **O botão que trabalha agora DIZ que trabalha** — `aria-busy` em **88 botões** que já se
  desabilitavam, e um giro desenhado em CSS no `::before`. ⚠️ **Pelo atributo, não por uma
  classe**: `aria-busy` já é o que o leitor de tela anuncia, e uma classe a mais para dizer a
  mesma coisa é uma chance a mais de as duas discordarem. ⚠️ A varredura só marcou os nomes que
  significam trabalho (`ocupado`, `salvando`, `enviando`…) — `somenteLeitura` e `bloqueado`
  desabilitam por PERMISSÃO, e botão parado não é botão ocupado.
  🔑 **Quatro variantes de botão, e não duas**: `terciario` e `perigo` nasceram porque
  "estornar" e "excluir" eram LINKS DE TEXTO, com a mesma forma de "ver detalhes". ⚠️ O de
  perigo não é vermelho cheio: botão sólido vermelho atrai o clique justamente onde ele não
  deve ser atraído.
  ⚠️ **`.btn` teve de ir para `@layer components`** ao ganhar `display: inline-flex` (o gap
  entre o giro e o texto) — CSS sem camada vence a utilitária do Tailwind, e um `w-full` ou um
  `hidden` sobre um botão deixaria de valer. Efeito colateral bom: os cinco botões que
  escreviam `px-2.5 py-1` à mão viraram `.btn-pequeno`, que é a peça que faltava.
  ⚠️ **O `required` do navegador foi embora do cadastro de produto** (`noValidate` no `<form>`):
  ele mostra o balão cinza do Chrome — a mesma caixa que a casa já baniu do resto do sistema.
  A regra passou a ser nossa, a frase é nossa, e ela aparece embaixo do campo, com o foco indo
  para lá. O servidor continua sendo a guarda de verdade.
  ⚠️ **O interruptor (switch) do protótipo NÃO foi implementado, de propósito.** Ele promete
  efeito IMEDIATO, e todo booleano destas telas só vale depois do "Salvar" — um interruptor que
  não liga nada até alguém salvar é um controle que mente. A caixa de marcar está certa aqui.

- 🔑 **Aba é PERGUNTA, não gaveta — e o rótulo diz a pergunta** (16/09/2026, protótipo do
  painel de CMV aprovado pelo dono). A tela longa que empilha quatro listas obriga a rolar para
  descobrir o que existe; a mesma tela em abas responde "o que dá para perguntar aqui?" numa
  linha. O padrão é `<nav role="tablist">` com `<button role="tab" aria-selected>` e
  `min-h-[44px]` (dedo), borda inferior de 2px no ativo.
  ⚠️ **A aba só monta quando está aberta** (`{aba === "x" && <Componente/>}`): cada uma destas
  busca a própria rota, e montar as sete de uma vez faria sete chamadas para mostrar uma.
  ⚠️ **O rótulo acompanha o estado.** No CMV a aba se chama `Quebra por setor` e vira
  `Quebra por categoria` quando o eixo muda — aba que não acompanha mente sobre o que está na
  tela. A bateria cobra isso.
  ⚠️ **Decisão de RECORTE fica FORA das abas**, no cabeçalho: período, escopo e eixo valem para
  a tela inteira. Dentro de uma aba elas ficam escondidas de quem está em outra, e a pessoa
  muda o recorte sem saber que mudou o que as outras seis mostram.
  ⚠️ **A ordem da barra de filtros é a da leitura**: QUANDO (período pronto, depois datas
  soltas), ONDE (escopo, eixo) e só então o que fazer com isso (baixar, imprimir). Os botões
  vinham primeiro, e a pessoa escolhia o que baixar antes de escolher o que estava olhando.

- 🔑 **Gráfico de cinco retângulos se desenha à mão, em SVG** (`cmv/cascata.tsx`, 16/09/2026).
  Uma dependência de gráfico para isso pesaria mais que a tela inteira. ⚠️ **O `viewBox` reserva
  as bordas** para os rótulos de fora não serem cortados, e o `aria-label` traz a mesma conta em
  PALAVRAS — é o que o leitor de tela lê e é por onde a bateria prova que o desenho não saiu
  vazio. ⚠️ **O desenho não recalcula nada**: os valores vêm prontos da apuração. Um gráfico que
  soma por conta própria é a segunda versão da regra, e diverge na primeira correção.

- 🔑 **Filtro e botão na mesma fileira se confundem — o traço é o que separa** (16/09/2026,
  pedido do dono sobre o painel de CMV). Controle que muda o que a tela MOSTRA e botão que TIRA
  a tela de dentro do sistema são famílias diferentes, e alinhados com o mesmo `gap` eles leem
  como uma coisa só. O padrão é dois grupos num `flex`, o segundo com
  `border-l-2 border-linha2 pl-3`.
  ⚠️ **A cor é `linha2`, não `linha`.** Medido: `--color-linha` (#d8ded0) some contra o fundo
  do miolo — a classe estava no HTML e o traço simplesmente não aparecia.
  ⚠️ **E sem variante de breakpoint.** `sm:border-l`, `sm:border-linha2` e `sm:pl-4` não
  chegaram à folha (`border-left-width: 0px` no elemento medido, com 25 s de espera pelo
  rebuild), enquanto as mesmas utilitárias sem prefixo aplicam — inclusive uma inédita no
  projeto (`pl-5`), o que descarta "o Tailwind não regenera". Quando a fileira quebra, a
  barrinha abre a linha de baixo e continua dizendo "aqui começa outro grupo".
  ⚠️ **Nunca filtre elemento por `className.includes("border-l")`**: `border-linha2` contém
  esse pedaço. A checagem da bateria procura `border-l-2`.

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

- 🔑 **Imprimir a tela é um recurso de verdade, e o esqueleto atrapalhava** (16/09/2026). O
  padrão da casa é `window.print()` num botão marcado `nao-imprimir`, e `@media print` em
  `globals.css` some com menu, botões e o que for marcado. Só que o esqueleto do app é
  `lg:grid-cols-[276px_minmax(0,1fr)]`: **esconder o `aside` não tira a coluna dele**, e o
  conteúdo ia parar na faixa de 276px com as colunas da direita cortadas. Descoberto ao imprimir
  a folha da produção, onde sumia justamente a coluna "Total" — e **o papel não denuncia o corte
  como a tela denuncia, com a barra de rolagem**. A regra passou a desfazer a grade
  (`.esqueleto { display: block }`), soltar o `max-width` do miolo e tornar `.overflow-x-auto`
  visível.
  ⚠️ **`break-inside: avoid` no cartão inteiro é armadilha**: empurra lista longa para a página
  seguinte e corta quando ela não cabe em nenhuma. A unidade que não se parte é a LINHA
  (`.tabela tr`).
  ⚠️ **O que é dinheiro fica fora do papel quando a folha circula.** A da produção é passada de
  mão em mão na cozinha: o custo continua na tela, para quem tem a permissão, e sai da impressão.

- ⚠️ **`.campo` tem `width: 100%` FORA de camada, e ganha da utilitária do Tailwind.** Um
  `className="campo w-[92px]"` não estreita coisa nenhuma: medido, o campo ficou com os 326px da
  célula e a coluna virou a mais larga da tabela. A largura mora no **invólucro**
  (`<span className="block w-[96px]"><input className="campo …" /></span>`), que resolve pela
  cascata em vez de brigar com ela. ⚠️ O mesmo vale para `<select className="campo">`.

# Notas fiscais e Omie

> Extraído do CLAUDE.md original (seções "O que já existe" e "Armadilhas já pagas").
> Consultar antes de mexer nesta área do sistema.

## O que já existe

- **Cada nota tem endereço** (25/08/2026): `/compras` é só a LISTA, `/compras/nova` digita e
  `/compras/[id]` mostra — com **cabeçalho, itens e total**, no mesmo modelo do formulário de
  digitação. Antes as três coisas dividiam a mesma tela: o formulário empurrava as notas para
  fora do campo de visão, e a conferência mostrava os itens espremidos e **nunca somava o
  total** — quem conferia via as linhas e não via o número que se bate contra o papel do
  fornecedor. `/compras/[id]/editar` corrige a digitada (a correção também é longa demais para
  caber num cartão).

- **`services/nfe_xml.py`** + `routers/notas.py`: a casa opera **sem integração nenhuma**. A
  nota entra por três portas — XML da NF-e, digitação e Omie — e da gravação em diante o
  caminho é um só (conciliação → conversão → rateio → razão). Por isso o ciclo da nota
  (conferir, vincular, lançar, estornar) mora em `notas.py`, e `omie.py` ficou só com
  credencial, sincronização e catálogo. Nota digitada não tem chave da NF-e: a repetição se
  reconhece por fornecedor + número + série (índice único `ux_nota_manual`).
  ⚠️ **Só a nota MANUAL se edita** (`PUT /notas/{id}`), e só antes de lançar: a que veio do
  XML/Omie é o documento do fornecedor, e mudar valor ali faria o sistema divergir da nota
  fiscal sem rastro. Os itens são reescritos inteiros — nada virou movimento ainda, e casar
  linha a linha só abriria caminho para item órfão.

- 🔑 **As notas de compra estão em `produtos/recebimentonfe`, NÃO em `produtos/notaentrada`**
  (24/08/2026). O segundo é o lançamento manual de nota do Omie: na conta do cliente tinha
  **uma** nota, de 2024, enquanto o recebimento de NF-e tinha **3.670**. Quem olhasse só o
  primeiro concluiria que a casa não compra nada. A varredura usa `ListarRecebimentos` para os
  cabeçalhos e `ConsultarRecebimento` (por `nIdReceb`) para os itens — a lista **não traz item
  nenhum**, e o detalhe só é pedido para nota que ainda não existe aqui: pedir o de todas
  custaria meia hora e a conta bloqueada. Mapeador: `recebimento_de_nfe` / `item_do_recebimento`.

- 🔑 **A conferência de estoque com o Omie NUNCA funcionou até 27/08/2026 — e o modo simulado
  dizia que sim.** `GET /omie/conferencia` sempre voltou "Tag [PAGINA] não faz parte da
  estrutura"; cada recusa gastava cota. Três erros empilhados, e o segundo é o pior:
  1. **`ListarPosEstoque` tem um dialeto SÓ DELE** (`DIALETO_POSICAO`): aceita `nPagina`,
     **recusa** `nRegistrosPorPagina` e quer `nRegPorPagina`; responde `nTotPaginas`/
     `nTotRegistros`. São **três** dialetos, não dois — e a lição não é o número: é que **o
     dialeto é por CHAMADA, não por módulo**. Uma chamada com um registro só diz qual é.
  2. **O mapeador lia `cCodigo` como `codigo_omie`.** `cCodigo` é o código da CASA registrado no
     Omie ("104304"); `codigo_omie` guarda o id de lá (`nCodProd`, "7302593753"). Nunca casava —
     e o sintoma seria uma **lista vazia**, que se lê como "está tudo certo". Mesma família do
     erro que ligou REDBULL a LIMÃO TAITY: ler o identificador errado não dá erro em lugar nenhum.
  3. **A comparação olhava só o custo médio.** Saldo diferente com custo igual é o caso mais
     comum de todos — a entrada lançada de um lado só.
  ⚠️ **E a fixture tinha sido escrita a partir da suposição errada** (`pagina`, `cCodigo`), então
  o simulado confirmava a suposição de quem a escreveu. **Fixture que copia o que se imagina não
  testa nada.** Agora ela copia a forma real, lida da conta do cliente.
  ⚠️ A resposta virou **objeto**, não lista: `conferidos`, `sem_cadastro_aqui`, `divergentes` e
  `truncado`. Lista sozinha não distingue "nenhuma divergência" de "nenhum produto comparado", e
  a tela mostra o resumo ANTES da tabela por isso. Medido na conta real: **1.987 produtos em
  ~17 s** (10 páginas de 200).

- ⚠️ **O Omie tem DOIS dialetos de paginação** (`cliente.DIALETO_PADRAO` e `DIALETO_HUNGARO`).
  Os módulos antigos falam `pagina`/`registros_por_pagina`; o recebimento exige
  `nPagina`/`nRegistrosPorPagina` e recusa o outro com "Tag [PAGINA] não faz parte da
  estrutura". Cada chamada recusada gasta cota — e cota gasta bloqueia a conta.

- **`POST /notas/reconciliar`** passa a cascata de novo nos itens pendentes. Existe porque a
  ordem real é: chegam as notas, e só depois o cadastro fica pronto. Sem isso, item que não
  achou dono no dia da importação só sairia da fila na mão. Nota **lançada** não se mexe (os
  movimentos já estão no razão) e item ignorado fica ignorado.

- 🔑 **O `vTotalItem` do Omie JÁ TRAZ frete, IPI/ST e desconto rateados pelo emitente**
  (25/08/2026). Tratar isso como mercadoria e ratear as acessórias da nota por cima cobrava
  tudo DUAS vezes: numa conta real, R$ 74,44 a mais no razão e um queijo entrando 13,5% acima
  da nota. `mapeadores._acessorias_do_emitente` reconhece a sobra (`vTotalItem` − mercadoria
  líquida) e a transforma em acessória INFORMADA — a mesma regra que o XML já seguia: quando o
  emitente rateou, o rateio é dele e ninguém soma nada por cima. A mercadoria passou a ser
  **quantidade × preço**, nunca `vTotalItem`, e o desconto da NOTA guarda só o que não está
  nos itens (`vTotalDescontos` é a soma dos `vDesconto`). Migrações 024 e 025 consertam o que
  entrou antes; nota já lançada precisa de estorno + novo lançamento.

- **A busca das notas pode rodar sozinha** (`services/omie/agenda.py`, migração 033,
  26/08/2026): `MANUAL` (o padrão), `HORARIA` ou `DIARIA` numa hora escolhida, por loja, mais
  uma janela em dias opcional (nulo = a janela adaptativa de sempre). Nota que chega na sexta e
  ninguém busca até segunda é nota que não entrou no estoque — e o CMV do fim de semana sai com
  compra a menos.
  ⚠️ **O padrão é MANUAL e tem de continuar sendo.** Cada busca consome cota, e o Omie
  **bloqueia a integração inteira** de quem consome demais: ligar é decisão de quem paga a
  conta, não algo que uma migração liga sozinha. A tela avisa que "a cada hora" são 24 buscas
  por dia.
  ⚠️ **O relógio é `agenda_rodou_em`, não `ultima_sincronizacao`** — a segunda só avança quando
  alguma nota chega, e usá-la como relógio faria o agendador tentar de novo a cada minuto numa
  casa sem nota nova, que é a casa normal de domingo. Por isso ele avança **mesmo com erro**: o
  erro fica em `agenda_ultimo_erro`, à vista na tela, e a próxima tentativa é no horário
  seguinte. Repetir em cima de um bloqueio do Omie só o prolonga.
  ⚠️ A DIÁRIA dispara na hora escolhida **e só uma vez no dia**: sem a segunda condição ela
  rodaria a cada minuto durante os sessenta minutos daquela hora.
  ⚠️ **`pg_try_advisory_xact_lock` antes de olhar o relógio**: duas instâncias da API (ou o
  worker do `--reload` com um órfão) leriam a mesma linha vencida e gastariam cota em dobro.
  ⚠️ O laço vive no `lifespan` e sobe SEMPRE — quem decide é a configuração. Se ele só subisse
  havendo agenda, ligar exigiria reiniciar a API, e ninguém lembraria disso. A busca roda em
  `asyncio.to_thread`: o importador é síncrono e leva dezenas de segundos; no laço de eventos
  travaria a API inteira enquanto isso.

- ⚠️ **A janela da busca do Omie é adaptativa** (`importador.janela`): sem parâmetro, vai
  **desde a última sincronização com 7 dias de folga** — a folga existe porque nota emitida
  antes e lançada no Omie depois cairia fora se a janela começasse onde a anterior parou, e
  ninguém veria (o resultado seria "0 novas"). `desde=` faz a carga inicial do histórico;
  `dias=` fixa. O controle do que já veio continua sendo a **chave da NF-e**, nunca um
  marcador. `GET /omie/conferencia-notas` compara período a período e **nomeia** as notas que
  faltam — "0 novas" sozinho não distingue "nada mudou" de "passou batido".

- **`services/omie/`**: `cliente.py` (HTTP, paginação, back-off, modo simulado com fixtures),
  `mapeadores.py` (**o único arquivo que muda quando a credencial real chegar** — cada campo
  é lido por uma lista de nomes possíveis) e `importador.py` (de-para em cascata, rateio,
  conversão, lançamento).

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

- 🔑 **Nem toda rota do PDV responde um OBJETO — e isso derrubava o envio DEPOIS de gravar**
  (30/08/2026). `impressoras/update` devolve a STRING `"Registry updated successfully!"`, como
  o `delete` já fazia. O router fazia `resposta.get("id")` e levantava `AttributeError`:
  **500 com corpo vazio**, a alteração já feita do outro lado, a pendência continuando aberta
  e a tela só sabendo dizer que falhou. Clicar de novo repetia o ciclo.
  ⚠️ A nota da string já existia para o `delete` e o cliente HTTP já a tolerava — quem supunha
  o dicionário era o router, um lugar só, que a nota não alcançou.

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

- ⚠️ **O teste de navegador põe a integração em `simulado` e devolve o modo no fim.** Depois de
  o dono configurar a conta real, "Buscar no Omie" na suíte sincronizaria 3.670 notas de
  verdade — e a conta bloqueia quem consome demais. Trocar só o MODO não toca na credencial.
  O restauro é registrado em `aoTerminar` e roda no `finally` do roteiro: repor no fim do bloco
  não bastou, porque a suíte estourou no meio uma vez e deixou a integração em `simulado` — a
  busca do dono parou de trazer nota e nada explicava por quê. Mesma lição do
  `preservar_credenciais`.

- ⚠️ **Trabalhar na integração com a conta REAL configurada custa cota.** `POST
  /omie/importar-catalogo` varre os 2.189 produtos do cliente a cada chamada, e o Omie bloqueia
  quem consome demais. Antes de exercitar qualquer coisa do Omie: **conferir o modo** e pôr em
  `simulado` (só o MODO — a credencial fica onde está). Para descobrir que campos uma conta
  devolve de verdade, **uma** chamada com `registros_por_pagina: 1` responde tudo e não custa
  quase nada; adivinhar nome de campo e varrer o catálogo para conferir é o caminho caro.
  `preservar_credenciais()` repõe a linha inteira — credencial, modo e `ativa` —, então suíte
  que o chama devolve o modo sozinha.

- ⚠️ **`preservar_credenciais()` em `tests/comum.py`, registrado no `atexit`.** A suíte do Omie
  grava uma credencial de mentira na MESMA linha onde mora a real, e a API não devolve a chave
  em claro (é a regra que protege o segredo) — então perder a credencial do cliente é
  definitivo. Repor no fim do roteiro não bastava: a suíte estourou no meio uma vez, e foi
  assim que a chave real se perdeu. `atexit` repõe mesmo com traceback.

### Armadilhas já pagas

## Armadilhas já pagas

- ⚠️ **Suíte de navegador que quebra no MEIO deixa rastro que derruba a próxima.** A limpeza de
  notas roda no fim; uma quebra antes dela deixou uma nota manual órfã, e as rodadas seguintes
  falharam num ponto sem relação nenhuma com a causa. Antes de caçar bug numa suíte que
  começou a falhar sozinha, **procure a sobra da rodada anterior**.
  ⚠️ O perfil do Chrome do `verificar.mjs` agora fica em `web/scripts/_chrome-perfil` — no
  TEMP do C: (que vive no limite nesta máquina) o Chrome falha com erro de PROTOCOLO em pontos
  diferentes a cada rodada, não com "disco cheio", e isso se lê como teste instável.

- ⚠️ **E contagem somada da PÁGINA é a mesma mentira.** A tela de Compras somava `pendentes`
  das notas que tinham vindo na página carregada e chamava aquilo de "a fila da casa inteira" —
  verdade com 37 notas, mentira com 3.670: a pendente cai na página 4 e o botão "Reconciliar"
  simplesmente some, com a pendência continuando lá. A fila vem de `GET /notas/pendencias`, que
  é da casa inteira. Vale para todo número que resume uma lista paginada.

- ⚠️ **Lista sem total é lista mentirosa.** A tela de compras mostrava as 50 notas mais
  recentes de 3.670 e nada dizia que havia mais — a nota do mês passado simplesmente não
  existia. Toda listagem que pode crescer devolve o total em `X-Total` (helper único em
  `api/paginacao.py`) e ganha busca no SERVIDOR.

- ⚠️ **A prévia de custo da nota digitada divide pela quantidade EM ESTOQUE**, não pela da
  nota: mostrava R$ 20,60 por caixa onde o custo real era R$ 1,72 por unidade. A tela busca
  o fator em `/produtos/{id}/unidades` e diz "por UN" no número.

- **O local de estoque é do PRODUTO** (`produtos.id_local_padrao`, migração 017): uma nota traz
  congelado e seco na mesma folha, e um local por NOTA obrigaria a lançar duas vezes ou a
  aceitar o sorvete no estoque seco. O local da nota virou **reserva** — vale para o produto
  que ainda não tem um definido, e a tela da nota mostra o destino item a item antes de lançar
  (`local_destino`). Ordem no lançamento: local do produto → local passado no lançar → local da
  nota.

- Item de nota sem produto **não entra no estoque** e barra o lançamento da nota inteira.

- ⚠️ No XML da NF-e, `vFrete` **ausente** e `vFrete` igual a **zero** são coisas diferentes:
  zero é o emitente dizendo "neste item não há frete". Tratar zero como ausente joga o item no
  rateio por valor e cobra dele um frete que a nota não pôs. Se **algum** item traz o campo, o
  rateio é do emitente e os outros recebem zero — senão o frete entraria duas vezes.

- 🔑 **O cadastro vem ANTES da nota** (`importador.sincronizar_completo`, migração 053,
  03/09/2026, pedido do dono, espelhando o que o PDV já fazia). Produto criado no Omie hoje e
  comprado hoje ficava sem vínculo, ia para a fila de pendências e esperava alguém lembrar de
  clicar em "Importar catálogo" — um segundo botão que ninguém sabe que precisa apertar.
  🔑 **A lógica mora no SERVIÇO, não no router, porque há DOIS chamadores.** A primeira versão
  ficou só no endpoint, e o agendador chama `sincronizar` direto: a integração funcionaria pelo
  botão e não pela madrugada, sem nada explicando. É a mesma lição do relógio do cardápio.
  ⚠️ **Falhar no catálogo NÃO impede a busca de notas.** Nota não importada é compra faltando no
  estoque e no CMV; cadastro não sincronizado é um item que fica na fila mais um dia.
  ⚠️ **Aqui NÃO existe o "só criar, nunca alinhar" do PDV**, e a diferença é real: o `importar`
  do cardápio sobrescreve campo, então rodá-lo a cada busca desfaria calada a correção de quem
  arrumou a categoria de um prato à mão. O `_completar_produto` do Omie usa
  `coalesce(coluna, valor)` — preenche só o que está nulo. Reimportar não desfaz nada.
  ⚠️ **O catálogo custa ~115 s** contra a conta real (2.201 produtos, paginados), enquanto as
  notas sozinhas levam 4 s. Medido, não estimado — a estimativa inicial era de 15 a 30 s e estava
  errada por um fator de quatro. Por isso: a agenda faz o catálogo **uma vez por dia**
  (`integracoes.catalogo_em`), `?catalogo=false` pula o passo, e a tela avisa que a busca demora.
  ⚠️ **A agenda do Omie aceita frequência HORÁRIA** — sem a trava diária, a varredura de 2.201
  produtos rodaria vinte e quatro vezes por dia para achar os dois que nasceram.
  ⚠️ **O relógio é do AGENDADOR, não do botão**: quem clica está pedindo agora, não dispensando a
  passada da madrugada. Mesma correção que o `cardapio_em` do PDV já precisou.
  ⚠️ **A premissa de um teste caiu junto, e não se enfraqueceu o teste.** O bloco "sem produto,
  sem lançamento" dependia de a nota chegar antes de o produto existir; com o catálogo na frente,
  a fila esvazia. Aquela sincronização passou a usar `catalogo=false` (com o porquê escrito) e o
  caminho novo ganhou bloco próprio, o `8b`.
  ⚠️ **Achado à parte, não regressão:** um item de nota descrevendo café estava ligado a
  `LARANJA PERA KG`. A causa é a conta REUSAR códigos — o item traz `codigo_fornecedor` PRD00004
  e o catálogo atual diz que PRD00004 é laranja. O vínculo saiu do nível 1 da cascata
  (`codigos_externos`), que já existia. Se a conta recicla códigos, cada reciclagem vira um
  vínculo silencioso e errado numa nota antiga — vale uma investigação própria.

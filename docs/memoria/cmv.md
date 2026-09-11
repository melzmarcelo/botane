# CMV

> O painel do CMV: apuração, grupos, fechamento e memória de cálculo.
> Leia antes de mexer neste módulo.

## O que já existe

- **Movimentação do estoque por produto** (`cmv.movimentacao_por_produto`, migração 018,
  21/08/2026): estoque inicial, entradas, saídas e estoque final de cada produto — a conta que
  EXPLICA o CMV, que é uma linha só. Aba em `/cmv` e planilha em `/exportar/movimentacao.csv`.
  ⚠️ O saldo inicial e o final saem da **fotografia do razão** (`saldo_apos` ×
  `custo_medio_apos`), não de somar entradas menos saídas: a quantidade daria igual e o
  **valor** não, porque o médio muda a cada entrada. ⚠️ Entradas e saídas aqui são **todas**
  (produção, transferência e ajuste inclusive) — a soma que vira CMV continua sendo só a de
  compras; são perguntas diferentes.

- **`services/relatorios.py`** (19/08/2026): os dois relatórios do dono. `cmv_por_grupo`
  quebra a MESMA conta do CMV por setor ou categoria — **não é rateio**, e a soma dos grupos
  fecha com o CMV do período (o teste confere isso). Produto sem grupo aparece como "Sem
  setor" em vez de sumir na junção. `evolucao_de_preco` ordena pelo **impacto em reais**, não
  pelo percentual: 8% num item semanal dói mais que 60% num trimestral. Base é o **custo de
  aquisição** (frete dentro), não o valor de tabela.

- **O fechamento tem três ritmos** (`services/periodos.py`, migração 028, 25/08/2026):
  `MENSAL` (o padrão e o de sempre), `SEMANAL` (escolhendo o dia em que a semana fecha) e
  `DIARIO`. A casa que viu a apresentação fecha o CMV toda **semana** — mês é o ritmo do
  contador, e uma variância que só aparece no dia 30 chega tarde para virar decisão. Escolhe-se
  em `parametros.ciclo_fechamento` + `fechamento_dia_semana` (ISO: 1 = segunda, 7 = domingo).
  ⚠️ **A pergunta "que período é este dia?" é feita num lugar só.** O mês estava escrito por
  dentro de quatro: o fechamento, o painel de CMV, a tela inicial e a frase com que o razão
  recusa lançamento. Trocar o ritmo em um deles faria o sistema discordar de si mesmo.
  ⚠️ **`dia_fechamento_cmv` era campo MORTO** — estava na tela de Lojas e ninguém lia. Virou o
  dia em que o mês do CMV COMEÇA: 1 dá o mês do calendário (idêntico ao de antes), 26 dá o
  ciclo 26/07–25/08 de quem fecha junto com o fornecedor. Limitado a 28: dia 30 não existe em
  fevereiro, e período de tamanho variável não compara com o anterior.
  ⚠️ **Período que ainda não terminou não fecha.** A conferência antiga (`competencia > mês
  corrente`) deixava fechar o mês CORRENTE: no dia 25, congelar agosto travava os seis dias que
  ainda iam acontecer. O corte é `fim > hoje`, e não `>=`, porque o dia do fechamento pertence
  ao período que ele encerra — recusar o último dia deixaria a casa sempre um período atrasada.
  ⚠️ **Períodos fechados não se sobrepõem** (409 nomeando o outro): quem fechava por mês e passa
  a fechar por semana teria dois congelados dizendo coisas diferentes sobre os mesmos dias.
  ⚠️ `cmv_fechamentos.ciclo` entra na unicidade (`ux_fechamento_ciclo`) — sem ele a semana que
  começa no dia 1 colidiria com o mês que começa no dia 1, e o `ON CONFLICT` sobrescreveria um
  com o outro em silêncio.
  ⚠️ **O nome do período vem do SERVIDOR** (`periodos.rotulo`), nunca remontado no front: só a
  coluna `ciclo` sabe se "01/08" é o mês de agosto ou a semana que começou nele. E o nome curto
  ("agosto de 2026") só vale para o período INTEIRO — um recorte que para no dia 25 mostra as
  duas pontas, senão manda-se ao contador um pedaço achando que é o mês.
  ⚠️ A tela de Lojas mostra a prévia do calendário **pedindo ao servidor**
  (`GET /unidades/{id}/parametros/previa-fechamento`), com os valores do formulário e sem
  salvar: semana que fecha na quarta, mês que começa no 26 e dia corrido são três aritméticas,
  e uma segunda implementação em TypeScript divergiria no primeiro caso de borda — aparecendo
  como fechamento no período errado, que só se desfaz reabrindo.

- **A casa monta os próprios grupos do CMV, por TIPO de produto**
  (`services/cmv_grupos.py`, migração 029, 26/08/2026). O painel já mostrava Perdas, Consumo
  interno e Ajustes de inventário como linhas que EXPLICAM o número; faltava a pergunta que o
  dono faz olhando a nota do mês: **quanto disto não é comida?** Detergente, sacola e marmita
  entram no custo pela mesma porta dos insumos e somem no total. Tipo novo:
  **`MATERIAL_LIMPEZA`**. O grupo de exemplo ("Material de limpeza e embalagem" = EMBALAGEM +
  MATERIAL_LIMPEZA) nasce na migração — funcionalidade que não aparece é funcionalidade que
  ninguém procura —, e é editável e apagável como qualquer outro.
  ⚠️ **Um tipo só entra em UM grupo, e quem garante é o BANCO**: `tipo` é a chave primária de
  `cmv_grupo_tipos`. Conferir só na aplicação deixaria duas telas gravarem ao mesmo tempo — e o
  mesmo custo apareceria em dois grupos, com a soma dos grupos deixando de fechar com o CMV, que
  é justamente a propriedade que dá sentido ao corte (a suíte cobra a identidade).
  ⚠️ **O vínculo é com o TIPO, nunca com o produto.** Mudar a configuração reclassifica o
  passado inteiro sem tocar em cadastro nenhum; gravar o grupo no produto exigiria varrer o
  cadastro a cada mudança e deixaria para trás justamente os produtos antigos, que são os que
  têm histórico.
  ⚠️ **O grupo escolhe se entra no CMV real** (`considerar_no_cmv`, migração 032). Marcado, a
  linha EXPLICA o CMV — como Perdas: o custo já está no total e a linha diz quanto do total é
  aquilo. Desmarcado, o custo **sai da conta**, e é isso que separa comida de detergente no food
  cost, que é o percentual que vira decisão de cardápio.
  ⚠️ **Sair é sair das TRÊS pontas** — estoque inicial, compras e estoque final. Tirar só as
  compras deixaria o estoque de limpeza do começo e do fim na conta, e a diferença entre os dois
  viraria custo de comida do mesmo jeito, com sinal imprevisível. Saindo das três, a
  contribuição do grupo se anula por completo: a suíte cobra que o CMV caia **exatamente** o que
  o grupo valia, e que remarcar devolva o número.
  ⚠️ **O dinheiro NÃO some da tela**: o grupo continua no painel, dito "FORA do CMV real", e um
  aviso acima da conta nomeia o que ficou de fora. Gasto que desaparece da vista é gasto que
  ninguém controla — e quem compara com o mês passado precisa saber que a régua mudou.
  ⚠️ `tipos_fora_do_cmv` viaja na apuração e é uma **lista**: o router converte os valores para
  `float`, e `float(list)` derrubava a apuração inteira com 500. Campo novo que não seja número
  precisa entrar na exceção de `_float`.
  ⚠️ **Grupo configurado aparece no painel mesmo valendo zero**, ao contrário do relatório por
  grupo (que lista o que pesou): ali "não apareceu" é indistinguível de "não salvou". E na ordem
  que a casa definiu, não na do valor — linha que troca de lugar entre um período e outro é
  linha que ninguém acha.
  ⚠️ A conta é a MESMA de `relatorios.cmv_por_grupo` (`agrupar="grupo"`), não uma soma escrita à
  parte: painel e relatório mostram o número lado a lado. Configura-se em **Tabelas de apoio ▸
  Grupos do CMV**, sob a chave `cmv.grupos` — ver o painel e remontar a apuração da casa são
  coisas diferentes, e o Contador tem a primeira.

- **`services/cmv.py`**: `CMV real = estoque inicial + compras − estoque final`. O valor do
  estoque numa data sai do próprio razão (último movimento antes do corte já traz
  `saldo_apos` × `custo_medio_apos`) — não se recalcula série nenhuma.
  ⚠️ **Data de HOJE responde pelo `estoque_saldos`, não pelo razão.** Os dois dão o mesmo
  número (o saldo é a fotografia corrente, e o razão não aceita movimento no futuro), mas o
  caminho é outro: uma linha por produto e local contra um `DISTINCT ON` sobre tudo o que já
  aconteceu. Com 400.000 movimentos, **837 ms viraram zero** — e é o caso mais comum, porque
  todo mês aberto termina hoje. O atalho está em DOIS lugares (`valor_do_estoque` e a CTE
  `final` de `movimentacao_por_produto`) e `smoke_cmv` cobra que continuem concordando.
  Para data passada vale o índice `ix_mov_fotografia` (migração 027): apuração do mês de
  ~1.700 ms para **625 ms**, movimentação do mês aberto de 1.262 ms para **642 ms**.

- 🔑 **A MEMÓRIA DE CÁLCULO** (`services/memoria_calculo.py`, três relatórios novos,
  02/09/2026, pedido da contabilidade numa reunião). O sistema já dizia o **resultado** (a
  apuração, dez linhas) e já provava a **identidade** (a movimentação por produto, onde
  `inicial + entradas − saídas = final` fecha na própria planilha). Faltava o passo do meio:
  **os documentos que compõem cada linha**. Perguntado *"estes R$ X de compras, de quais notas
  são?"*, não havia resposta — era abrir Compras, filtrar o período e somar à mão.
  🔑 **E somar as notas à mão dá OUTRO número, de propósito** — este é o ponto que faria a
  reunião seguinte terminar mal. A linha "Compras" **não** é a soma dos totais das notas: ela
  soma os MOVIMENTOS de entrada (com frete, IPI e ST já rateados por item), **tira** os grupos
  fora do CMV e **soma** a remessa recebida de outra loja. O contador que soma as notas encontra
  diferença, e ela parece erro. O **Quadro 4** é a conciliação que leva de uma à outra em linhas
  nomeadas, terminando exatamente no número da apuração.
  **Os três relatórios**, todos pela janela de exportação (CSV e PDF, timbre e rodapé de graça):
  * **`memoria-cmv`** (botão em `/cmv`, ao lado do arquivo do contador) — a apuração com quatro
    quadros anexos: estoque inicial item a item, compras por documento, estoque final item a
    item, e a conciliação.
  * **`inventario-valorizado`** (botão em `/estoque`) — o estoque NUMA DATA, com o método de
    custeio declarado no cabeçalho. É o documento do balanço.
  * **`memoria-produto`** (botão em `/produtos/[id]`, com o produto já semeado) — um insumo
    movimento a movimento, com a **conta escrita na linha**:
    `(saldo × médio + entrada × custo) ÷ novo saldo`. É a resposta para *"como você chegou nesse
    custo unitário?"*: sem a conta, o número aparece pronto e não se confere.
  ⚠️ **Nada aqui recalcula.** Toda ponta sai de `cmv.valor_do_estoque` e dos mesmos tipos de
  movimento da apuração — `estoque_em` espelha até o ATALHO de hoje (`estoque_saldos` para hoje,
  fotografia do razão para data passada). Uma segunda implementação divergiria no primeiro caso
  de borda, e o sintoma seria a memória discordando do número que ela existe para explicar: pior
  que memória nenhuma. **`smoke_memoria` cobra que cada quadro FECHE com a linha.**
  ⚠️ **Cada quadro traz DOIS totais: o da coluna e o da apuração.** O do quadro soma as linhas
  ARREDONDADAS (é ele que fecha com a coluna que alguém confere à mão); o da apuração é o
  AUTORIZADO. Em 158 linhas os dois deram 2 centavos de diferença — e esconder um deles seria
  pior: ou a coluna não soma, ou não bate com o painel. Vendo os dois, a diferença tem nome.
  ⚠️ **O custo unitário NÃO vai a centavos**, ao contrário do valor: ele é um PREÇO (R$ por KG),
  e arredondá-lo faria `quantidade × custo` deixar de reproduzir o valor da linha — que é
  justamente a conta que o contador refaz.
  ⚠️ **O inventário do balanço NÃO tira os tipos fora do CMV.** Aquele filtro é da conta do
  custo da comida; o balanço é o que a casa POSSUI, e detergente em estoque é patrimônio igual.
  ⚠️ **Uma DATA, não um período** — filtro novo (`tipo: "data"`) no catálogo e na janela. A
  pergunta "quanto valia o estoque em 31/12" tem uma resposta só, e duas pontas fariam escolher
  um intervalo para ela.
  ⚠️ **A chave é `inventario-valorizado`, não `inventario`**: já existe `/exportar/inventario/{id}`,
  a folha de CONTAGEM. Dois endereços parecidos para documentos diferentes é a divergência que
  só aparece no dia em que alguém baixa o errado e manda ao contador.
  ⚠️ **O sinal vai no VALOR, não no rótulo.** A conciliação dizia "(−) o que não vira mercadoria"
  e somava um número positivo: a conta andava para o lado contrário do texto. Aquela diferença
  vai para os dois lados — item ignorado tira, acessória rateada põe — e só o número sabe qual.
  ⚠️ **O documento diz se o período está FECHADO.** Aberto, o número ainda pode mudar depois de
  o arquivo sair da casa — e este é o que se assina embaixo.
  ⚠️ Sem escolher o produto, a memória por produto sai com uma frase mandando escolher, e não
  vazia: vazio se lê como "não houve movimento", que é outra coisa.

## Armadilhas já pagas

- 🔑 **Apuração e movimentação NÃO respondem a mesma pergunta, e a diferença dormiu até o
  primeiro grupo fora do CMV existir na base.** `cmv.apuracao` desconta do estoque final os
  tipos com `considerar_no_cmv = false`; `cmv.movimentacao_por_produto` **não recebe esse
  filtro** — é relatório de ESTOQUE e mostra tudo, porque taça guardada é estoque mesmo não
  sendo custo de comida. A checagem do `smoke_cmv` comparava os dois crus e passou anos verde:
  a base local não tinha nenhum grupo fora do CMV (a semente da 029 sumiu numa limpeza com
  `--tabelas-de-apoio`, e migração não reexecuta). Assim que a 037 semeou o de utensílios, a
  identidade abriu **exatamente o valor das taças** — e parecia erro de razão.
  ⚠️ **A segunda checagem, a de ONTEM, passava por sorte**: o estoque do dia anterior ainda não
  tinha utensílio. Quebraria sozinha no dia seguinte, longe de qualquer commit — que é o pior
  tipo de teste frágil. As duas agora tiram a parcela fora do CMV dos dois lados.
  ⚠️ **A movimentação não devolve `tipo`** (só `categoria` e `setor`), então o teste casa por
  `id_produto` contra `/produtos?tipo=`. Pôr `tipo` no relatório seria melhor, mas a cópia
  congelada (`cmv_movimentacao`, migração 018) também não tem a coluna: mês fechado ficaria
  sem ela. É migração própria, não efeito colateral de outra coisa.

- ⚠️ **A fotografia do razão não sobrevive a lançamento retroativo — e não é dos ciclos.**
  `saldo_apos` é calculado na ordem de LANÇAMENTO (decisão certa: por data, o CMV de ontem
  mudaria sozinho). Como o saldo de uma data passada é lido do último movimento antes dela, um
  retroativo gravado hoje entra como "o último" e devolve um saldo que já inclui o que veio
  antes dele na fila. Resultado: `inicial + entradas − saídas = final` abre em recorte que
  termina antes de hoje. No mês inteiro fecha, porque o retroativo e o que ele contamina caem os
  dois dentro da janela — foi por isso que passou anos despercebido, com o mês sendo o único
  período possível. A tela nomeia a causa; o conserto está em `docs/o-que-falta.md`.
  ⚠️ Toda suíte que confere essa identidade tem de **garantir o ritmo MENSAL** antes, não supô-lo.

- 🔑 **A semente que sumia era a limpeza, e ela só repunha UMA das três.** A armadilha acima
  nomeia o sintoma ("a semente da 029 sumiu numa limpeza"); a causa estava em
  `limpar_dados.py`, que reaplicava só a `005_cadastros_iniciais.sql`. Os grupos do CMV nascem
  na **029** (material de limpeza e embalagem) e na **037** (utensílios, com
  `considerar_no_cmv = false`) — e migração aplicada não roda de novo, por checksum. Logo toda
  base criada com `--cliente-novo` ficava **sem grupo nenhum**: `tipos_fora_do_cmv` devolvia
  `[]` e utensílio entrava no CMV real como se fosse comida.
  ⚠️ **O raciocínio já estava escrito no próprio arquivo**, para a 005 — "o seed NÃO volta
  sozinho" — só não tinha sido aplicado às outras duas. `_SEED` virou `_SEEDS` (tupla) e
  `semear()` percorre as três.
  ⚠️ **Só `UTENSILIO` sai por padrão.** O grupo de limpeza nasce com `considerar_no_cmv = true`
  de propósito: é escolha da casa, configurável na tela. Grupo que existe mas não exclui
  ninguém não muda conta nenhuma — por isso a regressão em `smoke_grupos_cmv.py` afirma sobre o
  EFEITO (`tipos_fora_do_cmv`), não sobre a existência das linhas.
  ⚠️ **Medido na base recém-criada**: com os grupos de volta, `compras` caiu 900 e `cmv_real`
  **não se moveu** (12850,61519 antes e depois). É a confirmação do desenho documentado — grupo
  fora do CMV sai das três pontas, e a contribuição dele se anula por completo.

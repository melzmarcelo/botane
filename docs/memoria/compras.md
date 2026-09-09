# Compras

> Notas de entrada: XML, digitação, conciliação e lançamento no razão.
> Leia antes de mexer neste módulo.

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

## Armadilhas já pagas

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

- 🔑 **As unidades que vêm nas notas agora têm de-para** (09/09/2026, decisão do dono: *"conforme
  as unidades vão chegando pelas notas podemos ir vinculando ou cadastrando"*).

  ⚠️ **O silêncio que isto conserta.** Item de nota com unidade desconhecida **não parava** o
  lançamento — e continua não parando, o que é certo: recusar a nota inteira por falta de uma
  linha de cadastro seria pior. O que acontecia é que a conversão não achava caminho e a
  quantidade entrava **1:1**. Dez BJ de um produto contado em KG viravam dez quilos no razão, e o
  custo unitário saía dividido por dez. Nada avisava, e a diferença só aparecia no CMV do mês.

  ⚠️ **Mas o 1:1 só morde quem NÃO tem embalagem cadastrada.** `PUT /produtos/{id}/unidades`
  copia a unidade padrão para `um_compra`/`fator_compra`, e esse é o ÚLTIMO degrau de
  `_fator_do_item` — que não olha a unidade da nota. Tendo embalagem, o fator dela responde para
  qualquer texto. O caso real são os **607 produtos que vieram do Omie sem unidade nenhuma**,
  porque o importador descarta a unidade que não existe aqui (deixá-la entrar rebentava a chave
  estrangeira e derrubava a carga dos 2.198 por causa de um).
  ⚠️ A primeira versão da suíte montou um produto COM embalagem e "provou" um defeito que não
  existia naquele cenário — a conta já vinha certa sem de-para nenhum.

  🔑 **Por que de-para e não importar as unidades do Omie.** O cadastro de lá tem **603
  unidades** (`geral/unidade/ListarUnidades`, que só aceita `{"codigo": ""}` — as formas de
  paginar ele recusa), e é uma tabela **global e compartilhada**: `%`, `01`, `1/4`, `12X4`,
  `18x4x4`. Mesmo restrito às que os produtos da casa usam sobram **57 siglas para uns doze
  conceitos** — `PC` (194 produtos), `UNID` (74), `UND`, `UN1`, `1 UNID`, `UM` e `1` são todas
  "unidade"; `PT` (55), `PAC`, `PK` e `SC` são todas "pacote". Criá-las como unidades faria o
  combo do cadastro oferecer sete coisas com o mesmo significado — e **unidade diferente não
  converte**, então o custo pararia de fluir do jeito mais silencioso possível.

  ⚠️ **Apelido não é unidade**: sem grandeza, sem fator, fora de todo combo. Quem tem grandeza e
  fator continua sendo `unidades_medida`, e é lá que nasce a unidade que realmente falta (metro).
  A tela diz isso com todas as letras — traduzir para "a mais parecida" é como o custo para de
  fluir.

  ⚠️ **A fila é uma CONSULTA, não uma tabela** (`unidade_apelidos.pendentes`): o que apareceu em
  `nota_itens`, menos o que já é unidade, menos o que já foi traduzido. Mesma decisão da fila de
  envio ao PDV — uma fila mantida à mão precisaria ser alimentada em todo lugar que grava um item
  de nota, e o próximo lugar nasceria sem ela. Ela traz **exemplos** de produto junto: "BJ"
  sozinho não diz nada, "BJ em CHAMPIGNON FATIADO" é bandeja.

  ⚠️ **A tradução é resolvida UMA vez e usada nos três lugares** do cálculo (o fator do item, a
  comparação com a unidade de estoque e a conversão por grandeza). Traduzir em um só faria a nota
  casar a embalagem e errar a comparação. O texto CRU continua gravado em `nota_itens.um_nota` —
  é o que o fornecedor mandou, e é por ele que a fila reconhece o caso.

  ⚠️ **Vale para as PRÓXIMAS notas.** O razão é append-only: o que já entrou se corrige por
  estorno, e a tela avisa. `calcular_nota` roda na criação, na correção e no vínculo do item —
  **não no GET**.

- ⚠️ **`GET /usuarios` traz 100 por padrão, e isso derrubou ONZE suítes** (09/09/2026). O usuário
  de teste fica inativo entre as rodadas (`smoke_fundacao` o exclui no fim, e exclusão de usuário
  é lógica); com a base acumulando **148 inativos** de rodadas anteriores e a ordem sendo
  `ativo DESC, nome`, ele caiu para fora da primeira página. A busca não o achava, o POST batia em
  409 "já existe", o login falhava — e onze suítes passaram a **comparar 401 com 403**, cada uma
  acusando um defeito de permissão que não existia. As buscas de fixture passam `limite=500`.
  🔑 **O sintoma aparecia longe da causa e crescia sozinho com o tempo**, que é o pior tipo: a
  bateria passou 42/42 duas vezes seguidas hoje antes de começar a falhar, sem ninguém mexer em
  permissão nenhuma.

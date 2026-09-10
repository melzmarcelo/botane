# Custos

> Tudo que decide quanto uma coisa custa: custo médio, custo de referência, ajuste de custo e a ordem de precedência.
> Leia antes de mexer neste módulo.

## O que já existe

- 🔑 **O custo inicial vindo do Omie** (migração 049, `importador.custos_iniciais`, botão
  **Trazer o custo inicial** em Integrações, 01/09/2026, pedido do dono). Medido na base:
  **2.323 produtos ativos que controlam estoque estavam sem custo NENHUM** — nunca entrou nota
  deles aqui e não há preço de fornecedor. Sem custo não há ficha, nem CMV teórico, nem margem:
  o prato entra na conta **valendo zero** e o food cost sai bom demais, sem nada denunciando. O
  Omie já sabe o número (o CMC da posição de estoque), e a tela só sabia COMPARAR os dois.
  🔑 **É REFERÊNCIA, não movimento — e essa é a decisão que importa.** Nada entra no razão e
  nenhum saldo muda: o CMV real continua saindo do que a casa comprou e contou. Como movimento,
  2.323 linhas erradas entrariam no CMV do período da carga e **não se apagariam** — o razão é
  append-only, e a única saída seria estornar 2.323 movimentos.
  ⚠️ **`produtos.custo_referencia` é o ÚLTIMO degrau de `custos.custo_do_insumo`**, depois do
  médio do razão e do último preço do fornecedor. A ordem é a da confiança: o médio é o que a
  casa pagou com o frete DELA rateado dentro; o preço do fornecedor é o que ela negociou; a
  referência é o que outro sistema acha — melhor que nada e pior que os dois.
  ⚠️ **Só quem NÃO tem custo**, e rodar de novo só alcança quem continua sem. Referência
  sobrescreve referência; custo de verdade, nunca.
  ⚠️ **CMC zero é PULADO.** Zero não é um custo: é o Omie dizendo que não sabe, e gravá-lo faria
  a ficha calcular com um número inventado — pior que calcular sem, porque o aviso de
  "sem_custo" some.
  ⚠️ **`custo_referencia_origem` existe para daqui a seis meses**: sem ela ninguém sabe se
  aquele número foi importado ou digitado, e é essa diferença que decide se ele pode ser
  sobrescrito sem perguntar.
  ⚠️ **A prévia vem antes, sempre** (`GET /omie/custos-iniciais/previa`): mesma varredura, sem
  gravar. Com 2.323 produtos, descobrir o efeito depois é tarde. E o de-para é
  `vinculo.por_codigo_omie` — a coluna e depois os apelidos, senão o principal que absorveu um
  duplicado ficaria de fora.
  ⚠️ **A suíte provava a precedência lançando uma ENTRADA no produto da conferência** — e o
  razão é append-only: o saldo ficava lá e a rodada seguinte falhava em "o saldo daqui é zero",
  acusando um defeito que não existia. Agora ela usa produto próprio e escreve o
  `custo_referencia` direto. **Teste que deixa rastro derruba a próxima; aqui o rastro seria
  permanente.**

- 🔑 **A saída provisória saía por ZERO enquanto o cupom da mesma venda mostrava o custo**
  (`estoque._ultimo_medio_conhecido`, 10/09/2026, relatado pelo dono). O "último médio
  conhecido" só olhava para dentro do próprio razão — `estoque_saldos.custo_medio` e o
  `custo_medio_apos` do último movimento. Produto que nunca recebeu nota não tinha nem um nem
  outro, então a baixa saía a R$ 0,00, e o saldo (negativo) ficava com médio zero: a tela
  Saldos e movimentos mostrava R$ 0,00 para o produto que a tela do produto mostrava a R$ 2,76.
  🔑 **Duas respostas para a MESMA venda.** O item de venda congela o custo pela cascata de
  `custo_do_insumo` (`origem_custo = 'referencia'`), então o cupom estava certo o tempo todo —
  quem estava sozinho era o razão. Agora o último degrau do helper é a própria cascata:
  fornecedor e referência entram, e a regra continua existindo num lugar só.
  ⚠️ **É o caso mais comum da casa, não uma borda**: catálogo importado do Omie, custo inicial
  trazido junto pelo botão de Integrações, PDV vendendo antes de a primeira nota chegar. Medido na base local:
  92 movimentos provisórios a zero.
  ⚠️ **A saída continua PROVISÓRIA.** Preço de fornecedor e referência são a melhor estimativa
  disponível, não o que a casa pagou; é o filtro "só custo provisório" que aponta o que rever
  quando a nota entrar.
  ⚠️ **Zero segue possível — e aí é verdade**: ninguém sabe quanto custa. O que não podia era
  zero por o razão olhar só para si mesmo com o número a uma consulta de distância.
  ⚠️ **As linhas já gravadas ficam a zero.** O razão é append-only e correção é estorno; o
  conserto natural é a primeira entrada do produto, que sobre saldo negativo grava o médio
  novo. Ponteiro em [`estoque.md`](estoque.md).
  ⚠️ **A suíte prova sem deixar rastro**: o `custo_referencia` vai direto no cadastro, nunca por
  uma entrada — mesma armadilha do teste de precedência acima, e aqui o rastro seria permanente.

- 🔑 **A TELA e a FICHA diziam custos diferentes do mesmo produto** (10/09/2026, achado na
  varredura do módulo). A cascata (`custo_do_insumo`) pondera só
  `quantidade > 0 AND custo_medio > 0`; os saldos agrupados, a visão da rede e a posição
  exportada ponderavam TUDO — inclusive prateleira negativa. Medido: câmara com 10 kg a R$ 40 e
  bar com −2 kg a R$ 52 davam **R$ 37,00 na tela e R$ 40,00 na ficha**, no mesmo instante; com
  o bar a custo zero, **R$ 50,00 contra R$ 40,00**.
  🔑 **A tela adotou o recorte da cascata** (decisão do dono). Saldo negativo é DÍVIDA, não
  mercadoria, e o custo dele é provisório: deixá-lo pesar no médio seria uma estimativa
  corrigindo o que a casa realmente pagou.
  ⚠️ **O `valor` continua somando TUDO**, de propósito — ele responde "quanto vale o que está
  aqui", e o negativo faz parte dessa conta. Então `valor` PODE não ser
  `quantidade × custo_medio` na mesma linha: são duas perguntas, e a de dinheiro é a do custo.
  A checagem antiga de `smoke_estoque` afirmava a igualdade e continua valendo — mas só porque
  naquele cenário as duas lojas estão positivas; o comentário agora diz isso.
  ⚠️ **Eram QUATRO cópias do ponderado** (`custos.py`, dois lugares em `estoque.py`,
  `exportacao_catalogo.py`). Foi assim que a divergência nasceu: a que decide dinheiro mudou e
  as três que mostram não acompanharam.

- ⚠️ **Cópia congelada acompanha a largura da ORIGEM.** `cmv_movimentacao.codigo` era
  `varchar(20)` contra `produtos.codigo varchar(40)`: **fechar o mês estourava com 500** assim
  que a base tinha um código real de 40 caracteres. Migração 026. É a terceira vez que largura
  de coluna quebra com dado de verdade (catálogo do Omie e NCM foram as outras).

- ⚠️ **`lancar()` devolve `custo_exato` além de `custo_total`.** O razão guarda dinheiro em
  centavos, mas quem ENCADEIA custo (a produção soma consumos para achar o custo do prato)
  precisa do valor sem arredondar: a produção somava 4,48 + 4,98 = 9,46 onde a conta era
  9,455, e o prato nascia a 0,946 em vez de 0,9455 — meio centavo por unidade que reaparece
  multiplicado no CMV teórico.

- **`services/custos.py` é o único lugar que sabe quanto custa um insumo**: custo médio do
  estoque, com o último preço do fornecedor como reserva. Dinheiro em `Decimal`.

- **O médio segue a ordem de LANÇAMENTO, não a data do movimento** — data serve ao relatório;
  recalcular por data faria o CMV de ontem mudar sozinho.

## Armadilhas já pagas

- ⚠️ **O ajuste de custo é MAIS UM TIPO na tela de Ajustes, um produto por vez** — não um
  processo em lote com tela própria. A primeira versão fez lote (`/ajustes/lote`,
  `/ajustes/custo`, item no menu) e o dono pediu igual aos outros quatro: mesma tela, mesma
  forma. O lote saiu; o que ficou do backend é `POST /ajustes/custo` (recebe lista, a tela
  manda uma) e `POST /ajustes/custo/previa`. `ajuste_lotes` continua no banco e recebe um lote
  de UM por ajuste — é o que guarda autor e observação e amarra o movimento por
  `origem_tipo = 'AJUSTE_LOTE'`. **Quantidade tem porta própria e mais antiga**
  (`/estoque/entradas`, `/saidas`, `/transferencias`); o lote de estoque virou código morto e
  foi removido.
  ⚠️ **A prévia é pedida ao SERVIDOR no blur do campo**, não recalculada em TypeScript: seria a
  segunda versão da mesma regra, e as duas divergiriam no primeiro caso de borda.
  ⚠️ O campo de quantidade **some** no tipo custo — mostrá-lo desabilitado sugeriria que alguma
  quantidade se move.

- 🔑 **Movimento de quantidade ZERO some das somas que ramificam por sinal.** O ajuste de custo
  (migração 039) reavalia o estoque sem mover mercadoria: `quantidade = 0`, `custo_total <> 0`.
  A CTE da movimentação ramificava só em `quantidade > 0` e `< 0`, então ele caía em nenhum dos
  dois lados e o valor sumia — enquanto o estoque FINAL, que sai da fotografia do razão, já o
  incluía. A identidade `inicial + entradas − saídas = final` parou de fechar, e a diferença era
  exatamente o reavaliado. **Três suítes caíram de uma vez.** Agora o valor entra pelo SINAL do
  `custo_total` quando a quantidade é zero. ⚠️ A quantidade continua fora (é zero mesmo): a linha
  mostra valor sem unidade, que é literalmente o que aconteceu.
  ⚠️ **O sinal do efeito é contraintuitivo e precisa estar escrito na tela**: subir o custo do
  estoque AUMENTA o estoque final, e o CMV é `inicial + compras − final` — estoque mais caro,
  CMV **menor**. A prévia diz isso em reais antes do botão.
  ⚠️ **Teste de tela que desvia tem de VOLTAR.** As checagens novas navegavam para
  `/ajustes/lote` e `/ajustes/custo` e o bloco seguinte supunha estar em `/ajustes` — a suíte
  morria procurando campos numa página que não os tem, longe da causa.

- 🔑 **O custo do produto passou a ter onde ser CONSULTADO** (`GET /produtos/{id}/custo`, cartão
  **Custo** + botão **Histórico** na tela do produto, 03/09/2026, pedido do dono). O número já
  alimentava ficha, CMV teórico e margem, mas nenhuma tela o mostrava: para saber quanto custava
  um insumo era preciso abrir uma ficha que o usasse.
  🔑 **E a "Memória de cálculo" não cobria o caso.** Ela explica o custo MÉDIO, que nasce de
  movimento — numa casa que importou o catálogo e ainda não lançou nota ela sai VAZIA, enquanto o
  custo de referência responde pela cascata sem aparecer em lugar nenhum. Foi exatamente o
  sintoma relatado depois da carga do Omie.
  ⚠️ **A ORIGEM vem junto do valor, sempre.** "R$ 20,03" sozinho não responde se é o que a casa
  pagou, o que o fornecedor cobra ou o que outro sistema acha — três coisas que valem diferente.
  ⚠️ **Sem custo é "—", nunca R$ 0,00.** Zero é uma afirmação, e é o número que faz o food cost
  sair bom demais sem ninguém desconfiar.
  ⚠️ **NÃO se criou tabela de histórico, e não é economia.** O razão já é a memória do custo:
  `estoque_movimentos.custo_medio_apos` guarda o médio depois de cada movimento. Tabela nova
  nasceria vazia para tudo o que já aconteceu e criaria duas versões da mesma verdade. Só as
  linhas em que o médio MUDOU entram (`lag` por local) — listar todas viraria extrato de estoque.
  ⚠️ **As outras duas pontas da cascata não têm série, e a janela DIZ isso**:
  `produto_fornecedor.ultimo_preco` e `produtos.custo_referencia` guardam só o valor corrente e a
  data dele. Mostrá-los como linha do tempo faria parecer que o sistema sabe o que não sabe.
  ⚠️ Pede `estoque.saldos`, a mesma chave da memória de cálculo: custo é dado de ESTOQUE e não
  vira dado de cadastro por estar na tela do produto.

- 🔑 **As vendas antigas que entraram valendo ZERO passam a ser custeadas** (`custos_iniciais`,
  `_custear_vendas_sem_custo`, 03/09/2026, pedido do dono). Trazer o custo para o produto
  consertava METADE do problema: o item de venda guarda o custo congelado do dia da venda, e os
  que entraram antes de existir custo ficavam com nada — contando zero no CMV teórico, que é o
  que faz o food cost sair bom demais sem nada denunciando. Medido: 2.121 de 2.122 itens sem
  custo.
  🔑 **É a MESMA regra que o vínculo de cadastros já aplicava** (`fundir`): só quem está sem
  custo é tocado. Item com número guarda o que se sabia no dia da venda.
  ⚠️ **Mês FECHADO fica de fora — a fronteira que não se cruza.** Ele já foi ao contador. O
  relatório dele sobreviveria (o fechamento congela `cmv_teorico` e a movimentação por produto),
  mas reescrever as linhas por baixo faz o número congelado deixar de se reproduzir a partir dos
  dados — e reabrir o período o mudaria sozinho. A suíte prova nos DOIS sentidos: fechado não
  recusteia, aberto recusteia o mesmo item.
  ⚠️ **A origem vai GRAVADA** (`origem_custo`). A referência é o degrau mais fraco da cascata:
  congelar um palpite dentro do CMV de um mês passado só é aceitável porque a linha diz que é um
  palpite. Sem essa marca, isto não deveria existir.
  🔑 **O escopo errado devolveu ZERO, e o erro ensina onde o custo anda.** A primeira versão
  recalculava só as vendas dos produtos que acabaram de receber referência — e o custo do Omie
  cai nos INSUMOS comprados, enquanto quem foi vendido são os itens do cardápio do PDV, cadastros
  diferentes: dos 215 produtos vendidos, ZERO recebeu referência. O ganho chega ao prato pela
  FICHA, cujos insumos agora têm custo. Varre-se todo item sem custo, não os da carga.
  ⚠️ **Custo nulo continua NULO, não vira zero** — é justamente a afirmação falsa que se está
  corrigindo. Sobraram 213 produtos vendidos sem custo porque não têm ficha; a cada ficha nova,
  rodar o custo inicial de novo os alcança.

# Precificação

> A configuração de cada loja (impostos, taxas, custo operacional, margem), a análise dos preços
> e a evolução de preço × custo. Leia antes de mexer neste módulo.
> O estudo que deu origem a tudo, com o protótipo, é [`docs/precificacao-estudo.md`](../precificacao-estudo.md).

## O que já existe

- **Três telas, no grupo "Precificação" do menu** (05/10/2026, pedido do dono):
  `/precificacao` (analisar e aplicar), `/precos` (preço × custo de um produto no tempo — a
  memória dela está em [`custos.md`](custos.md)) e `/precificacao/configuracao`.
  ⚠️ O grupo se chamou "Preços" por um dia; o dono pediu o nome do módulo. ⚠️ Fora do grupo do
  CMV de propósito: ele pediu o CMV direto na lateral, e um segundo item o faria voltar a pasta.

- 🔑 **As três decisões do dono** (05/10/2026), que o código carrega:
  1. **Por loja, podendo seguir outra.** `precificacao_config.id_unidade_origem` preenchido =
     esta loja usa a configuração daquela, e aqui é só consulta. ⚠️ **Sem corrente**: só se
     segue quem TEM a configuração, e quem é seguida não pode passar a seguir outra (409 com
     frase). "De quem é a configuração de A?" não pode depender de dois saltos nem virar laço.
  2. **Vale na hora; o PDV segue o parâmetro de envio.** `aplicar` só grava o preço. A
     pendência nasce sozinha pelo gatilho de `produto_precos` (migração 044) para o produto
     integrado; se ela é ENVIADA, quem decide é `integracoes.enviar_ao_pdv`. A resposta conta
     os dois, para a tela dizer a verdade sobre o caixa.
  3. **Único, por categoria, por setor.** Toda linha tem `alcance` (TUDO, CATEGORIA, SETOR).

- 🔑 **A conta é o markup DIVISOR, e mora em `services/precificacao.py` e só lá**:
  `preço = custo direto ÷ (1 − soma dos percentuais sobre a venda)`, com a margem dentro da
  soma. ⚠️ **Não é "custo + percentual"**: imposto e cartão incidem sobre o PREÇO. Custo de
  R$ 10 com 48,5% dá R$ 19,42, não R$ 14,85 — a suíte cobra as duas afirmações.
  ⚠️ **A tela não refaz a conta**, nem no simulador: cada posição do controle chama
  `POST /precificacao/simular`. A configuração soma os percentuais para mostrar o total (soma
  é soma), mas dividir e arredondar é do servidor.

- 🔑 **A precedência: a linha MAIS ESPECÍFICA de mesmo nome substitui a geral** (`resolver`).
  Categoria ganha de setor, que ganha de tudo. É o que deixa o custo operacional ser único,
  por setor ou por categoria sem três mecanismos — e vale igual para imposto, taxa e custo por
  unidade. ⚠️ **A margem é UMA por produto**, qualquer que seja o nome da linha: "Margem da
  cafeteria" (categoria) substitui "Margem" (loja).
  ⚠️ Linha que só existe para outra categoria simplesmente não se aplica.

- ⚠️ **Uma tabela só para as três famílias de linha** (`precificacao_linhas.tipo`): PERCENTUAL
  (sai de cada real vendido), VALOR (reais por unidade — embalagem, sachê) e MARGEM. As três
  têm o mesmo alcance e a mesma precedência; três tabelas seriam três cópias da regra.

- 🔑 **O sugerido é o PISO, não o alvo.** É o menor preço que entrega a margem. Produto
  vendido ACIMA dele tem **folga**, aparece sem caixa de marcar e sem impacto — a tela não
  manda baixar preço. A primeira versão do protótipo ordenava pela diferença em módulo e punha
  no topo a sugestão de baixar a cuca de R$ 14,00 para R$ 9,90.
  ⚠️ **Arredonda sempre para CIMA** (`NOVENTA`, `MEIO`, `NENHUM`): para baixo, a sugestão
  entregaria a margem que acabou de calcular.

- ⚠️ **A análise usa o custo de HOJE** (`cmv.custo_teorico_do_produto`), não o congelado na
  última venda: precifica-se para a frente. A tela de Preços, que olha para trás, usa o
  congelado — são perguntas diferentes.
  ⚠️ **A ordem é a do impacto no mês** (diferença × quantidade vendida), prejuízo na frente.
  ⚠️ **O impacto é "se vender o mesmo"** — o sistema não prevê queda de venda, e a tela diz.
  ⚠️ **Sem custo não há sugestão** (nulo, nunca zero), e a soma de uma combinação que chega a
  100% deixa o produto "sem conta possível" em vez de a gravação recusar por um caso que talvez
  nem ocorra. Só a soma GERAL (linhas de alcance TUDO, com a margem) é barrada ao salvar.
  ⚠️ `?id_produto=` fixa um produto: a lista é cortada pelos que mais faturam, e sem isso não
  haveria como perguntar pelo que ficou de fora.

- 🔑 **De quem é o preço gravado ao aplicar**: se o produto já tem preço DESTA loja, é ele
  que muda. Senão, numa casa de uma loja só muda o preço da casa; com mais de uma, nasce um
  preço da LOJA — a configuração é por loja, e mexer no preço da casa mudaria o cardápio das
  outras sem ninguém de lá ter pedido. Usa `precos.gravar`, que só cria histórico quando muda.

- ⚠️ **Voltar de "seguir outra" para "própria" sem mandar linhas COPIA a que era seguida** —
  começar do zero deixaria a loja sem sugestão até alguém preencher tudo.

- ⚠️ **Imposto é ESTIMATIVA para precificar, não apuração fiscal.** O sistema não emite nota
  de venda. A calculadora do Simples (Anexo I, `simplesEfetivo` em `web/lib/precificacao.ts`)
  só preenche o campo; o percentual que vale é o que a casa gravar, confirmado com a
  contabilidade. A reforma tributária (CBS/IBS) não está modelada — troca-se o número.

- **Permissões** (migração 105): `precificacao.analisar`, `precificacao.aplicar`,
  `precificacao.configurar`. Administrador e Gerente recebem as três. ⚠️ **Quem tinha
  `cmv.painel` ganhou `precificacao.analisar`**, e `/precos` continua aceitando as chaves do
  CMV: a tela nasceu com elas, e tirá-las no deploy faria o item sumir do menu de quem a usava.

- **Cobertura:** `tests/smoke_precificacao.py` (62 checagens — a conta conferida à mão, a
  precedência, as recusas, simular, aplicar, seguir outra loja e as permissões),
  `tests/smoke_preco_custo.py` (25) e os blocos de Preços e Precificação no `verificar.mjs`.
  ⚠️ A suíte guarda e devolve a configuração da loja (`atexit`), cria uma filial só da rodada
  para medir "seguir outra loja" e a desativa no fim, e fixa o produto na análise — a base
  local tem centenas de vendidos no mês.

## O que ficou de fora, de propósito

- **Canais** (salão × delivery): a taxa do aplicativo hoje entra como linha por categoria ou
  setor. Preço por canal exigiria o canal na venda e no cadastro de preço.
- **Aprovação antes de aplicar**: o dono decidiu que vale na hora.
- **Produto sem preço cadastrado** não ganha caixa de marcar, mesmo com sugestão: aplicar ali
  seria CRIAR um preço, não corrigir um.

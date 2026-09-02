# O que falta na primeira parte

Levantado em 25/08/2026, comparando o [`MAPEAMENTO.md`](../MAPEAMENTO.md) item a item com o
que existe, e somando o que a análise de desempenho e confiabilidade encontrou com dado real
na base (2.183 produtos, 817 fornecedores e 30 notas de uma conta de verdade).

A fundação está inteira: acesso, cadastros, fichas com fator de correção e de cocção, razão de
estoque, inventário com contagem cega, CMV com fechamento e o Omie exercitado contra a conta
real do cliente. O que segue é o que resta.

---

## 🔴 Sem isto, metade do sistema não produz número

### O CMV por setor sai do cadastro do produto, não de onde a mercadoria saiu

`relatorios.cmv_por_grupo(agrupar="setor")` agrupa por `produtos.id_setor` — **o setor do
PRODUTO, um só**. O processo real da casa põe o mesmo insumo em vários setores: o açúcar entra
no Estoque Central e de manhã Bar, Confeitaria, Cozinha e Cafeteria levam um pacote cada. Hoje
todo o consumo de açúcar é atribuído a um setor.

A ponte já existe desde a migração 051: `locais_estoque.id_setor` diz de quem é a prateleira, e
`estoque_movimentos.id_local` diz de onde a mercadoria saiu. Falta o relatório passar a somar
pelo setor do **local do movimento**, com o setor do produto como reserva para o que sair de um
local sem setor.

⚠️ **Não é uma troca de `JOIN`.** As três CTEs (`inicial`, `compras`, `final`) agregam por
`id_produto`; passariam a agregar por `(id_produto, id_local)`. As fotografias de estoque já são
`DISTINCT ON (id_produto, id_local)`, então o dado está lá — mas a identidade *a soma dos grupos
fecha com o CMV do período* é cobrada pela bateria, e é ela que dá sentido ao corte por grupo.
Merece entrega própria, com a bateria inteira em cima dela.

⚠️ E muda número de relatório já lido pelo dono: o "quanto a cozinha pesou" de antes e o de
depois não vão bater, e a tela precisa dizer por quê.

### Carga inicial das fichas técnicas

**Há zero fichas.** Sem elas não existe CMV teórico; sem CMV teórico não existe variância nem
food cost — que é o número que o sistema existe para produzir. O painel é honesto e mostra
"—" em vez de zero, mas metade da tela fica muda.

Não é código: é levantar as receitas da casa (planilha, caderno ou cabeça da cozinheira) e
cadastrá-las. O que talvez precise de código é uma **importação em massa** de fichas por
planilha, se o volume justificar.

---

## 🟠 Falta construir

### Remessa de VÁRIOS produtos numa vez (31/08/2026)
`POST /transferencias` já aceita N itens, e a tela de recebimento confere item a item — mas o
**envio** só nasce por *Estoque ▸ Ajustes*, um produto de cada vez, então na prática cada
remessa tem um item só. Quem manda a produção da semana para a filial despacha oito produtos
juntos, num carro só, e hoje isso vira oito remessas para o outro lado conferir uma a uma.

Falta a tela `/transferencias/nova`: escolher origem, destino e ir somando produtos, no modelo
de `/compras/nova`. **O servidor não muda** — é só o formulário que falta.

⚠️ E aí vale a mesma prévia do inventário: quantos itens, e o saldo de cada um na prateleira de
origem, ANTES do botão.

### Foto na ficha e no produto
A coluna `foto_url` existe em `fichas_tecnicas`; não há upload nem exibição. Só a logo da
empresa tem caminho de envio hoje. A cozinha reconhece prato por foto, não por código.

### Cobertura de vínculo como indicador
O painel mostra a cobertura de **ficha**. O mapeamento (seção 9) pede outra coisa: **% da
receita do período com prato vinculado à ficha**. CMV teórico de 60% do faturamento não é CMV
teórico — é metade da conta, e o número precisa dizer isso na cara de quem olha.

### Conciliação por semelhança fora do Python
Medido: **296 ms por item pendente**, dos quais 94% é comparação de texto contra 2.183
produtos. Uma nota com 50 itens desconhecidos leva 15 s; reconciliar 1.100 itens levaria 5,4
minutos numa chamada só. O `pg_trgm` está disponível no servidor e **não instalado** — com
índice trigrama isso vira milissegundos.

---

## 🟡 Falta, e dói quando a base cresce

### A fotografia do razão não sobrevive a lançamento retroativo
`saldo_apos`/`custo_medio_apos` são calculados na **ordem de lançamento** — decisão de projeto,
e a certa: recalcular por data faria o CMV de ontem mudar sozinho. A consequência, que só agora
ficou visível, é que **um movimento gravado hoje com data de trás carrega a fotografia do
momento em que foi gravado**. Como `valor_do_estoque` e `movimentacao_por_produto` leem o saldo
de uma data passada pegando o último movimento antes dela, esse retroativo entra como "o
último" e devolve um saldo que já inclui o que veio antes dele na fila de gravação.

Efeito prático: a identidade `inicial + entradas − saídas = final` abre num recorte que
**termina antes de hoje**, se houve retroativo depois. Medido na base local: três produtos do
`smoke_cmv` (que lança retroativo de propósito) abriam R$ 130,00 cada num recorte de um dia. No
recorte do mês inteiro a conta fecha, porque o retroativo e os movimentos que ele contamina
caem os dois dentro da janela — foi por isso que passou despercebido enquanto o único período
possível era o mês.

⚠️ **Não é regressão dos ciclos de fechamento** — é anterior a eles, e sempre esteve ao alcance
de quem escolhesse datas na mão. Os ciclos só tornaram a janela curta o padrão. A tela nomeia
essa causa junto com a do saldo negativo.

Consertar de verdade quer dizer parar de usar a fotografia para data passada e reconstruir o
saldo somando o razão **na ordem de data** — o que é caro (é justamente o que a fotografia
existe para evitar) e muda o número histórico. A alternativa barata é **impedir retroativo
fora de período fechado** — hoje só o fechamento trava, e período aberto aceita qualquer data
de trás. Decidir antes de a casa começar a usar retroativo com frequência.

### Engenharia de cardápio
`cmv.margem_por_prato` já entrega o que cada prato vendeu, custou e deixou. Falta a matriz que
cruza **popularidade × margem** e classifica em estrela, cavalo de batalha, quebra-cabeça e
abacaxi — que é o que transforma a lista numa decisão de cardápio.

### Classificar produtos em massa
O catálogo do Omie trouxe **2.183 produtos sem categoria e sem setor**. Enquanto ficarem
assim, o relatório de CMV por grupo devolve tudo em "Sem setor" e não serve para nada. Falta
uma tela de classificação em lote (selecionar N produtos, aplicar categoria e setor).

### ~~Unificar cadastros duplicados~~ — FEITO (27/08/2026)
O botão **Vincular**, na tela do produto: escolhe-se o outro cadastro numa busca, vê-se a prévia
e funde. A descrição fica com o nome do lado do Omie e a curta com o do PDV; os códigos das duas
integrações (`codigo_omie` e o novo `codigo_pdv`) passam para o mesmo cadastro; os campos em
branco se completam; o que sai vira inativo.

🔑 **A detecção automática foi construída e depois REMOVIDA — vale registrar por quê.** Um
cruzamento por semelhança de nome errava nos dois sentidos: não achava `BEB CERV HEINEKEN 350ML`
contra `CERVEJA HEINEKEN PILSEN` (o mesmo produto, 63,8%) e juntava `CAKE BOARD N19` com
`CAKE BOARD N21`, que são tamanhos diferentes. **Nenhum piso separa os dois casos, porque a
diferença não está no texto.** Quem reconhece produto é gente.

⚠️ **O que NÃO foi feito, de propósito: mover saldo e movimentos.** O razão é append-only. Um
cadastro com movimento fica; é o outro que é absorvido. Onde os DOIS têm movimento, a fusão é
recusada — juntar duas histórias de estoque exigiria reescrever o razão, e o custo médio
resultante seria uma invenção.

### `cest` no produto
Campo fiscal previsto no mapeamento (4.3) e ausente na tabela.

---

## ⚪ Bloqueado por terceiro — não é dívida nossa

### PDV Legal — falta a ficha técnica dos pratos
**As vendas e o de-para estão prontos** (26/08/2026). Na conta real: 46 vendas importadas, o
cardápio de **164 itens** trazido, e **102 itens de venda vinculados** ao prato correspondente.

**O que falta agora é a ficha técnica.** Os 164 pratos nasceram como **rascunho** com
`producao_propria` marcada — estão na fila de "produzido sem ficha", em Produtos. Enquanto
nenhum tiver ficha, `com_custo` é zero: a venda entra, a receita aparece, e o **CMV teórico
continua zero**. É a mesma pendência que já era o maior item desta lista, agora com a lista
pronta e nomeada em vez de em branco.

Ordem que rende mais: fazer a ficha dos pratos **mais vendidos** primeiro. A tela de Vendas
ordena por receita, e `cmv.margem_por_prato` mostra o que cada um faturou.

⚠️ **Não case código de cardápio com código de produto.** A primeira versão da cascata fazia
isso e criou 78 vínculos errados (REDBULL → LIMÃO TAITY). Os dois números são espaços de nome
diferentes. Vinculam o de-para e o nome idêntico; semelhança vira dica no rascunho.

Também não verificado: a paginação do `cupom/get` (a importação dia a dia não tem teto) e os
valores de `tipovenda` além do `"B"`.

---

## Fora do código

- **Não há deploy.** O sistema roda só local nesta primeira parte. Hospedagem e **backup**
  seguem parados desde que foram adiados.
- **Dados da empresa** incompletos: só razão social e UF preenchidos. Faltam CNPJ, IE, regime
  tributário, endereço, contador e logo.
- **Quem recebe login**, e quantos — hoje existe só o administrador.

---

## Divergências entre o mapeamento e o que foi construído

Coisas que mudaram com bom motivo e que o `MAPEAMENTO.md` ainda não registra:

1. **"A venda não baixa estoque"** (seção 9, decisão 1) deixou de valer. A venda baixa todo
   produto que controla estoque. O receio original — contar duas vezes o mesmo quilo de carne
   — não se materializa porque o insumo sai pela produção e o produto PRONTO sai pela venda;
   são movimentos de coisas diferentes. Sem essa baixa, o CMV real saía subestimado e a
   primeira contagem cobria o buraco como "ajuste de inventário".
2. **`modo_producao`** (`PARA_ESTOQUE` / `NA_HORA`) não existia no mapeamento. Sem ele, a casa
   venderia mil cafés e o pó continuaria inteiro no razão.
3. **`KIT`** era um tipo previsto e não implementado; hoje é `services/kits.py`.

## O envio de e-mail segura a transação do banco (28/08/2026)

`email.enviar(cur, ...)` recebe o cursor e faz a conversa SMTP **dentro** da
transação. São três chamadores — o botão de teste, a criação de usuário e a
recuperação de senha — e o último é **rota pública**: cada pedido prende uma
conexão do pool por até `ORCAMENTO_ENVIO` (20 s) enquanto fala com um servidor
externo. Numa casa com o SMTP mal configurado, alguns pedidos seguidos esgotam
o pool e derrubam o sistema inteiro, não só o e-mail.

O caminho já está aberto: `email.entregar(cfg, msg)` não toca no banco. Falta
reordenar os chamadores para **ler a configuração, fechar a transação, enviar e
só então gravar o status**.

⚠️ Na recuperação de senha a ordem importa: o token tem de ser gravado **mesmo
que o envio falhe** — senão o admin não consegue entregar o link pela tela de
Usuários, que é a saída prevista para quem não tem SMTP.

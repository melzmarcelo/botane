# O que falta na primeira parte

Levantado em 25/08/2026, comparando o [`MAPEAMENTO.md`](../MAPEAMENTO.md) item a item com o
que existe, e somando o que a análise de desempenho e confiabilidade encontrou com dado real
na base (2.183 produtos, 817 fornecedores e 30 notas de uma conta de verdade).

A fundação está inteira: acesso, cadastros, fichas com fator de correção e de cocção, razão de
estoque, inventário com contagem cega, CMV com fechamento e o Omie exercitado contra a conta
real do cliente. O que segue é o que resta.

---

## 🔴 Sem isto, metade do sistema não produz número

### Carga inicial das fichas técnicas

**Há zero fichas.** Sem elas não existe CMV teórico; sem CMV teórico não existe variância nem
food cost — que é o número que o sistema existe para produzir. O painel é honesto e mostra
"—" em vez de zero, mas metade da tela fica muda.

Não é código: é levantar as receitas da casa (planilha, caderno ou cabeça da cozinheira) e
cadastrá-las. O que talvez precise de código é uma **importação em massa** de fichas por
planilha, se o volume justificar.

---

## 🟠 Falta construir

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

### Engenharia de cardápio
`cmv.margem_por_prato` já entrega o que cada prato vendeu, custou e deixou. Falta a matriz que
cruza **popularidade × margem** e classifica em estrela, cavalo de batalha, quebra-cabeça e
abacaxi — que é o que transforma a lista numa decisão de cardápio.

### Classificar produtos em massa
O catálogo do Omie trouxe **2.183 produtos sem categoria e sem setor**. Enquanto ficarem
assim, o relatório de CMV por grupo devolve tudo em "Sem setor" e não serve para nada. Falta
uma tela de classificação em lote (selecionar N produtos, aplicar categoria e setor).

### Unificar cadastros duplicados
A conta real trouxe **12 hortifrútis com cadastro repetido** (`laranja pera` tem 5, `mirtilo`
tem 3). Hoje só há desativar um a um. Quando a próxima compra vier pelo código do gêmeo, o
custo médio da laranja passa a existir em dois lugares. Falta uma ação de **unificar**: mover
saldo, movimentos e vínculos de um produto para outro.

### `cest` no produto
Campo fiscal previsto no mapeamento (4.3) e ausente na tabela.

---

## ⚪ Bloqueado por terceiro — não é dívida nossa

### PDV Legal
Faltam as credenciais (`username`, `password`, `client_id`, `client_secret`) **e** o acesso à
documentação dos endpoints, que não é pública. O cliente pede ao suporte deles, como titular
da conta — ver [`integracoes-o-que-pedir.md`](integracoes-o-que-pedir.md).

Enquanto não vem, a venda entra por **planilha ou digitação**, que é o plano B previsto e
funciona. Quando a API abrir, muda a fonte e não o resto.

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

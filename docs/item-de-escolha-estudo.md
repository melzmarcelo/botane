# Item de escolha no catálogo — estudo (29/10/2026) · ENTREGUE na 1.1.153

🔑 **Pedido do dono (29/10/2026):** *"no catálogo, gostaria de colocar um 'item' configurável.
Por exemplo, Monte sua cesta. Aí teremos 3 produtos Cesta, que é embalagem: Pequena, Média,
Grande. Dentre estas é necessário selecionar um para ir para o próximo passo. Para cada produto
teremos configuração de quantidade mínima e máxima de itens. Ao selecionar, aparece a lista de
itens configurados para que possa ser adicionado, e somando dá o valor total da cesta. [...]
Chocolate Quente (este não é um produto): ao selecionar, tem a escolha Preto ou Branco. Estes
são o produto, que no fundo é Chocolate Quente Preto e Chocolate Quente Branco."*

## Decisões do dono (29/10/2026)

| # | Pergunta | Decisão |
|---|---|---|
| 1 | O mesmo item pode ir mais de uma vez na cesta? | **Sim** (2 geleias). |
| 2 | Preço da cesta | **Embalagem + soma do preço de cada item escolhido.** Item pode ser marcado "incluso" e entra por R$ 0. |
| 3 | Onde aparece | **Site (pedido/encomenda) e mesa (Cardápio Vivo).** |
| 4 | No caixa | **A casa lança no PDV a embalagem e cada item como linhas separadas** — é como o pedido já chega no painel. A cesta NÃO é KIT: o kit tem composição fixa. O pedido continua sem mexer em estoque. |

## O modelo — dois passos que já se encaixam no que existe

1. **Item de escolha** (novo): uma linha do catálogo que NÃO é produto — nome, descrição e foto
   próprios — e que oferece uma lista de PRODUTOS. O cliente escolhe UM para seguir.
   Chocolate Quente → Preto / Branco. Monte sua cesta → Pequena / Média / Grande.
2. **Os adicionais do produto escolhido** (já existem, migração 113): grupos com mínimo/máximo e
   opções que podem apontar para um produto (o preço sai dele). A Cesta Média tem o grupo
   "Itens da cesta", de 3 a 6.

O pedido leva o PRODUTO escolhido (Chocolate Quente Branco; Cesta Média), com os adicionais
congelados — o painel, o "lançar no PDV" e o PDF não mudam de conta.

## O que se constrói

- **Migração 142**
  - `catalogo_itens.id_produto` passa a aceitar NULO; colunas `tipo` (`PRODUTO`|`ESCOLHA`),
    `nome`, `descricao`, `foto_url` e traduções `_en`/`_de`. CHECK: PRODUTO exige produto;
    ESCOLHA exige nome e NÃO tem produto.
  - `catalogo_item_escolhas` (`id_item`, `id_produto`, `rotulo` opcional — "Preto" —, `ordem`),
    único por (`id_item`, `id_produto`).
  - `produto_adicionais_grupos.permite_repetir` (padrão falso: o que existe continua igual).
  - `produto_adicionais_opcoes.incluso` (padrão falso): entra por R$ 0 mesmo com produto.
- ⚠️ **As 42 consultas sobre `catalogo_itens`**: as que fazem `JOIN produtos` deixam o item de
  escolha de fora sozinhas — é o comportamento certo para A/B, atenção, anúncios e cartões
  nesta primeira fase. Entram de propósito: o feed, o cardápio do site, o conteúdo do cadastro,
  o resumo/"o que falta" e o pedido.
- **Pedido** (site E mesa): a linha do carrinho manda `item`, `escolha` (o produto, quando o item
  é de escolha) e `adicionais` como lista de `{opcao, quantidade}`. A regra de mínimo/máximo é
  UMA, em `cardapio_pedido._escolhas`, e o pedido do site passa a usá-la (hoje os adicionais do
  site iam no texto da observação).
- **Cadastro**: na aba Cardápio, "+ item de escolha" ao lado de "+ pratos"; a gaveta do item de
  escolha edita nome, descrição, foto e a lista de produtos. No produto, o grupo de adicionais
  ganha "pode repetir", a opção ganha "incluso" e o grupo ganha "copiar de outro produto"
  (as três cestas usam a mesma lista).
- **Feed e site**: o item de escolha abre um passo "escolha um" (com o preço de cada), depois os
  adicionais do escolhido com contador (− 2 +) quando o grupo deixa repetir, e o total
  atualizando.

## Ordem

1. Banco + serviço + rotas do cadastro, com suíte.
2. Pedido com escolha e adicionais com quantidade (site e mesa), com suíte.
3. Telas: cadastro (catálogo e produto), feed e site; bateria do navegador.

# PDV Legal (Tablet Cloud) — a API, como ela é

Obtido em **26/08/2026**, com a credencial do cliente. O catálogo não é público:
fica no portal de parceiros. Ele apareceu em `GET /help` — a página de ajuda do
ASP.NET Web API —, que **só responde com o Bearer token** (sem token dá 500).

O HTML cru está em [`pdv-legal-help.html`](pdv-legal-help.html); este arquivo é o
recorte do que interessa ao Botané. São 173 rotas ao todo.

---

## Autenticação

```
POST https://api.tabletcloud.com.br/token
Content-Type: application/x-www-form-urlencoded

grant_type=password&username=…&password=…&client_id=…&client_secret=…
```

- `client_id` é o **código do grupo econômico**; `client_secret`, o token dele.
- Devolve `access_token` (JWT de ~342 caracteres) e `expires_in`.
- ⚠️ **`expires_in` veio 43.199 s (12 h)**, não as ~6 h que a documentação
  pública sugeria. O código não depende disso: usa o que vem, com 5 min de folga.

## A conta do cliente

Uma filial: **código `37622`**, CAFE DA CLINICA LTDA, CNPJ 59.938.158/0001-50,
Biguaçu. O `client_id` (31121) aparece nos cupons como `codempresa`.

---

## As rotas que interessam

| Rota | Para quê |
|---|---|
| `GET filial/get` | as filiais — é de onde sai o parâmetro `filiais` |
| `GET cupom/get/{dataInicial}/{datafinal}/{filiais}` | **as vendas** |
| `GET cupom/get/{offset}/{dataInicial}/{datafinal}/{filiais}` | o mesmo, paginado |
| `GET cupom/get/{VendaId}/{CodFilial}` | um cupom específico |
| `GET produtos/get` | o cardápio inteiro — a base do de-para |
| `GET produtos/getbydata/{dataUltimomodificacao}` | só o que mudou desde uma data |
| `GET produtos/getlistaresumida/{pagina}` | lista resumida, paginada |
| `GET grupoprodutos/get` | grupos do cardápio (viram categoria) |
| `GET tools/motivocancelamento/{CodFilial}` | os motivos de cancelamento |

⚠️ **O limite que decide a estratégia de importação.** A própria documentação
diz: *"Devolve uma lista de cupons com intervalo máximo de 10 dias e no máximo
100 registros — obs: se a data inicial e final forem iguais não existe
limitação"*.

Ou seja: **importar DIA A DIA** (`dataInicial == dataFinal`) é o único caminho
sem teto de 100 registros. Uma casa com 48 cupons num dia comum estoura o teto
em três dias de janela; pedir "os últimos 10 dias" traria 100 cupons e calaria o
resto — e ninguém veria falta nenhuma, porque 100 é um número plausível.

`filiais` é uma lista separada por vírgula: `37622` ou `10,20,30`.

---

## A forma real do cupom

Conferida contra a conta do cliente, não contra a documentação — é a lição do
Omie, onde quatro campos que a doc previa vinham vazios.

```
venda_id        int      1608263957   ← identidade da venda (idempotência)
codcupom        int      626771538
loja_id         int      37622        ← a filial
codempresa      int      31121        ← o client_id
dtmovimento     str      "2026-08-26T00:00:00"   ← a data do negócio
dtabertura      str      "2026-08-26T07:56:00"
dtrecebimento   str      "2026-08-26T07:57:29"
iscancelado     bool     false
isestornado     bool     false
valortotal      float    5.0
valordesconto   float    0.0
valoracrescimo  float    0.0
valorentrega    float    0.0
tipovenda       str      "B"          ← o canal
nomeVendedor    str      "admin"
terminal_id     str      "276DEC57EECF"
itens           list     […]
formaPgtos      list     […]
notas           list     […]          ← a NFC-e, com número de protocolo
clientes        list     []
modificadores   list     []
```

### O item

```
codproduto      int      10689993     ← o código do produto NO PDV (o de-para)
codigoVenda     str      "195"        ← o código do cardápio
nomeProduto     str      "PDQ C/ REQ CMB"
quantidade      float    1.0
valortotal      float    5.0          ← o total da LINHA, não o unitário
valordesconto   float    0.0
valoracrescimo  float    0.0
valorcusto      float    3.29         ← o custo que o PDV acha
iscancelado     bool     false        ← cancelamento por ITEM, além do cupom
```

⚠️ **`valortotal` é o total da linha.** O unitário sai da divisão pela
quantidade — e quantidade zero existe em cupom cancelado, então a divisão
precisa de guarda.

⚠️ **`valorcusto` é o custo do PDV, e NÃO deve virar o nosso.** O CMV teórico do
Botané é `quantidade × custo da ficha daqui`; usar o número de lá seria trocar a
ficha da casa pelo cadastro do PDV, que é justamente o que não se quer conferir
contra si mesmo. Ele serve, no máximo, como um segundo par de olhos.

⚠️ **Cancelamento em dois níveis**: `iscancelado`/`isestornado` no cupom e
`iscancelado` no item. Um cupom válido pode ter uma linha cancelada dentro.

⚠️ **`dtmovimento` do cupom vem com hora zerada** (a data do negócio) e a do
item vem com a hora do lançamento. Para o CMV vale a do cupom: é ela que diz em
que dia a venda conta.

---

## O cardápio — `produtos/get` (lido na conta real em 26/08/2026)

Devolve uma **lista** (não um envelope) com **630 itens** na conta do cliente, e
cada item traz muito mais do que a lista resumida:

```
codigo             int    7029540         ← o de-para: é o `codproduto` do item da venda
codigoVenda        int    187             ← o número digitado no PDV, não é chave
codReferencia      str    "533"           ← ⚠️ NÃO casa com `produtos.codigo` daqui
descricaoCupom     str    "ACONCHEGO FRIO"
descricaoDetalhada str    "ACONCHEGO FRIO"
status             bool   true            ← false = fora do cardápio (166 dos 630)
nomeGrupo          str    "CHA"           ← vira CATEGORIA
nomeImpressora     str    "BAR"           ← vira SETOR (VITRINE/BAR/COZINHA/Nenhum)
unidade            str    "UN"            ← "GR" aqui é "G"
codigoNCM          str    "21011200"      ← 463 dos 464 ativos vêm preenchidos
codigoEAN          str    ""              ← ⚠️ vazio em 100% da conta real
localEstoque       str    "Botane"
baixaEstoque       bool   true            ← true em 100% — não separa nada
```

⚠️ **`getlistaresumida` traz MENOS itens, e não avisa.** Na mesma conta ela
devolveu 570 dos 630 — sessenta pratos a menos, calada. Ela também só tem quatro
campos (`codigo`, `codReferencia`, `descricao`), então o rascunho nasceria sem
categoria, sem setor, sem NCM e sem unidade. Ficou como reserva.

⚠️ **A impressora é o dado mais útil que ninguém esperaria.** VITRINE (183),
BAR (132), COZINHA (66) e "Nenhum" (83) descrevem onde o item é preparado — que
é exatamente o que "setor" significa aqui. Sai de graça um CMV por setor que de
outro jeito alguém teria de digitar 630 vezes. **"Nenhum" não é setor**: é o
texto do PDV para "não imprime em estação nenhuma".

⚠️ **O grupo NÃO diz se o item é revenda ou produção própria.** "PRODUTOS
MERCEARIA" e "CATERING" caem os dois em "Nenhum", e um é comprado pronto e o
outro é feito na casa. O tipo continua sendo decisão de quem confere o rascunho;
chutar poria o prato na fila errada — a de "falta ficha" em vez da de "falta
compra".

### Código de barras: não existe nesta conta

Conferido nos três lugares possíveis em 27/08/2026 — vale registrar para não se
repetir a busca:

| Onde | Campo | Resultado |
|---|---|---|
| `produtos/get` | `codigoEAN` | existe no modelo, **vazio em 630 de 630** |
| `produtos/getlistaresumida` | `listaUnidadeCompra[].codEAN` | a lista vem **vazia em 570 de 570** |
| item do cupom | — | **não existe** campo de código de barras |

⚠️ **`listaUnidadeCompra` é o único lugar da API com fator de embalagem**
(`{unidade, fatorconversao, codEAN}`), e só aparece na rota resumida. Se um dia
o cliente preencher, é dali que sai o `produto_unidades`.

⚠️ **O contraste explica**: NCM preenchido em 463 de 464, EAN em zero. O NCM é
obrigatório para emitir o cupom fiscal; o EAN é opcional — e num café ninguém
bipa nada, o operador toca um botão. O campo nunca teve a quem servir.

⚠️ A página de ajuda de cada rota (`/Help/Api/GET-produtos-get`) traz o **modelo
de campos**; o índice de `/help` traz só a lista de rotas. As duas respondem
apenas com o Bearer token.

### `grupoprodutos/get`

30 grupos, com `codigo`, `nome`, `corIcone` e `ativo`. Os nomes são os que viram
categoria: ALMOCO, CAFETERIA, SANDUICHES, VITRINE SECA DOCE, GELADEIRA…

---

## O que ainda não foi verificado

- **Paginação** (`cupom/get/{offset}/…`): não foi exercitada, porque a
  importação dia a dia não tem teto.
- **`produtos/getbydata/{data}`**: seria o caminho para atualizar só o que mudou
  no cardápio, em vez de reler os 630. Não foi chamada.
- **`tipovenda`**: na janela de 30 dias da conta real apareceram os valores já
  mapeados; nenhum desconhecido chegou a virar `null`.

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

## O que ainda não foi verificado

- **O cardápio** (`produtos/get`): a rota existe e está documentada, mas a
  resposta real não foi lida. É o que liga `codproduto` ao prato com ficha.
- **Paginação** (`cupom/get/{offset}/…`): não foi exercitada, porque a
  importação dia a dia não tem teto.
- **`tipovenda`**: só o valor `"B"` apareceu no dia lido. Os outros (delivery,
  mesa) precisam de um dia com movimento diferente para serem confirmados.

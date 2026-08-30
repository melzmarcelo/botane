# Uma segunda loja — o que já existe, o que falta e o que decidir

*Levantado em 30/08/2026, lendo o esquema e o código, não a memória.*

O sistema nasceu multi‑loja: **`id_unidade` está em 18 tabelas**, e a regra 5 do projeto
("toda tabela de movimento carrega `id_unidade`") foi seguida. Então a pergunta não é *"dá para
ter duas lojas?"* — é **"o que acontece no dia em que existir a segunda?"**.

Este documento responde isso com o que está no código hoje. Ele não implementa nada.

---

## 1. O que já está pronto

**O dado já é por loja.** Carregam `id_unidade`, e não vazam entre lojas:

| assunto | tabelas |
|---|---|
| razão de estoque | `estoque_movimentos`, `estoque_saldos`, `estoque_lotes`, `ajuste_lotes` |
| operação | `inventarios`, `producoes`, `producao_agenda`, `notas_entrada`, `vendas` |
| apuração | `cmv_fechamentos` |
| configuração | `parametros`, `locais_estoque`, `integracoes`, `pdv_envios` |
| acesso | `usuario_papeis`, `auditoria` |

**A chave do saldo é `(id_unidade, id_local, id_produto)`** — duas lojas com o mesmo produto no
mesmo nome de local são duas linhas diferentes, como tem de ser.

**O escopo do usuário existe e é real.** `usuario_papeis.id_unidade` nulo quer dizer "todas as
lojas"; preenchido, restringe. `Contexto.ve_unidade` é a única porta, e o cabeçalho `X-Unidade`
é validado por ela — **mandar o cabeçalho não dá acesso a loja nenhuma**.

**O seletor de loja está na barra superior**, embaixo do nome da empresa, e trocar de loja
recarrega a página inteira de propósito — cada tela já buscou saldo, alerta e apuração da loja
anterior.

**A configuração é por loja onde precisa ser**: `parametros` tem `id_unidade` como chave
primária (ciclo de fechamento, dia de corte, travas), e `integracoes` também — **cada loja pode
ter sua própria conta de PDV, com a sua filial**.

**Criar a loja já funciona**: `POST /unidades` grava a loja e cria a linha de `parametros`.

---

## 2. O que quebra ou mente no dia da segunda loja

### 🔴 2.1 O custo do insumo é calculado sobre TODAS as lojas

É o achado mais grave, e não aparece em teste nenhum enquanto houver uma loja só.

`services/custos.py::custo_do_insumo` faz a média ponderada de `estoque_saldos`
**sem filtrar `id_unidade`**:

```sql
SELECT sum(quantidade * custo_medio), sum(quantidade)
  FROM estoque_saldos
 WHERE id_produto = %s AND quantidade > 0 AND custo_medio > 0
```

Com duas lojas, o café que a Matriz comprou a R$ 40/kg e a Filial a R$ 52/kg passa a valer
**R$ 45,30 nas duas** — e nenhuma das duas pagou isso.

Isso não fica contido: `custo_do_insumo` alimenta

- o **custo da ficha técnica** (`custos.py:229`),
- o **custo congelado do item de venda** (`cmv.py:525`),
- o **custo da baixa por vínculo** (`estoque.py:578`).

Ou seja, contamina **ficha, CMV teórico, margem por prato e food cost** das duas lojas ao mesmo
tempo. E é silencioso: nenhum número fica absurdo, só errado.

⚠️ **A correção não é só acrescentar um `WHERE`.** É preciso decidir o que fazer quando a loja
não tem saldo daquele insumo: cair no custo da outra loja? no último preço do fornecedor? ou
devolver "sem custo"? A reserva de hoje (`produto_fornecedor.ultimo_preco`) é da casa, não da
loja — e provavelmente continua sendo a resposta certa, porque preço de compra negociado vale
para a rede.

### 🔴 2.2 Transferência entre lojas não existe

`estoque.transferir` recebe **um** `id_unidade` e dois locais. Movimento de uma loja para outra
não tem como ser representado: seria uma saída numa loja e uma entrada em outra, com custo
atravessando a fronteira.

Hoje, se alguém escolher um local da outra loja, o razão registra os dois lados sob a mesma
loja — e o saldo das duas fica errado sem nada denunciando.

⚠️ Isto é o que uma casa com duas lojas faz **toda semana** (a Matriz produz e manda para a
Filial). Não é um extra.

### 🟠 2.3 A loja nova nasce sem local de estoque

`POST /unidades` cria a loja e os parâmetros, e mais nada. **Sem local, nada se movimenta** — e
a mensagem que aparece é "Local não encontrado", que não diz o que fazer.

A migração 016 já ensina a regra ("o primeiro local da loja nasce principal"); falta a loja
nova nascer com um.

### 🟠 2.4 Setor é global; local é por loja

`locais_estoque.id_unidade` é **NOT NULL**; `setores.id_unidade` é **anulável** (hoje todos
nulos = da casa). É uma assimetria defensável — setor é organização do cardápio, local é
prateleira física — mas precisa ser dita, porque a tela de Tabelas de apoio mostra as duas
juntas e não distingue.

### 🟠 2.5 O preço de venda tem coluna por loja, e ninguém a usa

`produto_precos.id_unidade` é anulável, e `cardapio._gravar_preco` grava **sempre com
`id_unidade IS NULL`** (o preço da casa). No PDV o preço é **por filial** — duas lojas podem
cobrar valores diferentes pelo mesmo prato, e o `tabelapreco/get/{filial}` já devolve isso.

A estrutura está pronta; a decisão não foi tomada.

### 🟡 2.6 Não há visão consolidada

Toda tela responde pela loja atual. Não existe "CMV da rede", "estoque parado somando as duas"
nem comparação lado a lado. Para o dono de duas lojas, essa é a tela que passa a existir — e
hoje ela não existe nem como endpoint.

### 🟡 2.7 Ficha, produto, fornecedor e categoria são da CASA

Nenhum tem `id_unidade`, e isso está certo: o cardápio é o mesmo, o cadastro é o mesmo. Só vale
registrar que **a receita é uma só** — se uma loja fizer o prato com outra composição, o modelo
de hoje não representa isso.

---

## 3. Ordem APROVADA (30/08/2026)

O dono aprovou iniciar por aqui, logo depois da separação de permissões do inventário.

1. **O custo por loja** (2.1). É correção, não recurso: sem ela os números das duas lojas ficam
   errados desde o primeiro dia, e errados para trás, porque o custo do item de venda é
   congelado no momento da venda.
2. **A loja nova nascer utilizável** (2.3) — um local principal junto com a loja.
3. **Transferência entre lojas** (2.2), com o custo atravessando: saída pelo médio da origem,
   entrada por esse mesmo valor no destino. É o que mantém a identidade do CMV das duas.
4. **Preço por loja** (2.5), se as duas cobrarem diferente.
5. **A visão consolidada** (2.6), que é a tela nova de verdade.

---

## 4. O que precisa de decisão sua

- **Custo do insumo sem saldo na loja**: cai para o último preço do fornecedor (da rede), ou
  fica "sem custo"?
- **Preço de venda**: um da casa, ou um por loja?
- **Transferência entre lojas**: dois movimentos ligados (o modelo honesto), ou uma "nota
  interna" que passa pelo mesmo caminho da compra?
- **Quem enxerga o quê**: gerente de uma loja vê só a dele (já é possível hoje) — e o dono
  precisa de uma tela que some as duas.

---

## 5. O que NÃO precisa mudar

Vale dizer, porque é a maior parte: razão, saldos, lotes, inventário, produção, notas, vendas,
fechamento, parâmetros, integrações e auditoria **já são por loja** e não precisam de migração
nenhuma. O trabalho está no custo, na transferência e nas telas — não na fundação.

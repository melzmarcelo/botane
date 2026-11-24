# Finalizadoras do PDV Legal — estudo

🔑 **Pedido do dono (24/11/2026):** *"pode realizar um estudo do que temos do PDV Legal,
conseguimos a finalizadora da compra, se foi dinheiro, debito, credito, pix ..."*

Estado: **etapas 1 e 2 construídas em 24/11/2026** (1.3.20, migração 160); 3 e 4 por fazer. O
que foi decidido está em `docs/memoria/vendas.md`. O levantamento abaixo foi conferido contra a
conta real do cliente em 24/11/2026, só com leituras (`formapagamentopdv/get` e `cupom/get` de
20, 21 e 23/11), nenhuma gravação.

## 1. A resposta curta

**Sim.** Todo cupom válido traz a finalizadora, com o valor pago em cada uma. O sistema já
recebe esse dado a cada importação e **joga fora**: `mapeadores.cupom()` lê itens, total e
desconto, e ignora a lista `formaPgtos`. A tabela `vendas` não tem onde guardar.

Foram 96 cupons em 20/11, 93 em 21/11 e nenhum em 23/11 (domingo). Dos 189, 11 eram
cancelados, e **nenhum veio sem pagamento**.

Nos dois dias, por forma:

| Forma | Pagamentos | Valor |
|---|---|---|
| Crédito | 112 | R$ 17.738,37 |
| Débito | 41 | R$ 5.105,00 |
| Dinheiro | 14 | R$ 2.073,00 |
| Pix | 12 | R$ 1.000,00 |
| Pix web | 1 | R$ 610,00 |
| Vale-presente | 1 | R$ 150,00 |
| Troco | 11 | R$ 285,00 (sai do dinheiro) |

⚠️ Os valores incluem os 11 cupons cancelados, que também trazem pagamento. Na importação eles
ficam fora das somas, como já acontece com a receita.

## 2. O que vem, campo a campo

### As formas cadastradas — `GET formapagamentopdv/get`

Seis, todas ativas:

| `codigo` | `descr` | `classificacao` | `codclassificacao` |
|---|---|---|---|
| 1 | DINHEIRO | Dinheiro | 1 |
| 95239 | CREDITO | Cartão de Crédito | 3 |
| 95240 | DEBITO | Cartão de Débito | 4 |
| 95241 | PIX | PIX – Estático | 20 |
| 95310 | VALE PRESENTE | Vale Presente | 12 |
| 108159 | PIX WEB | Pagamento Eletrônico | 22 |

Em todas: `tef = false`, `taxacartao = 0`, `prazodias = 0`, `provedor` "Nenhum". **A maquininha
não é integrada ao PDV**: o operador escolhe "CREDITO" e passa o cartão num aparelho separado.

### O pagamento dentro do cupom — `formaPgtos[]`

```
cod                    int     identidade da LINHA de pagamento (não da forma)
codcupom               int     o cupom
codformarecebimentopdv int     = `codigo` da forma cadastrada (1, 95239…); TROCO = -1
codClassificacao       int     = `codclassificacao` (1, 3, 4, 20, 12, 22); TROCO = 1
nome                   str     "CREDITO", "DINHEIRO", "TROCO"…
nomeExterno            str     "Cartão de Crédito"; vazio no PIX e no troco
valortotal             float   o valor pago nesta forma
detalhes               list    VAZIO em 206 de 206
isFidelidade, codClienteContaAssinada, codRefExterna, codRefDetalhes   vazios em todos
```

### Três achados que decidem o desenho

1. 🔑 **O troco vem como LINHA, com valor positivo.** Cupom de R$ 163,50 pago com R$ 200:
   `DINHEIRO 200,00` + `TROCO 36,50`. A soma das formas só bate com o total descontando o troco,
   e nos 11 cupons em que ela não bateu, era sempre isso. Dinheiro que ficou na casa =
   dinheiro − troco.
2. **Pagamento dividido existe, e é raro.** Em 178 cupons válidos, um só: Pix R$ 5 + vale-presente
   R$ 150. Os outros dois que apareceram (débito + Pix, crédito + Pix) eram cupons cancelados.
3. **Cupom cancelado também traz pagamento** (11 de 11). Tem de ser guardado junto, para a
   conferência com o PDV fechar, e ficar fora de toda soma, a mesma regra de `vendas.cancelada`.

### O que NÃO vem

- **Bandeira, parcelas, NSU e autorização do cartão.** `detalhes` vem vazio, e sem TEF o PDV
  não sabe. Quem sabe é a maquininha (a adquirente).
- **A taxa do cartão.** `taxacartao` é zero no cadastro do PDV; a taxa real está no contrato com
  a adquirente.

## 3. O que dá para fazer com isso

| Uso | O que precisa | Valor para a casa |
|---|---|---|
| **Vendas por forma** (dia, semana, período) | só o dado novo | Quanto entrou em cartão, Pix e dinheiro, sem abrir o PDV |
| **Na venda**, mostrar como foi paga | só o dado novo | Conferência de um cupom |
| **Conferência do caixa**: dinheiro esperado na gaveta (dinheiro − troco) | só o dado novo | O fechamento do dia confere com um número |
| **Custo do cartão estimado** | taxa por forma, digitada | Quanto o cartão leva por mês |
| **Precificação com o mix real** | a taxa por forma, e o peso de cada forma nas vendas | A taxa de cartão da configuração deixa de ser um chute |
| **Conciliar com a maquininha** | extrato da adquirente (outra integração) | Fora do alcance deste dado |

## 4. Como construir — recomendação

**Tabela `venda_pagamentos`**, uma linha por pagamento do cupom, ligada à venda:

| Coluna | |
|---|---|
| `id_venda`, `id_unidade` | regra 5 do CLAUDE.md |
| `grupo` | DINHEIRO, CREDITO, DEBITO, PIX, VALE, TROCO, OUTRO |
| `nome_pdv`, `cod_forma_pdv` | "PIX WEB", 108159: o detalhe, para relatório e conferência |
| `valor` | `numeric(14,2)`, nunca float |

- 🔑 **O grupo sai de `codClassificacao`, não do nome.** O nome é texto que o cliente edita no
  PDV ("CREDITO" pode virar "CRÉDITO"); a classificação é do sistema. TROCO pelo
  `codformarecebimentopdv = -1`. Classificação desconhecida vira OUTRO e aparece num aviso,
  sem ser descartada.
- 🔑 **Troco guardado como veio**, e o relatório mostra o dinheiro LÍQUIDO (dinheiro − troco).
  Guardar já descontado perderia o que a gaveta recebeu, que é o número da conferência de caixa.
- **PIX WEB entra no grupo PIX**, com o nome "PIX WEB" preservado.
- Vocabulário: **um só para a casa**. Hoje há três parecidos (`receber.FORMAS`,
  `consumo.FormaPagamento`, `pedidos.como`), e "CARTAO" neles não separa crédito de débito.
  Os grupos acima entram como a lista da venda; os outros não mudam agora.

**A importação** (`mapeadores` → `importador` → `/vendas/importar`) passa a levar os pagamentos.
⚠️ **E precisa preencher vendas que JÁ existem**: hoje, reimportar um dia não mexe na venda já
gravada (a idempotência é pelo `documento`). Os pagamentos têm de ser gravados à parte, por
venda, apagando e regravando os daquela venda, para uma reimportação completar o que faltava.

**O histórico:** a base tem 1.764 vendas do PDV (de 26/08 a 24/11). Reler esse período dia a dia
custa uma chamada por dia, cerca de 90, sem teto de registros, e preenche tudo. Rodar pela agenda,
em segundo plano, e não num clique.

⚠️ **Planilha e lançamento à mão** continuam sem forma: a venda fica sem pagamentos, e o
relatório mostra "não informado" em vez de inventar.

## 5. Etapas

| Etapa | Entrega | Resolve |
|---|---|---|
| **1. Guardar** | Migração da tabela, mapeador, importação gravando e completando, histórico relido, a forma na tela da venda, testes | O dado para de ser jogado fora |
| 2. Ver | Vendas por forma no painel de vendas e num relatório (dia, período, canal), dinheiro líquido | **O pedido do dono** |
| 3. Caixa | Dinheiro esperado na gaveta por dia, para o fechamento conferir | Diferença de caixa com número |
| 4. Taxas | Taxa por forma na configuração da loja, custo do cartão estimado, mix real na Precificação | Quanto o cartão custa |

As etapas 1 e 2 fazem sentido juntas: só guardar não mostra nada ao dono.

## 6. Riscos e o que conferir antes

- ⚠️ **Só três dias foram lidos.** Antes de construir, rodar a leitura num mês inteiro e conferir
  se aparece classificação fora das seis, como Pix dinâmico, voucher ou conta assinada.
- ⚠️ **Conta assinada (fiado) e fidelidade** têm campos na linha (`codClienteContaAssinada`,
  `isFidelidade`), vazios nos três dias. Se a casa usar, viram um grupo próprio.
- ⚠️ **23/11 voltou sem cupom nenhum** direto do PDV (domingo). O alerta do ar "sem venda do PDV
  desde 21/11" pode estar contando dia em que a casa não abre; vale olhar à parte.
- `cupom/gettotalfilial` e `conferenciacaixa/getByCodigo` existem na API e podem trazer totais
  por forma e o fechamento de caixa do próprio PDV. Não foram chamadas; seriam a conferência
  da etapa 3.

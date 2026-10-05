# Precificação — estudo

🔑 **Pedido do dono (05/10/2026):** *"Inicia um estudo para uma página de Precificação. Podemos
ter uma de configuração, onde podemos ter se a configuração será desta empresa ou irá
considerar de outra, caso tenha mais de uma. Caso for de outra, nesta fica somente
visualização. Terá como informar custos sobre os produtos. Custo operacional e outros que o
usuário queira configurar. Também margens e outros percentuais cabíveis para este cálculo. Aí
na tela de precificação podemos ter algo para o usuário analisar e aplicar a precificação com
base nos estudos, podemos ter algo até relacionado a impostos, bacana seria bolar um protótipo
para vermos. E também uma tela de preços, exemplo, selecionar um produto e ver em forma de
gráfico de linhas a evolução de preço × custo."*

Estado: **análise, nada construído.** Protótipo navegável em
[`apresentacao/precificacao-prototipo.html`](../apresentacao/precificacao-prototipo.html), com
dados inventados e a conta de verdade rodando na página.

---

## 1. Para que serve

Hoje o sistema sabe **quanto custa** cada prato (ficha técnica, custo médio do razão) e **por
quanto ele é vendido** (`produto_precos`), e mostra a margem depois que a venda aconteceu
(*CMV ▸ Margem por prato*). O que ele não faz é a pergunta ao contrário: **por quanto este
prato DEVERIA ser vendido** para pagar o imposto, a maquininha, a casa aberta e ainda sobrar o
que o dono quer que sobre.

Três telas, três perguntas:

| Tela | Pergunta |
|---|---|
| **Configuração** | O que sai de cada real vendido, e quanto eu quero que sobre? |
| **Precificação** | Com isso, quais preços estão errados, e o que acontece se eu corrigir? |
| **Preços** | Como o preço e o custo deste produto andaram ao longo do tempo? |

## 2. A conta

É o *markup divisor*, que é como o ramo precifica:

```
                      custo direto do produto
preço sugerido = ─────────────────────────────────────
                  1 − (soma dos percentuais sobre a venda)
```

- **Custo direto** = o que o sistema já calcula (ficha técnica para o que se produz, custo médio
  para o que se revende) **+ custos por unidade** que a casa informar (embalagem, sachê,
  guardanapo), com um percentual de perda opcional por cima.
- **Percentuais sobre a venda** = tudo o que sai de cada real que entra: impostos, taxa da
  maquininha, custo operacional, o que mais a casa quiser configurar — **e a margem de lucro
  que ela quer**.

Exemplo: custo direto R$ 10,00; impostos 6%, cartão 2,5%, operacional 25%, margem 15% → soma
48,5% → preço = 10 ÷ (1 − 0,485) = **R$ 19,42**, arredondado para R$ 19,90.

⚠️ **Não é "custo + 48,5%".** Somar o percentual sobre o custo dá R$ 14,85, e aí o imposto e a
maquininha — que incidem sobre o PREÇO — comem a margem inteira. É o erro mais comum de
planilha, e o motivo de a conta ser uma divisão.

⚠️ **A soma não pode chegar a 100%.** Com 100% ou mais não existe preço que pague a conta; a
configuração recusa e diz por quê.

**A leitura ao contrário**, para o preço que já está praticado: de cada real, tira-se o custo
direto e os percentuais; o que sobra é o **lucro líquido do prato**, em reais e em percentual.
É esse número que a tela de Precificação pinta de verde, amarelo ou vermelho.

### O food cost como segunda lente

Muita casa precifica por *food cost alvo* (custo ÷ 30% = preço). As duas contas são a mesma
vista de dois lados: fixar a margem define o food cost, e vice-versa. A tela mostra os dois, e
a configuração aceita informar qualquer um — o outro é calculado.

## 3. Configuração

### 3.1 De quem é a configuração

O pedido fala em "empresa". No sistema existe **uma empresa com várias LOJAS** (`unidades`), e
é por loja que as coisas variam (preço, custo, estoque). Então:

- **Própria desta loja** — edita aqui.
- **Usar a de outra loja** — escolhe qual; nesta, a tela fica **só de leitura**, com o aviso de
  onde editar. É o caso da filial que segue a matriz.

🔑 É o mesmo desenho do preço e do custo, que já são "o da loja, senão o da casa". ⚠️ Trocar de
"usar a de outra" para "própria" **copia** a configuração herdada como ponto de partida —
começar do zero faria a loja ficar sem sugestão de preço até alguém preencher tudo.

### 3.2 Percentuais sobre a venda

Uma lista que a casa monta. Nasce com as linhas mais comuns e aceita outras:

| Linha | Padrão | Observação |
|---|---|---|
| Impostos | — | ver 3.5 |
| Taxa de cartão / maquininha | — | média ponderada de débito, crédito e Pix |
| Custo operacional | — | ver 3.3 |
| Comissão / taxa de serviço | — | se a casa paga comissão sobre a venda |
| *(outras que o usuário criar)* | | marketing, royalties, provisão de perdas… |

Cada linha tem nome, percentual e **onde vale**: tudo, uma categoria, ou um canal de venda (o
delivery por aplicativo tem uma taxa que o salão não tem — é ela que explica por que o mesmo
prato não pode custar igual nos dois).

### 3.3 Custo operacional

É o que a casa gasta para estar aberta — aluguel, folha, energia, contador — e que não está em
ficha nenhuma. Na conta ele entra como **percentual do faturamento**.

O sistema não tem o financeiro (isso mora no Omie), então a tela oferece uma **calculadora**:
a casa informa a despesa fixa mensal, o sistema traz o **faturamento médio dos últimos meses**
(esse ele tem, pelas vendas do PDV) e mostra o percentual. A casa aceita ou digita outro.

⚠️ **O número é uma média, e a tela diz isso.** Mês fraco faz o percentual subir; a
calculadora mostra os últimos meses lado a lado para a casa não precificar pelo pior deles.

### 3.4 Margem

- **Margem de lucro alvo** da loja (percentual sobre a venda).
- **Por categoria**, quando for diferente: café e bebida costumam carregar mais margem que
  prato principal. Categoria sem margem própria usa a da loja.
- **Arredondamento**: para ,90 · para ,00 ou ,50 · sem arredondar. ⚠️ Sempre **para cima** — a
  sugestão que arredonda para baixo entrega a margem que acabou de calcular.

### 3.5 Impostos

O imposto sobre a venda entra como **um percentual**, e é aqui que mora o maior risco de a
tela parecer mais sabida do que é.

- **Simples Nacional** (o caso da maioria das casas do ramo): a alíquota não é a da tabela, é a
  **efetiva**, que depende do faturamento dos últimos 12 meses e da faixa. A tela ajuda a
  calcular — informa-se o anexo e o faturamento acumulado, e ela aplica a fórmula oficial
  `(RBT12 × alíquota nominal − parcela a deduzir) ÷ RBT12`.
- **Exceções por categoria**: bebida com ICMS por substituição tributária ou tributação
  monofásica não paga de novo na venda; a alíquota efetiva daquele produto é menor. A
  configuração permite um percentual de imposto **por categoria**, que substitui o geral.

⚠️ **Isto é estimativa para precificar, não apuração fiscal.** O sistema não emite nota de
venda nem apura imposto (os campos fiscais moram no PDV — ver `docs/memoria/vendas.md`). O
percentual deve ser **confirmado com a contabilidade**; a tela registra quem informou e quando.
⚠️ **Reforma tributária (CBS/IBS)**: está em implantação gradual e vai mudar essa conta. O
desenho de "um percentual por loja, com exceção por categoria" comporta a mudança — troca-se o
número, não a tela —, mas o estudo não tenta modelar as regras novas.

### 3.6 Custos por unidade

O que acompanha o produto e não está na ficha: embalagem de viagem, sachê, canudo. Em reais
por unidade vendida, para tudo, por categoria ou por canal. ⚠️ Se a embalagem **já está na
ficha técnica**, não se informa aqui — entraria duas vezes. A tela avisa quando a ficha do
produto tem insumo do tipo EMBALAGEM.

## 4. Precificação — analisar e aplicar

Uma linha por produto vendido, com:

- **Custo direto** e de onde ele vem (ficha, custo médio, referência) — a mesma etiqueta de
  origem que o sistema já usa.
- **Preço atual** e **lucro líquido atual** (R$ e %), pintado pela distância da margem alvo.
- **Preço sugerido** pela configuração, e a **diferença** para o atual.
- **Vendido nos últimos 30 dias** — sem volume, a diferença de preço não diz o tamanho do
  problema.
- **Impacto no mês**: diferença × volume. É o que ordena a lista: um real a menos no café que
  vende 400 vezes pesa mais que dez reais no prato que vende quatro.

🔑 **A lista abre pelo que mais custa à casa**, não em ordem alfabética — o mesmo princípio da
fila de fichas ("Por onde começar").

🔑 **O sugerido é o PISO, não o alvo.** Ele é o menor preço que entrega a margem configurada.
Produto vendido ACIMA dele não é erro a corrigir: aparece com a **folga** (quanto o preço
poderia cair mantendo a margem) e sem caixa de marcar. A primeira versão do protótipo ordenava
pela diferença em módulo e punha no topo a sugestão de BAIXAR a cuca de R$ 14,00 para R$ 9,90 —
a tela respondendo o que ninguém perguntou. A folga é informação (cabe uma promoção?), não uma
ação.

**Abrindo um produto**: a decomposição do preço atual em barras (imposto, cartão, operacional,
custo, lucro), a mesma do sugerido ao lado, e um **simulador** — "e se o preço fosse R$ X?" —
que recalcula na hora.

**Aplicar**: marca-se os produtos, confere-se a prévia (quantos mudam, impacto estimado no
faturamento do mês com o volume atual) e confirma. Cada um vira um preço novo em
`produto_precos`, com data de vigência — que é o que alimenta a tela de Preços.

⚠️ **O volume é o de hoje, e a prévia diz isso**: subir preço pode derrubar venda, e o sistema
não sabe prever. O impacto é "se vender o mesmo".
⚠️ **Preço vai para o PDV.** A casa tem o envio de cadastro ao PDV (`Exportação para o PDV`);
preço aplicado aqui entra naquela fila como qualquer alteração de preço, e só vale no caixa
depois de enviado. A prévia avisa.
⚠️ **Produto sem custo não tem sugestão** — aparece com "—" e o link para a ficha. Sugerir
preço sobre custo zero seria o erro que o sistema inteiro evita.
⚠️ **Preço abaixo do custo direto** é destacado à parte, antes de tudo: aí não é margem
apertada, é prejuízo por unidade.

## 5. Preços — a evolução de preço × custo

O produto é escolhido pela **busca de cadastro padrão** (`components/busca-cadastro.tsx`): campo
de texto com a lupa — digita-se código ou nome, um resultado só já escolhe, vários abrem a
janela com ↑ ↓ e Enter. ⚠️ Combobox não serve aqui: com mais de mil produtos, uma lista para
rolar não é busca (corrigido no protótipo a pedido do dono, 05/10/2026).

Escolhido o produto, vê-se, em linhas, **o preço de venda e o custo** ao longo do tempo, na
mesma escala de reais. A distância entre as duas linhas É a margem bruta — vê-la abrir ou
fechar é o que a tela existe para mostrar.

- Abaixo, um segundo gráfico menor com a **margem em percentual** (gráfico à parte, e não um
  segundo eixo no mesmo: dois eixos no mesmo desenho inventam uma relação que não existe).
- **Marcas no tempo**: cada mudança de preço e cada compra que mexeu o custo.
- Tabela com os mesmos números, para conferir e exportar.

### De onde vêm as séries — e o que o sistema NÃO sabe

| Série | Fonte | Limite |
|---|---|---|
| Preço de venda | `produto_precos` (`vigente_de`/`vigente_ate`) | completo desde que o preço passou a ser gravado aqui |
| Custo do que se REVENDE | `estoque_movimentos.custo_medio_apos` | completo — o razão é a memória do custo |
| Custo do que se PRODUZ | `venda_itens.custo_ficha_unitario` (congelado em cada venda) | só nos dias em que houve venda, e só depois de a ficha existir |

⚠️ **O custo da ficha não tem série própria.** A ficha é versionada, mas o custo dela é
calculado na hora com o preço de hoje dos ingredientes. O que existe é o custo **congelado em
cada venda** — que é a fotografia certa (o que o prato custava no dia em que foi vendido), mas
tem buracos onde não houve venda. O gráfico liga os pontos e marca os dias sem dado; não
inventa linha onde não há.

⚠️ O preço que o PDV praticou pode diferir do cadastrado (promoção, desconto). A linha de preço
é a do **cadastro**; o preço médio realmente cobrado sai das vendas e pode entrar como uma
terceira linha, opcional — decisão em aberto.

## 6. O que seria construído

**Banco** (migração nova):

- `precificacao_config` — uma linha por loja: própria ou `id_unidade_origem` (de quem herda),
  margem alvo, arredondamento, quem alterou e quando.
- `precificacao_componentes` — as linhas da configuração: nome, tipo (`PERCENTUAL_VENDA` ou
  `VALOR_UNIDADE`), valor, e o alcance (tudo, categoria, canal).
- `precificacao_margens` — margem por categoria.

Nada novo para preço e custo: as séries saem do que já existe.

**Permissões:** `precificacao.configurar`, `precificacao.analisar`, `precificacao.aplicar` —
quem enxerga a margem de cada prato não é necessariamente quem muda o cardápio.

**Regras da casa que valem aqui:** dinheiro em `numeric`, percentual também (nunca float); a
conta mora num serviço só (`services/precificacao.py`) e a tela não recalcula — o simulador
pede ao servidor ou usa a MESMA função exposta; toda rota declara permissão; aplicar preço é
auditado.

**Ordem sugerida:** (1) tela de Preços — só leitura, dado que já existe, valor imediato;
(2) Configuração; (3) Precificação com prévia; (4) aplicar em lote e a ponte com o PDV.

## 7. O que precisa ser decidido

1. **"Empresa" ou loja?** O estudo assume configuração **por loja**, com a opção de usar a de
   outra loja. Se a intenção era entre empresas diferentes (clientes diferentes do sistema),
   muda o desenho — hoje cada cliente tem a própria instalação.
2. **Custo operacional**: percentual único da loja (o estudo assume) ou rateio diferente por
   categoria/setor?
3. **Imposto**: um percentual geral com exceção por categoria é suficiente, ou a contabilidade
   da casa trabalha com outra divisão? Vale levar a pergunta à reunião com a contabilidade.
4. **Canais**: precificar separado salão × delivery já na primeira versão, ou começar com um
   preço só?
5. **Quem aplica**: o preço aplicado vale na hora no sistema e vai para a fila do PDV, ou
   precisa de uma etapa de aprovação?
6. **Preço praticado**: a tela de Preços mostra também o preço médio realmente cobrado nas
   vendas (com desconto), ou só o do cadastro?
7. **Onde mora no menu**: grupo próprio "Preços", ou dentro de CMV?

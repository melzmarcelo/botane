# Módulo de Etiquetas — estudo

🔑 **Pedido do dono (28/09/2026):** *"inicia um novo estudo. Será um novo módulo. Vamos fazer
algo integrado e que conseguimos controlar tudo de forma simples e rápida. Este novo módulo é
o de Etiquetas, onde, para melhor controle, vamos criar etiquetas para controlar validade,
quantidade e demais coisas úteis, em produtos produzidos e abertos para consumo."*

Estado: **construído em 28/09/2026** (migração 100) — o que foi decidido está em
`docs/memoria/etiquetas.md`. Abaixo, o estudo como foi escrito.

Estado original: **análise, nada construído.** Este documento diz o que a etiqueta precisa ter, o que o
Botané já sabe e só não imprime, como ela entra no dia da cozinha sem atrasar ninguém, como se
imprime, e o que precisa ser decidido.

---

## 1. Para que serve (e por que integrado)

Uma etiqueta de validade feita à mão — caneta, fita crepe — responde "quando isto vence?".
Integrada ao Botané, ela responde também:

- **O que vence hoje e amanhã, e onde está** — sem abrir a câmara fria para ler potes.
- **Quanto se jogou fora, de quê e por quê** — o descarte pela etiqueta vira perda no estoque,
  com o valor, em vez de sumir.
- **De qual produção veio** — o pote leva o lote; o lote leva a ficha, o dia e quem fez.
- **Quem manipulou** — o que a vigilância sanitária pergunta.

## 2. O que a etiqueta precisa ter

A regra sanitária para serviços de alimentação (**RDC 216/2004 da Anvisa**) pede que alimento
preparado, fracionado ou retirado da embalagem original seja **identificado com o nome, a data
de preparo (ou de abertura) e o prazo de validade**. As vigilâncias locais costumam cobrar
também a **forma de conservação** e o **responsável**. ⚠️ Conferir com a nutricionista /
responsável técnica da casa o que a vigilância de Blumenau exige — o Botané deixa os campos
configuráveis justamente por isso.

| Campo | Produção | Abertura |
|---|---|---|
| Nome do produto | ✓ | ✓ |
| Data e hora de preparo / de abertura | ✓ | ✓ |
| **Validade (data e hora)** | ✓ pela conservação | ✓ "após aberto" |
| Conservação (refrigerado, congelado, ambiente) | ✓ | ✓ |
| Responsável | ✓ | ✓ |
| Lote | ✓ (o da produção) | ✓ (o do fabricante, se houver) |
| Quantidade / peso do recipiente | ✓ | opcional |
| Validade original do fabricante | — | ✓ |
| Alergênicos | ✓ (da ficha técnica) | opcional |
| QR code | ✓ | ✓ |

## 3. Os tipos de etiqueta

1. **Produção** — ao produzir: o molho, a massa, o recheio. A validade sai da conservação
   escolhida (refrigerado 3 dias, congelado 30…). Uma produção pode gerar várias etiquetas
   (**porcionamento**: 10 L de molho em 5 potes de 2 L, cada um com a dele).
2. **Abertura** — insumo industrializado aberto: o creme de leite, o leite, o molho de tomate.
   A validade é a "após aberto" do produto, **nunca maior que a do fabricante**.
3. **Descongelamento** — o que sai do congelado para o refrigerado ganha validade NOVA (e
   curta), e a etiqueta antiga deixa de valer.
4. **Reetiquetagem** — o pote que foi transferido, dividido ou mudou de conservação.

Fora do início: a etiqueta de **produto embalado para venda** (com tabela nutricional e
rotulagem da RDC 429/2020) — é outra regra e outro formato.

## 4. O que o Botané já tem — e o que falta

| Já existe | Serve para |
|---|---|
| `produtos.perecivel`, `validade_dias`, `controla_lote`, `controla_validade` | o ponto de partida da validade de cada produto |
| **Lotes com validade** (`estoque_lotes`), saída **FEFO** (vence antes, sai antes) | a etiqueta de produção vira um LOTE de verdade |
| Alerta de vencimento (`alerta_validade_dias`) e a lista "Vencimentos" | "o que vence nos próximos dias", no Início e no Claude |
| Produção pela ficha (`estoque.produzir`), com rendimento e porções | o momento natural de imprimir |
| Ficha técnica com **alergênicos** | o campo de alergênicos da etiqueta, sem redigitar |
| Locais de estoque (câmara fria, seco, freezer) | "onde está" |
| Perda no razão (`SAIDA_PERDA`, com motivo) | o descarte pela etiqueta |
| Gerador de QR e PDF (`reportlab`, tela de QR codes) | a própria etiqueta |

⚠️ **O que falta, e é o centro do módulo:**
- **A produção não cria lote nem validade hoje** — o produto feito na cozinha entra no
  estoque sem data. O FEFO e o alerta de vencimento só funcionam para o que veio de nota.
- **Validade por conservação**: um número só (`validade_dias`) não diz que o molho dura 3 dias
  refrigerado e 60 congelado, nem quanto dura depois de aberto.
- **A etiqueta como registro**: hoje não há o que escanear, consultar ou dar baixa.

## 5. Como fica no dia da cozinha — "simples e rápido"

**Tela Etiquetas** (pensada para tablet ou celular na bancada):
1. Busca o produto (ou toca num dos **favoritos** da cozinha).
2. Escolhe **o que aconteceu**: produzi · abri · descongelei.
3. Escolhe a **conservação** (já vem a padrão do produto).
4. Quantas etiquetas (e a quantidade de cada pote, se quiser).
5. **Imprimir.** Validade, lote, responsável e alergênicos já vêm preenchidos.

**Integrado à Produção**: ao lançar uma produção, o sistema **cria o lote com a validade** e
oferece "imprimir N etiquetas" na mesma tela — sem ir a outro lugar.

**O QR da etiqueta**, lido com o celular por quem tem login:
- mostra tudo (produto, lote, feito por, quando, vence, onde está);
- **"Usei tudo"** → a etiqueta sai das ativas;
- **"Descartar"** → pede o motivo (venceu, contaminou, sobrou) e lança a **perda** no estoque,
  com o valor. É isto que transforma "jogamos fora" em número.

**Painel de validades**: o que vence **hoje**, **amanhã** e **já venceu**, por local — a
lista para a checagem da manhã. E um aviso no Início: "4 etiquetas vencem hoje".

## 6. Como imprimir

| Caminho | Como | Prós | Contras |
|---|---|---|---|
| **PDF no tamanho da etiqueta** (recomendado para começar) | o navegador imprime numa impressora térmica de etiquetas com o driver instalado (Elgin L42 Pro, Zebra ZD220/ZD230, Argox…), rolo 40×40, 50×30 ou 60×40 mm | Nada para instalar além do driver; funciona com qualquer marca | Aparece a caixa de impressão do navegador a cada vez |
| **Impressão direta (ZPL/EPL) por um agente local** (QZ Tray, Zebra Browser Print) | um programa pequeno no computador da cozinha recebe a etiqueta e manda à impressora | Um toque, sem caixa de diálogo; o mais rápido | Instalar e manter o agente em cada computador |
| **Folha A4 de etiquetas adesivas** (Pimaco) | PDF em A4 | Qualquer impressora | Lento para o dia a dia; bom como reserva |

**Recomendação:** começar pelo **PDF no tamanho do rolo** (um modelo por tamanho) e, se a
caixa de impressão atrapalhar, passar para o agente local — o conteúdo da etiqueta é o mesmo.

## 7. Modelo de dados proposto

```
produto_validades   -- id_produto, evento (PRODUCAO | ABERTURA | DESCONGELAMENTO),
                    --   conservacao (REFRIGERADO | CONGELADO | AMBIENTE), prazo, unidade (HORAS | DIAS)
etiqueta_modelos    -- por loja: tamanho (40x40, 50x30, 60x40, A4), campos que aparecem, texto extra
etiquetas           -- o registro: codigo curto (o do QR), id_unidade, id_produto, evento,
                    --   conservacao, feito_em, vence_em (data E hora), quantidade + um,
                    --   id_lote (estoque_lotes), lote_fabricante, validade_fabricante,
                    --   responsavel, id_local, status (ATIVA | USADA | DESCARTADA),
                    --   id_movimento_descarte, impressoes
```

- A etiqueta de **produção** cria (ou usa) o **lote** em `estoque_lotes` com a validade — e o
  FEFO e o alerta passam a enxergar o que a cozinha produz.
- ⚠️ A etiqueta de **abertura** não mexe no estoque: o insumo continua no mesmo saldo; ela só
  diz que AQUELA embalagem foi aberta e vence antes.
- ⚠️ **Descartar é perda no razão** (append-only, regra 1), nunca apagar a etiqueta.
- Validade **com hora**: produto de 12 h ou 24 h (arroz, maionese caseira) vence no meio do dia.
- Permissões novas: `etiquetas.imprimir` (cozinha), `etiquetas.descartar`,
  `etiquetas.configurar` (validades e modelos).

## 8. O responsável, sem atrasar a cozinha

Quem imprime é quem está logado — mas a cozinha costuma ter **um tablet para todos**. Opções:
- **login de cada um** (o mais simples de construir, o mais lento na bancada);
- **PIN rápido de 4 dígitos por pessoa** no tablet da cozinha (troca de responsável em um
  segundo, sem sair da tela);
- **escolher o nome numa lista** (rápido, mas qualquer um escolhe qualquer nome).

## 9. Perguntas para o dono

1. **Impressora**: a casa já tem uma de etiquetas? Qual modelo e qual tamanho de rolo? Se não
   tem, o estudo recomenda uma térmica com rolo 60×40 mm (cabe tudo com QR legível).
2. **Validades**: a nutricionista / responsável técnica tem uma tabela da casa (produto →
   refrigerado / congelado / após aberto)? Ela vira a carga inicial.
3. **Quais produtos primeiro?** Os de produção própria (fichas) e uma lista de insumos que se
   abrem todo dia?
4. **Responsável**: login, PIN no tablet ou lista de nomes?
5. **Descarte pela etiqueta** com lançamento de perda — quer desde o início?
6. **Onde imprime**: um tablet/computador na cozinha, ou também no celular de cada um?
7. Todas as lojas ou uma para começar?

## 10. Ordem de construção sugerida

1. **Validades por conservação no produto** + a produção passa a criar **lote com validade**
   (o FEFO e o alerta de vencimento ganham a cozinha na hora).
2. **Tela Etiquetas** (produção e abertura) com **PDF no tamanho do rolo** e a etiqueta como
   registro.
3. **Imprimir na tela de Produção**, junto do lançamento.
4. **QR da etiqueta**: consultar, "usei tudo", **descartar com perda**.
5. **Painel de validades** e o aviso no Início; descongelamento e reetiquetagem.
6. Impressão direta (agente local), se a caixa do navegador atrapalhar.

# Layout e usabilidade — estudo

> Pedido do dono, 14/09/2026: *"gostaria de melhorar o layout do sistema… para
> deixar ele mais amigável e mais compatibilidade com as normas de UX. Deixando
> com letras amigáveis e bonitas. E deixando a funcionalidade mais simples no dia
> a dia. Tanto para computador quanto para celular."*
>
> **Isto é um estudo, não uma especificação fechada.** Nada foi mudado no
> sistema. O que está aqui saiu de medição sobre as telas REAIS — a bateria do
> navegador fotografa 108 telas a cada rodada, e a paleta foi medida contra a
> norma, não contra o gosto.

---

## O que NÃO se deve mexer

Começo por aqui porque é o mais importante: **o sistema já tem identidade, e ela
é boa.** Um "redesign" que a jogue fora troca uma tela com personalidade por mais
um painel administrativo cinza — e o histórico deste projeto mostra que as
escolhas visuais foram feitas com motivo, não por acaso.

- **A paleta de papel e erva.** O verde do papel e o verde-erva das ações são a
  casa. `docs/memoria/_transversais/padroes-de-ui.md` registra por que o raio foi
  de 4px para 14px e por que a sombra é dupla — *"sombra única e escura é o que
  faz uma tela parecer de 2012"*. Continua verdade.
- **Os números em monoespaçada.** Quantidade, dinheiro e código alinham pela
  direita e em `IBM Plex Mono`. É o que faz uma coluna de preços ser conferível.
- **A serifada nos textos que se LEEM.** As frases explicativas de cada tela
  (*"Tudo o que entra e sai da casa…"*) são o que diferencia este sistema de um
  ERP mudo. Elas ficam.
- **O sublinhado nos links.** Ele parece ruído, mas é acessibilidade: a norma
  (WCAG 1.4.1) proíbe distinguir link **só** por cor. A proposta abaixo **não é
  tirar o sublinhado** — é reduzir quantas coisas são link.

---

## O que a MEDIÇÃO encontrou

Quatro achados objetivos. Não são preferência: são a norma, e três deles são
consertos de uma linha.

### 1. Duas cores do sistema não passam no contraste de corpo

Medido em `#fcfdfa` (a superfície dos cartões), pelo cálculo do WCAG 2.1. A
norma pede **4,5** para texto de corpo e 3,0 para 18px ou maior.

| Cor | Onde é usada | Sobre superfície | Sobre papel |
|---|---|---:|---:|
| `tinta` | texto principal | 16,44 ✅ | 13,08 ✅ |
| `erva` | links e ações | 6,30 ✅ | 5,01 ✅ |
| `erro` | perdas, negativos | 7,39 ✅ | 5,88 ✅ |
| `suave` | texto secundário | 5,44 ✅ | **4,33** ⚠️ |
| `latao` | destaques | **4,44** ⚠️ | **3,53** ⚠️ |
| `alerta` | avisos, etiqueta "rascunho" | **4,06** ⚠️ | **3,23** ⚠️ |

⚠️ **O `alerta` é o pior caso e o mais usado no lugar errado**: ele pinta a
etiqueta "rascunho", que é **11px**. Texto pequeno é onde a norma é mais exigente,
e é justamente onde a cor mais fraca está.

🔑 **O conserto é escurecer duas cores**, não trocar a paleta. `alerta` de
`#a9711a` para algo perto de `#8a5d12` passa dos 4,5 mantendo a mesma família.

### 2. A borda dos campos está abaixo da norma — por muito

`linha2` (`#bfc8b6`) sobre a superfície dá **1,69**. A WCAG 1.4.11 pede **3,0**
para a fronteira de um elemento de interface. Ou seja: a borda que diz "aqui é um
campo onde se digita" quase não existe para quem enxerga pouco — e, num
formulário, é ela que separa o campo do fundo.

### 3. No iPhone, focar um campo dá ZOOM — e o sistema já sabe disso

`.campo` tem `font-size: 15px`. O Safari do iPhone dá zoom automático ao focar
qualquer campo abaixo de 16px, e a tela salta.

🔑 **O mais interessante é que a regra já está escrita no próprio CSS**, em
`.campo-toque`:

> *"16px não é estética: abaixo disso o Safari do iPhone dá zoom ao focar, e a
> tela salta a cada produto contado."*

Só que `.campo-toque` é **opt-in** e está aplicado praticamente só na contagem de
inventário. Todo o resto do sistema — nota, produto, ficha, reserva — salta no
celular. ⚠️ Não é um problema novo a descobrir: é uma regra que a casa já
aprendeu e aplicou em uma tela só.

### 4. Os alvos de toque estão no limite exato

`.link-acao` mede **24,5px** de altura (12,5px de texto + 10 de respiro + 2 de
borda). A WCAG 2.5.8 pede 24×24 como mínimo **absoluto**; a recomendação de
conforto (2.5.5) é 44×44. E na lista de compras esses links aparecem **três lado
a lado** ("vincular", "criar produto", "não controla estoque") numa linha de
tabela.

---

## O que as TELAS mostram

Além da norma, o que salta ao olhar as fotos da bateria.

### Na lista de produtos (a tela mais usada do sistema)

- 🔑 **Três ênfases no mesmo texto.** O nome do produto é serifada + **negrito** +
  sublinhado, tudo junto, em 20 linhas seguidas. Qualquer uma das três já diria
  "isto é clicável". As três juntas fazem a lista parecer um texto grifado à mão.
- ⚠️ **Cinco colunas de travessão.** TIPO, CATEGORIA, SETOR, UN. e PREÇO ocupam
  cerca de 40% da largura útil e estão quase todas vazias. Coluna que quase
  sempre é "—" não deveria custar largura: ela cabe na própria linha do produto,
  em letra menor, só quando tiver valor.
- ⚠️ **A altura da linha é irregular.** A etiqueta "rascunho" quebra para a
  segunda linha nos nomes longos, e o ritmo da tabela se perde — o olho deixa de
  poder descer em linha reta.
- ⚠️ **Duzentos pixels antes do primeiro dado.** Título, parágrafo de duas linhas
  e três botões vêm antes da primeira linha da tabela. Numa tela que se abre
  vinte vezes por dia, isso é rolagem repetida.

### No celular

- ⚠️ **A tela inicial tem 2.795px de altura.** São sete cartões empilhados, um
  número em cada. Não existe "o dia num relance": para ver o food cost é preciso
  rolar três telas.
- ⚠️ **Toda linha é um link sublinhado.** Em "Precisa da sua atenção" e "A casa
  hoje" são catorze sublinhados seguidos.
- ✅ **O que está certo**: os números grandes em monoespaçada funcionam muito bem
  no celular, e o vermelho do food cost acima de 100% comunica sem legenda.

---

## A proposta, em quatro movimentos

Na ordem em que eu faria — do mais barato e mais valioso para o mais caro.

### 1. Conformidade (uma tarde, risco quase zero)

Não muda o desenho de nada; só conserta o que está fora da norma.

- Escurecer `alerta` e `latao` até passarem de 4,5.
- Escurecer `linha2` até passar de 3,0 como borda de campo.
- **`.campo` vai para 16px** e `.campo-toque` deixa de existir — a regra passa a
  valer em todo o sistema, que é o que ela sempre quis dizer.
- `.link-acao` sobe para 28px de altura e ganha respiro entre irmãos.

⚠️ Subir o corpo dos campos de 15 para 16px **muda a altura de todo formulário**.
É pouco por campo e visível numa tela de vinte. É o único item desta etapa que
pede olhar as telas depois.

### 2. Tipografia: uma família a mais, não uma a menos

🔑 **O problema não é a serifada — é ela estar carregando trabalho que não é
dela.** `Newsreader` é bonita e funciona em frase corrida. Numa célula de tabela
com 12px, negrito e sublinhado, ela vira ruído.

A proposta é **dividir por função**, mantendo as três famílias que já existem:

| Onde | Hoje | Proposta |
|---|---|---|
| Título de tela | Bricolage Grotesque | **fica** |
| Frase explicativa | Newsreader (serifada) | **fica** — é a voz da casa |
| Linha de tabela, campo, menu | Newsreader (serifada) | **sem-serifa de leitura** |
| Número, código, hora | IBM Plex Mono | **fica** |

⚠️ **Isto é a mudança mais visível do estudo**, e a que mais precisa do seu
aval: o sistema vai parecer mais "de trabalho" nas listas e continuar com
personalidade nos textos. É exatamente a divisão que jornal faz — manchete e
olho em serifada, tabela de resultados em sem-serifa.

### 3. Densidade: a tabela mostra o que existe

- **Coluna quase vazia sai da tabela** e vira detalhe da linha, abaixo do nome,
  em letra menor. A lista de produtos passa de 8 colunas para 4.
- **Uma ênfase por texto**: o nome do produto fica sem negrito e sem sublinhado
  de base — sublinha no `hover` e no foco, e a cor `erva` o distingue. ⚠️ Isto só
  vale porque a linha inteira passa a ser clicável, e aí o sublinhado permanente
  deixa de ser a única pista.
- **Cabeçalho de tela em uma linha**: título e botões na mesma altura, e a frase
  explicativa recolhida atrás de um "o que é isto?" — ela ensina na primeira
  semana e estorva na terceira.

### 4. Celular: o dia cabe numa tela

- A tela inicial troca sete cartões empilhados por **um bloco de quatro números**
  (vendas, food cost, CMV, perdas) em grade 2×2, e as listas longas viram
  acordeões fechados.
- **A barra inferior** com as quatro telas do dia a dia (Início, Estoque,
  Compras, Reservas) — no celular, menu que exige abrir gaveta é menu que não se
  usa.

---

## O que eu preciso de você

1. **A troca da fonte das tabelas** (movimento 2) é a decisão de verdade. As
   outras três são consertos que qualquer um aprovaria; esta muda o caráter das
   listas. O protótipo mostra os dois lados.
2. **Qual tela dói mais no dia a dia?** Eu escolhi Produtos e o Início do celular
   por serem as mais abertas, mas quem opera sabe melhor.
3. **A barra inferior no celular** muda a navegação inteira. Vale começar por
   ela ou deixar para depois do resto?

---

## O protótipo

[`apresentacao/ux-prototipo.html`](../apresentacao/ux-prototipo.html) — antes e
depois, lado a lado, nas duas telas escolhidas, com um interruptor para alternar
entre o desenho de hoje e o proposto. É para ir ajustando: o valor dele é você
apontar o que não gostou antes de qualquer linha de código mudar.

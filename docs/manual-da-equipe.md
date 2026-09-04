# Botané — manual da equipe

O que cada pessoa faz no sistema, no dia a dia. Uma página por rotina, sem
jargão. Se algo aqui não bater com a tela, a tela está certa e este texto está
velho — avise.

---

## Antes de tudo: por que registrar

O sistema existe para responder **quanto custou o que a casa vendeu**. Ele faz
essa conta de dois jeitos e compara:

- **pelo estoque** — o que entrou de compra, menos o que sobrou na prateleira;
- **pela receita** — o que cada prato vendido deveria ter consumido.

A diferença entre os dois números tem nome: **variância**. Ela é o que aparece
quando alguém serve porção maior que a ficha, quando um produto estraga sem
ninguém apontar, ou quando falta mercadoria. Nenhum dos dois números existe
sozinho — os dois dependem do registro de quem está no salão e na cozinha.

Registrar não é burocracia: é o que transforma "acho que a margem caiu" em
"o queijo subiu 18% e é isso".

---

## Primeiro acesso

1. Abra o endereço do sistema no navegador.
2. Entre com o e-mail e a senha que o administrador passou.
3. O sistema pede para **trocar a senha** — a que veio não é sua, é provisória.
4. Esqueceu a senha depois? Na tela de entrada, **"Esqueci minha senha"**. Chega
   um link no seu e-mail que vale 30 minutos e uma vez só.

**No celular:** abra o sistema no navegador e escolha "Instalar" (Android) ou
Compartilhar → "Adicionar à Tela de Início" (iPhone). Ele passa a abrir em tela
cheia, com ícone próprio, e o ícone tem atalho direto para o inventário.

---

## Conferente / estoque

### Quando a mercadoria chega

Menu **Compras → Notas de entrada**. Três caminhos, escolha o que couber:

| Situação | O que fazer |
|---|---|
| O fornecedor mandou o XML por e-mail | **Importar XML** — pode selecionar vários de uma vez |
| Compra no mercado, açougue, feira (só cupom) | **Digitar nota** |
| A nota já está no Omie | **Buscar no Omie** |

Depois de a nota entrar, **confira os itens**. Item que o sistema não reconheceu
aparece na fila de pendências: escolha o produto certo e marque **vincular**.
Da próxima vez que aquele fornecedor mandar o mesmo item, ele entra sozinho.

Item que não se controla em estoque (guardanapo avulso, serviço) → **"não
controla estoque"**.

Só depois de tudo conferido, **Lançar no estoque**. Enquanto houver item sem
produto, o botão fica desligado de propósito: nota lançada errada estraga o
custo de dois produtos ao mesmo tempo.

> **Por que o custo não é o valor da nota.** Uma caixa de 12 a R$ 60 com R$ 6 de
> frete custa R$ 5,50 a unidade, não R$ 5,00. O sistema faz essa conta sozinho —
> por isso o frete da nota importa.

### Lote e validade

Ao dar entrada em perecível, informe **lote e validade** se a embalagem trouxer.
Não é obrigatório, mas é o que faz o sistema avisar antes de vencer.

Na saída **você não escolhe o lote**: o sistema tira primeiro o que vence antes,
e diz qual foi — *"Saiu 6 do lote L338 (vence 08/09)"*. É essa frase que diz qual
pote pegar na prateleira.

### Contagem de inventário

Menu **Estoque → Inventário**.

1. **Abrir inventário** no local que vai contar.
2. Conte de verdade e vá digitando. **Nada muda no estoque enquanto você digita**
   — dá para parar no meio e voltar depois.
3. Precisa de papel? **Folha de contagem** — escolha **PDF**, que é o formato
   feito para imprimir. (Em contagem cega o papel também sai sem o esperado.)
4. No fim, **Fechar e ajustar**. Aí sim a diferença vira movimento, com o seu
   nome.

Antes de fechar, a tela mostra **o impacto em reais** da diferença. Número muito
alto quase sempre é erro de digitação (vírgula no lugar errado, unidade trocada)
— vale conferir antes de fechar.

### Perda

Menu **Estoque → Saldos e movimentos → Perda**. Sempre com **motivo**: quebra,
validade, erro de preparo, cortesia. O motivo é o que permite, no fim do mês,
separar "perdemos R$ 400" de "perdemos R$ 400 **em cortesia**", que são
problemas diferentes.

**Perda não apontada não desaparece** — ela reaparece como variância no fim do
mês, sem nome e sem responsável. Apontar é melhor para todo mundo.

### Mandar mercadoria para outra loja

Menu **Estoque → Ajustes → Transferência**. Escolha o produto, a prateleira de
onde ele sai e, no destino, a prateleira **da outra loja** — o nome da loja
aparece ao lado, para não confundir dois "Estoque".

Entre lojas isso vira uma **remessa**, e ela não é imediata:

- enquanto está no caminho, **a mercadoria continua contando no estoque daqui**.
  O saldo mostra quanto dele já está na estrada, para você não despachar duas
  vezes a mesma coisa;
- **quem recebe é a outra loja.** Ela abre a remessa em *Estoque → Remessas entre
  lojas*, confere item a item e dá entrada. Só nesse momento o produto sai daqui
  e entra lá;
- **o que não chegou vira perda desta loja**, com motivo. Não é punição: a
  mercadoria saiu da prateleira daqui, e fingir que ela ainda está faz a falta
  reaparecer na próxima contagem sem ninguém saber de onde veio;
- **desistiu antes de chegar? Cancele.** Nada foi lançado, então não há nada a
  consertar.

Dentro da **mesma loja** — da câmara para o seco, por exemplo — continua sendo
imediato: alguém carrega a caixa e pronto.

---

### Quanto um produto custa, e desde quando

Abra o produto: o cartão **Custo** mostra o valor de uma unidade de estoque e,
embaixo, **de onde ele veio** — que é a parte que importa:

- **custo médio do estoque desta loja** — o que a casa pagou de verdade, com o
  frete já rateado dentro. É o melhor número que existe;
- **último preço pago ao fornecedor** — o que ela negociou, para quem ainda não
  teve entrada no estoque;
- **custo de referência, vindo de fora** — o que o Omie acha. Vale enquanto não
  houver melhor: na primeira nota daquele produto, o custo médio assume.

O botão **Histórico** abre a lista do que mudou o custo, com a fonte de cada
linha. Só o **razão** é uma linha do tempo — cada movimento guarda o custo médio
depois dele. Fornecedor e referência guardam apenas o valor de agora.

⚠️ **Sem custo aparece "—", não R$ 0,00.** Zero diria que o produto não custa
nada, e é justamente o número que faz o food cost parecer melhor do que é.

---

### Produto sem custo: trazer do Omie

Produto que nunca teve nota lançada aqui não tem custo — e sem custo ele entra
na ficha e no CMV **valendo zero**, o que faz a margem parecer melhor do que é.

Em **Integrações**, o botão **Trazer o custo inicial** busca o custo médio que o
Omie tem e o grava nos produtos que aqui não têm custo nenhum. Antes de gravar
ele mostra a lista e o total; o botão de aplicar vem depois.

⚠️ **Isso não mexe no estoque.** Nenhum saldo muda e nada entra no razão — é só
um custo de referência, para a conta poder ser feita. O custo médio das notas
lançadas aqui e o preço negociado com o fornecedor continuam ganhando dele.

⚠️ Rodar de novo só alcança quem continua sem custo.

⚠️ **Ele também acerta as vendas antigas que entraram valendo zero.** Um prato
vendido antes de ter custo ficou registrado sem nenhum, e contava zero no CMV
teórico. Ao trazer o custo, esses itens passam a contar o que custam, e a
mensagem diz quantos foram. **Item que já tinha custo não é tocado** — aquele
número é o do dia da venda — e **mês fechado fica de fora**, porque já foi ao
contador.

⚠️ Isso só alcança o prato que **tem ficha**: é a receita que transforma o custo
do insumo em custo do prato. Prato sem ficha continua sem custo — que é
diferente de valer zero, e é assim que deve ser.

---

### A busca de notas traz os produtos novos junto

O botão **Buscar notas novas**, em Integrações, traz **primeiro o catálogo** e
depois as notas. Assim o produto que nasceu no Omie hoje já existe aqui quando a
nota dele chega, em vez de cair na fila de pendências esperando alguém importar
o catálogo à mão.

⚠️ **Por isso ela demora alguns minutos** — são milhares de produtos, uma página
de cada vez. A busca automática da madrugada faz o catálogo **uma vez por dia** e
as notas em toda passada.

⚠️ Falhar no catálogo não impede as notas de entrar: nota que não entra é compra
faltando no estoque, e isso é pior que um cadastro que espera mais um dia.

---

### Por que o PDV mostra mais cupons que o Botané

Não mostra mais: mostra a mesma coisa contada de outro jeito. O PDV conta os
**cupons emitidos**, incluindo os cancelados; o Botané conta as **vendas**.

O painel do dia diz a conta em português — *"10 cupom(ns) cancelado(s) no PDV,
somando R$ 1.529,00 — lá o dia tem 164 cupons"*. Some os dois e o número do PDV
aparece.

Os cancelados **entram no sistema, marcados**: aparecem na lista de vendas
esmaecidos, não baixam estoque e não entram em receita nem no CMV.

⚠️ **O desconto do cupom também vem.** O valor que o Botané mostra é o que a
casa recebeu, não a soma das etiquetas — é por isso que ele bate com o PDV no
centavo.

Para conferir um dia, use o **filtro de dia** na tela de Vendas.

---

### O cupom mostra o nome do PDV

Ao abrir uma venda, cada linha traz o nome do jeito que ele aparece no PDV — é o
que o caixa e o cliente viram. Quando esse nome é diferente do nome do cadastro,
o do cadastro aparece logo abaixo, marcado como **cadastro:**, para você saber em
que produto a linha caiu ao conferir.

Produto lançado à mão aqui nunca teve nome de PDV: nesse caso a linha mostra o
nome do cadastro mesmo.

---

### Prato novo no PDV aparece aqui sozinho

Toda busca de vendas traz os cadastros junto: o prato que nasceu no cardápio do
PDV é criado aqui como **rascunho**, e o que foi desligado lá fica **inativo**
aqui. Não precisa fazer nada — mas o prato novo entra sem ficha, e prato sem
ficha não tem custo. Ele aparece na fila de "produzido sem ficha".

⚠️ **O que a busca NÃO faz é alinhar o resto.** Nome curto, categoria, setor,
unidade e preço continuam como estão aqui — se você corrigiu a categoria de um
prato à mão, ela fica. Para trazer tudo do PDV de uma vez, use o botão
**Importar cardápio**, em Integrações: aí sim ele sobrescreve.

⚠️ Produto que apenas **some** da lista do PDV não é desativado aqui. Só o que
vier marcado como desligado. A lista do PDV já veio incompleta sem avisar, e
desativar por ausência apagaria dezenas de pratos de uma vez.

---

### A busca automática, e o que ela promete

Em **Integrações** você escolhe se o sistema procura as notas do Omie e os cupons
do PDV sozinho: **manual**, **a cada hora** ou **uma vez por dia**, na hora que a
casa escolher.

**"Uma vez por dia" quer dizer *a partir* daquela hora, não *só* naquela hora.**
Se o sistema estiver fora do ar às 4h — uma publicação, um reinício, o computador
desligado —, a busca daquele dia acontece assim que ele voltar. Antes ela
simplesmente não acontecia, e nada dizia isso: a tela mostrava a última
sincronização, que uma busca manual tinha atualizado, e a agenda parecia em dia.

⚠️ Mesmo depois de dias parado, ela roda **uma vez**, não uma por dia perdido: a
janela da busca cobre o período inteiro de uma vez só.

⚠️ **Buscar no botão não dispensa a busca do dia.** A cota diária é do
agendamento: quem clica em *Buscar* está pedindo agora, não abrindo mão da
passada da madrugada.

---

### O mesmo produto em embalagens diferentes

O fornecedor manda o açúcar de confeiteiro em pacote de 1 kg e às vezes em
pacote de 500 g — e para ele são **produtos diferentes**, com códigos
diferentes. Aqui os dois são o mesmo produto.

Junte os dois cadastros com o botão **Vincular**. Feito isso, abra o produto e
vá ao cartão **Códigos de fora, e quanto cada um vale**: cada código aparece
com o que ele é lá e de onde veio. No do pacote de 500 g, informe a conversão
**0,5** — quer dizer *"uma unidade deste código é meio quilo"*.

⚠️ **A unidade de estoque tem de ser a medida, não a embalagem.** Açúcar em
`KG`, nunca em `PCT`: com o estoque contado em pacotes, o de 500 g não teria como
ser representado, e a ficha técnica consome em gramas.

⚠️ **Por padrão a conversão é 1**, e códigos que ninguém informou aparecem como
*"não informada"*. Informar 1 também vale — é uma afirmação, e o sistema passa a
tratá-la como tal.

⚠️ **Vale da próxima nota em diante.** O que já foi lançado não muda: a entrada
antiga ficou com a quantidade que se acreditava na época, e corrigir isso é
estorno, à mão.

---

### O mesmo produto com vários códigos

O catálogo do Omie cria **um cadastro por código** — e o mesmo abacate aparece uma
vez para cada fornecedor que já o vendeu. Para juntar tudo num produto só há dois
caminhos, e eles não são a mesma coisa:

Abra o cadastro que vai ser o **principal** e clique em **Vincular**, no alto da
tela. Procure o outro cadastro, e **vá acrescentando quantos quiser** — cada um
vira uma etiqueta na lista.

Antes do botão, a janela mostra:

- **Fica** e **Sai (vira inativo)** — quem sobrevive e quem é absorvido;
- **Como fica** — com que nome o produto vai ficar;
- **Códigos que passam a cair neste cadastro** — a lista dos códigos de fora que
  o principal vai responder depois da fusão.

⚠️ **O código do Omie de cada absorvido não se perde**: ele passa a apontar para o
principal. É por ele que a próxima nota daquele fornecedor entra no cadastro
certo, sem criar o duplicado de novo.

⚠️ **Cadastro com história não é absorvido.** O que já recebeu nota lançada tem
movimento no estoque, e a janela recusa com o motivo — juntar duas histórias
exigiria reescrever o razão, que não se reescreve. Para esses, o caminho é a
própria nota: no item pendente, **vincular** ao produto certo com a caixinha de
aprender marcada. Da próxima vez ele entra sozinho, e o estoque entra no
principal.

⚠️ O sistema **nunca adivinha** que dois cadastros são o mesmo produto. Quem
reconhece é você.

---

### Muitos cadastros com o mesmo nome, de uma vez

Menu **Administração → Integrações**, cartão **Cadastros com o mesmo nome**,
botão **Mesmo nome**. Fica ali, e não em Produtos, porque o repetido não é erro de
quem cadastra: ele nasce das importações. O catálogo do Omie cria um cadastro por
código, então o mesmo abacate aparece uma vez para cada fornecedor que já o
vendeu — e o cardápio do PDV traz o dele. A tela lista os grupos de cadastros que
têm o nome **exatamente igual**, mostra qual fica e quais são absorvidos, e junta
o grupo num clique.

⚠️ **Confira os códigos antes de juntar. Nome igual não é prova.** Dentro do
catálogo do Omie quase sempre é o mesmo item — mas *VALE-PRESENTE* pode ser três
valores diferentes com o mesmo nome, e o importador corta nomes longos no tamanho
do campo, o que faz dois nomes diferentes chegarem iguais. **A fusão não tem
desfazer.**

⚠️ Grupo em que **mais de um** cadastro já tem movimento no estoque aparece
marcado e não se junta: unir dois históricos de estoque não é possível.

⚠️ Depois de juntar, **os códigos dos absorvidos continuam caindo no cadastro que
ficou** — é isso que faz a próxima nota daquele fornecedor entrar no lugar certo,
em vez de criar o duplicado de novo.

---

### O mesmo produto em vários setores

O açúcar chega e entra no **Estoque Central**. De manhã, cada setor leva o que vai
usar para o seu canto — e esse canto é um **local de estoque** com o nome dele:
"Bar", "Confeitaria", "Cozinha". No cadastro do local você diz **a que setor ele
pertence**; o Estoque Central fica sem setor, porque serve a todos.

O caminho no dia a dia:

1. A nota entra no **Estoque Central**.
2. De manhã, **Estoque → Ajustes → Transferência**: do Central para o local do
   setor. É imediata.
3. Durante a semana o setor gasta do que pegou — inclusive pela **produção**: ao
   produzir informando o local do setor, os insumos saem **do estoque dele**.
4. No fim, **um inventário por setor**: em *Inventário → Nova contagem*, filtre
   pelo local daquele setor e conte só o que está lá.

⚠️ Se o insumo **acabou** no local do setor, a produção busca no local padrão do
produto em vez de deixar o saldo negativo. É de propósito: uma receita usa leite
da câmara e café do seco ao mesmo tempo.

Em **Estoque → Saldos**, o seletor **Ver por** troca a pergunta:

- **prateleira** — onde está cada parte. É o que quem conta precisa.
- **produto** — quanto a loja tem no total, com o detalhe de cada prateleira e o
  setor dela embaixo. É o que quem compra precisa.
- **produto, todas as lojas** — só com mais de uma loja.

**Prepare o cadastro antes de operar.** Na tela do produto, o cartão **Onde este
produto fica** lista as prateleiras dele nesta loja, com o **saldo** e o **custo
médio** de cada uma. Ali você acrescenta os cantos dos setores sem esperar a
primeira transferência: escolha o local e clique em *Acrescentar*. Ele passa a
existir vazio, já pronto para receber a mercadoria e para entrar na contagem.

O cartão está **também na tela de cadastrar um produto novo** — é ali que se
decide onde ele vai morar. As prateleiras escolhidas são gravadas junto com o
produto, vazias.

⚠️ **Acrescentar um local não movimenta nada** — não é entrada, não vai para o
razão e não muda saldo nenhum. É só o cadastro dizendo que o produto mora ali.

⚠️ **Só sai da lista a prateleira VAZIA.** Com mercadoria, o sistema recusa e diz
quanto tem: o caminho é transferir ou lançar a saída primeiro. Apagar ali faria o
estoque sumir da vista sem nenhum movimento explicando para onde ele foi. E o que
já passou por aquela prateleira continua no razão depois de ela sair do cadastro.

⚠️ **O CMV por setor passou a somar pela prateleira de onde a mercadoria saiu**,
não pelo setor do cadastro do produto. Com o açúcar em quatro cantos, antes todo
o consumo dele ia para um setor só. Saída do Estoque Central — que não pertence
a setor nenhum — continua caindo no setor do produto.

---

### Os nomes são gravados em MAIÚSCULAS

Produto, fornecedor, setor, local, categoria e unidade de medida: o nome que você
digita é gravado em caixa alta, seja qual for a tela. O campo já mostra assim
enquanto você escreve.

Não é enfeite — é para a **lista poder ser lida**. Numa conferência de compra o
olho percorre a coluna procurando um item, e caixa alternada quebra essa
varredura. Como os nomes chegam de três lugares (o Omie, o cardápio do PDV e a
mão de quem cadastra), cada um com sua convenção, sem isso a mesma tela fica com
três jeitos de escrever.

⚠️ A **sigla** da unidade de medida e o **código** do produto não são tocados:
são chaves, e mexer neles quebraria o vínculo com as notas e o histórico.

⚠️ Observação, endereço e contato também ficam de fora: são texto para ser lido,
e em maiúsculas viram grito.

---

### Corrigir um setor, local, categoria ou unidade

Menu **Cadastros → Tabelas de apoio**. Cada linha tem **editar**: o registro
sobe para o mesmo formulário do cadastro, o botão passa a dizer **Salvar** e
aparece um *cancelar* ao lado.

⚠️ **Corrigir é melhor que desativar e criar outro.** O cadastro antigo continua
apontado por todo o histórico — nota, razão, ficha —, e criar um substituto
deixa metade do passado num nome e metade no outro.

⚠️ A **sigla** da unidade de medida não muda: é ela que produto, ficha e razão
guardam. Quem precisa de outra sigla cria outra unidade.

## Cozinha

### O painel já abre no que é seu

Ao entrar, o cartão **Para produzir** mostra o que está planejado para os
próximos sete dias — o que é para hoje, o que ficou atrasado e quanto de cada
coisa. Se o seu cadastro tem um setor marcado, a lista já vem só com o seu: quem
é da Confeitaria não precisa percorrer a agenda do Bar para achar as duas linhas
que são dela.

O botão **Abrir a agenda** leva à lista inteira, onde se marca o que foi feito.

⚠️ Não aparecendo nada, a frase diz se é a casa que não tem nada planejado ou se
é só o seu setor — as duas coisas são diferentes.

⚠️ Quem define o seu setor é quem cadastra os usuários. Se o painel está
mostrando setor que não é o seu, é lá que se corrige.

---

### Ficha técnica

Menu **Cadastros → Fichas técnicas**. A ficha diz o que entra em cada prato e
quanto rende.

- **Quantidade bruta** é o que sai do estoque; **líquida** é o que fica no
  prato. A diferença é a casca, a aparagem, o osso — e ela custa.
- Prato que usa outro prato (o molho da casa, a massa base) entra como
  **sub-ficha**, não como ingrediente solto.
- **Ficha homologada não se edita.** Mudou a receita? **Nova versão.** Editar a
  antiga reescreveria o custo de tudo que já foi vendido.
- **A foto do prato pronto** entra no cartão *Foto do prato*, e sai junto na
  ficha impressa — é ela que responde "está pronto?" para quem está montando.
  ⚠️ A foto é a única coisa que se troca mesmo com a ficha **publicada**: o
  prato só pode ser fotografado depois de feito. Ao criar uma versão nova, ela
  vem junto.

**Ficha em rascunho já custeia a venda — mas o sistema avisa.** A receita
escrita e ainda não homologada passou a valer para calcular o custo do prato
vendido. Antes ele entrava com **custo zero**, e o resultado era margem alta
demais e food cost bom demais, sem nada denunciando. Na tela da venda, o item
aparece com a origem *"ficha técnica em RASCUNHO"* e um aviso acima dos números
dizendo que aquele custo ainda pode mudar.

⚠️ **A homologada manda, sempre.** O rascunho só responde quando não existe
versão aprovada. Homologar não muda o custo das vendas já registradas: ele é
**congelado** no momento da venda, e é assim que o CMV do mês passado não se
reescreve sozinho.

⚠️ **Produzir continua exigindo ficha homologada.** Ali a receita tira
mercadoria do estoque de verdade — seguir uma versão não aprovada baixaria o
insumo errado.

### Produção

Menu **Estoque → Produção**. Escolha o prato e quanto vai produzir: o sistema
baixa os ingredientes pela ficha e dá entrada no produzido. Não precisa apontar
ingrediente por ingrediente.

### Apontar o que consumiu fora da ficha

Provou, queimou, refez? **Perda**, com motivo. É rápido e é o que mantém o
número honesto.

---

## Salão

Se as vendas vêm do PDV por planilha: menu **CMV → Vendas → Importar**. Cole ou
suba o relatório do dia. **Importar o mesmo arquivo duas vezes não duplica** —
pode repetir sem medo.

Item de venda que o sistema não reconhece fica marcado como **sem vínculo**.
Enquanto estiver assim, aquele prato não entra no custo teórico — vale avisar
quem cuida do cadastro.

---

## Dono / gerente

### O que olhar todo dia

Tela de **Início**: ela mostra o que precisa de atenção — produto abaixo do
mínimo, lote vencendo, nota parada esperando conferência.

### O movimento do último dia

Logo no alto da tela inicial: **Vendas do dia** — quantas vendas, quanto entrou e
o **ticket médio** (quanto cada cliente gastou em média). As setinhas ao lado da
data andam para trás e para a frente.

⚠️ **Ele abre no dia da última venda, não em hoje.** De manhã, ou num dia em que
a busca no PDV ainda não rodou, hoje é um dia sem venda nenhuma — e um cartão
zerado se lê como "a casa não vendeu", que é diferente de "ainda não importou".

⚠️ **As setas pulam para o próximo dia que TEM venda**, não para o dia seguinte
do calendário. Numa casa que fecha na segunda, avançar um dia mostraria zero. A
seta fica apagada quando não há para onde ir.

⚠️ Quando o dia na tela é o mais recente e não é hoje, o cartão avisa — é o sinal
de que falta importar as vendas de hoje.

### O que olhar todo mês

Menu **CMV → Painel de CMV**:

- **CMV real x teórico** e a **variância** entre eles. Variância grande e
  positiva = saiu mais do estoque do que as receitas explicam.
- **Cobertura de ficha**: quanto da receita vendida tem ficha. Cobertura baixa
  faz o teórico mentir por omissão — a variância parece enorme sem ser.
- **Curva ABC**: onde o dinheiro do estoque foi parar. Negociar preço na classe
  A muda o mês; na classe C, não muda nada.
- **Onde pesa e o que subiu**: o CMV por setor (cozinha x bar) e a lista do que
  subiu de preço, **ordenada pelo impacto em reais**. É a planilha para levar à
  conversa com o fornecedor — o botão "baixar esta tabela" gera o arquivo.

### Baixar: sempre a janela

Todo botão de **Baixar** abre uma janela antes de gerar o arquivo. Nela você
escolhe **o recorte** — o que faz sentido naquele relatório: locais, setores,
categorias, tipos de produto, produtos específicos, período — e **o formato**:

- **Planilha** para conferir e somar no Excel.
- **PDF** para ler, imprimir ou mandar por e-mail.

A **ficha técnica** também se imprime: na tela dela, **Imprimir ficha** — já vem
em PDF, com os ingredientes, o rendimento e o modo de preparo. É o cartão para
pendurar na cozinha. Quem não tem permissão de ver custo recebe a receita **sem
os valores**, igual à tela.

O rodapé da janela diz **quantas linhas vão sair** antes de você clicar. Se o
número estiver grande demais, estreite o filtro ali mesmo — é mais rápido que
abrir um arquivo de três mil linhas para descobrir que não era aquilo.

Deixar tudo em branco quer dizer **tudo**: nenhum filtro marcado não é "nada", é
"sem recorte".

### O que mandar para a contabilidade

Três documentos, e cada um responde uma pergunta diferente. Todos saem pelo botão
**Baixar**, em planilha ou em PDF.

**1. Memória de cálculo do CMV** — botão em *CMV*, ao lado do arquivo do contador.
É a apuração **aberta**: o estoque inicial item a item, as compras agrupadas por
nota, o estoque final item a item, e a conciliação. Cada quadro fecha com a linha
que ele explica.

⚠️ **A soma das notas fiscais não é a linha "Compras", e o quadro 4 explica por
quê.** A linha soma o que de fato entrou no estoque — com frete e IPI já
rateados por item —, tira o que é limpeza, embalagem e utensílio, e soma a
remessa recebida de outra loja. Sem esse quadro, quem soma as notas encontra
diferença e ela parece erro.

**2. Inventário valorizado** — botão em *Estoque*. O estoque **numa data**:
item, quantidade, custo unitário e valor, com o método de custeio declarado no
cabeçalho. É o documento do balanço.

⚠️ Ele conta **tudo o que a casa possui**, inclusive limpeza e embalagem — que
ficam de fora do CMV mas são patrimônio igual.

**3. Memória de cálculo por produto** — botão na tela do produto. Um insumo
movimento a movimento, com a **conta escrita em cada linha**:
`(saldo × médio + entrada × custo) ÷ novo saldo`. É a resposta para *"como você
chegou nesse custo unitário?"* — dá para refazer na calculadora.

⚠️ **Mande o período FECHADO.** O documento diz, no cabeçalho, se o período está
aberto — e período aberto ainda pode mudar depois de o arquivo sair daqui.

---

### Fechar o mês

No painel, **Fechar o mês**. Depois disso, lançamento com data daquele período é
recusado — é o que impede o número já apresentado de mudar sozinho. Reabrir
exige permissão e fica registrado.

---

### Quanto a empresa inteira tem

Em **Estoque → Saldos**, com mais de uma loja, marque **somar todas as lojas**. A lista
deixa de ser por prateleira e passa a ser por produto: quanto a rede tem, em que lojas
está e quanto vale — com uma coluna para cada loja.

O custo médio dessa linha é **ponderado**: valor total dividido pela quantidade total.
Não é a média dos custos das lojas, que daria o mesmo peso a um estoque grande e a um
pequeno.

⚠️ Você só soma as lojas que você enxerga. Quem trabalha numa loja só vê o total dela.

Abaixo da lista pode aparecer um aviso dizendo **quanto ficou de fora por o produto estar
inativo**. Não é erro: o painel da rede conta tudo o que está na prateleira, inclusive o que
foi descontinuado, porque é isso que o CMV precisa contar. A lista mostra o que se opera.
Marcando **incluir inativos** os dois números passam a ser o mesmo.

---

### Quem trabalha em qual loja

No cadastro do usuário, com mais de uma loja aberta, aparece **Onde trabalha**:

- **Todas as lojas** — o padrão, e o que vale para você e para quem circula entre elas;
- **Só estas lojas** — a pessoa não vê nem escolhe as outras no seletor do topo. Saldo,
  venda, contagem, remessa e apuração passam a ser só da loja dela.

Duas travas que existem de propósito:

- **você só dá acesso a loja que você mesmo enxerga.** Um gerente lotado na filial não
  consegue criar alguém com acesso à matriz;
- **você não reduz as suas próprias lojas.** Ficaria sem como voltar atrás — peça a outro
  administrador.

---

### De que setor cada pessoa cuida

No mesmo cadastro do usuário, o cartão **De que setor cuida**:

- **A casa toda** — o padrão, e o que vale para todo mundo hoje. Serve também
  para os setores que a casa criar depois;
- **Só estes setores** — o painel da pessoa passa a mostrar só a produção
  planejada para eles.

⚠️ **Isto não é permissão.** Ele diz de que parte da casa a pessoa cuida, para o
painel dela abrir no que interessa — não bloqueia tela nenhuma. Quem decide o que
alguém *pode fazer* é o **papel**, no cartão acima.

⚠️ Produto sem setor cadastrado aparece para todo mundo: ele não é de ninguém, e
escondê-lo o faria sumir do painel da casa inteira.

As mesmas duas travas das lojas valem aqui: você só põe alguém num setor que você
mesmo enxerga, e não reduz os seus próprios setores.

---

### Quem vê os valores

Os números de dinheiro do painel — custo do que saiu, food cost, o que está
parado na prateleira, perdas, o movimento do dia — só aparecem para quem tem a
permissão **Ver o painel de CMV**, em **Papéis e permissões**. Quem não a tem
abre o mesmo Início e vê a parte operacional: o que tem para produzir, os
alertas e as contagens da casa. **Não é um zero no lugar do valor — o valor
simplesmente não vai até lá.**

Hoje a têm Administrador, Gerente e Contador. Cozinha, Conferente e Salão não.
Para mudar, mexa no **papel**, não em cada pessoa.

---

## Perguntas que sempre aparecem

**Lancei errado, e agora?**
Movimento não se apaga — apaga-se com **estorno**, que cria o movimento
contrário e mantém os dois no histórico. Nota lançada errada: estorne o
lançamento, corrija o vínculo, lance de novo.

**O sistema deixou a saída passar sem saldo. Está errado?**
Não. A cozinha usa antes de a nota chegar, e travar a operação por causa disso
seria pior. O movimento fica marcado como **custo provisório**, e se acerta
quando a nota entra.

**Como eu acho todas as saídas com custo provisório?**
Em **Estoque → Movimentos**, marque **só custo provisório**. Cada linha que
aparecer é uma entrada que ainda não foi lançada — lançar a nota que falta
resolve as duas coisas de uma vez: o saldo volta ao lugar e o custo daquela
saída passa a ser o de verdade. Lista vazia é a boa notícia. O botão de baixar
aceita o mesmo recorte, e a planilha traz a coluna **Custo provisório**.

**Por que não vejo os valores?**
Custo é informação restrita por papel. Cozinha vê a receita e não vê o dinheiro.
Se você precisa ver, peça ao administrador.

**Contei errado e já fechei o inventário.**
Abra outro inventário e conte de novo: o ajuste novo corrige o saldo, e os dois
ficam no histórico. Não existe "desfazer" silencioso.

**Trabalho em duas lojas.**
O seletor de loja fica no alto do menu. Trocar de loja recarrega a tela: tudo o
que você vê a partir dali é daquela loja.

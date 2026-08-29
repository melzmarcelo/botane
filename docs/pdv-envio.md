# Enviar do Botané para o PDV — estudo

Aberto em **29/08/2026**. Nada construído ainda: este arquivo é o levantamento e
as decisões que precisam ser tomadas **antes** da primeira linha.

Hoje a integração com o PDV Legal é de **mão única**: lemos o cardápio, os
preços e as vendas. Escrever de volta abre um caminho que não existe hoje — e
abre junto a chance de estragar o sistema que a casa usa para vender.

---

## 1. A primeira coisa, e não é técnica: de quem é a conta

🔑 **[`pdv-legal-api.md`](pdv-legal-api.md) descreve a conta ERRADA.** A seção
"A conta do cliente" ainda diz *filial 37622, CAFE DA CLINICA LTDA, CNPJ
59.938.158/0001-50, Biguaçu* — que é a empresa de outra pessoa. A conta certa é
`client_id` **25527**, filial **30638**, BOTANE DELI E CAFE LTDA, CNPJ
45.304.800/0001-34, Blumenau/SC.

Isso já custou 46 vendas e 165 pratos de terceiro dentro da base, quando só
líamos. **Escrevendo, o mesmo erro cadastra produtos do Botané no PDV de outra
empresa** — e lá não há "cancelar importação": há um cadastro estranho no
sistema de vendas de alguém.

⚠️ **Regra para qualquer rota de escrita: conferir `GET filial/get` e comparar o
CNPJ (só os dígitos) com o da empresa ANTES de enviar qualquer coisa.** Não como
teste manual no dia da configuração — como guarda no código, a cada lote.

O arquivo de referência precisa ser corrigido junto com este estudo.

---

## 2. O que a API deixa escrever

São **64 rotas de escrita** nas 173 do catálogo. As que tocam neste assunto:

| Rota | Para quê |
|---|---|
| `POST produtos/save` | cadastra um produto novo |
| `PUT produtos/update` | altera um produto existente |
| `DELETE produtos/delete/{id}` | exclui — *"o campo ID pode ser o código interno ou externo"* |
| `POST produtos/saveunidades` | unidades de compra de uma **lista** de produtos |
| `POST produtos/saveImage` | a imagem do produto |
| `POST tabelapreco/save` | preço e impostos de um produto **numa filial** |
| `PUT tabelapreco/update` | altera preço e impostos de quem já tem tabela |
| `POST grupoprodutos/save` · `PUT …/update` | os grupos do cardápio (nossas categorias) |
| `POST impressoras/save` · `PUT …/update` | as impressoras (nossos setores) |

🔑 **"O campo ID pode ser o código interno ou externo"** aparece no `delete` e nos
`get/{id}` de produto e de grupo. Se isso valer também no `update`, o PDV aceita
ser endereçado pelo **nosso** código — e é esse o gancho que torna o envio
idempotente sem guardarmos o id deles. **Confirmar é a primeira pergunta
técnica do estudo.**

### O que NÃO se envia, e por quê

- **`cupom/save`** — gravar venda. A venda nasce no PDV; mandar cupom daqui
  criaria receita que não existiu no caixa.
- **`estoque/saveentrada` · `savesaida` · `savedevolucao`** — o PDV tem controle
  de estoque próprio. Alimentar os dois faz o saldo existir em dois lugares com
  regras diferentes de custo médio, e **a primeira divergência não teria dono**.
  O estoque é do Botané; o PDV que fique com a venda.
- **`usuariopdv/*`, `pontovenda/*`, `dispositivo/*`** — operação do PDV, não é
  assunto do Botané.

---

## 3. O caso de uso óbvio morreu na medição

O [`CLAUDE.md`](../CLAUDE.md) antecipava: *"existe saída, e ela é um write no PDV
— mandar o EAN daqui para os itens de mercearia"*. Os números de hoje:

| | |
|---|---|
| produtos ativos no Botané | 3.301 |
| já existem no PDV (têm `codigo_pdv`) | 534 |
| têm EAN aqui | 1.148 |
| **têm EAN _e_ existem no PDV** | **4** |
| REVENDA (a mercearia) | 120 |
| REVENDA **com EAN** | **3** |

Os 1.148 com EAN são quase todos **insumos vindos do Omie** — farinha, leite,
embalagem —, que não têm por que existir num cardápio de PDV. E a mercearia, que
era o alvo, tem EAN em três de 120 itens **do nosso lado também**.

⚠️ **Enviar EAN hoje beneficiaria quatro produtos.** Não é o primeiro trabalho a
fazer, e talvez não seja trabalho nenhum até alguém preencher os códigos de
barra da mercearia aqui — que é uma tarefa de cadastro, não de integração.

---

## 4. O caso de uso que sobra é o que fecha o ciclo do sistema

O Botané existe para responder **quanto custa o que se vende**. Ele calcula o
custo pela ficha, o CMV real pelo razão e o food cost. A conclusão natural disso
é uma decisão de **preço** — e hoje essa decisão não tem para onde ir: o preço
mora no PDV, e o Botané só o **lê** (`tabelapreco/get`, 629 de 630 preenchidos).

Enviar preço fecha o ciclo: o custo sobe, o food cost aperta, o dono decide a
margem no Botané, e o preço novo vai para o caixa **sem digitar duas vezes**.

Hoje há **721 produtos com preço** no Botané — e todos vieram do PDV.

🔑 **Mas isso exige uma decisão que não é técnica: quem passa a ser o DONO do
preço de venda.** Não pode ser os dois.

| | se o dono for o PDV (hoje) | se o dono for o Botané |
|---|---|---|
| quem digita | o operador, no PDV | quem decide margem, no Botané |
| o Botané | lê e nunca escreve | escreve e **para de ler** |
| risco | o preço nunca reflete o custo | um erro aqui vira preço errado no caixa |

⚠️ **O perigo de deixar os dois é concreto**: a importação do cardápio grava
preço em `produto_precos` "só quando muda". Com escrita ligada e leitura
mantida, um preço alterado no PDV voltaria por cima do que o Botané mandou, e o
próximo envio o desfaria de novo — dois sistemas brigando, e a tabela de preços
virando ruído em vez de "quando o preço subiu".

**Decisão pendente do dono.** Enquanto ela não existir, não há o que construir.

### O segundo caso, menor e sem conflito

**Prato novo criado no Botané ainda precisa ser digitado no PDV.** Quem monta
uma ficha técnica de um prato novo já descreveu nome, grupo e setor aqui; o
`produtos/save` evitaria a segunda digitação. Não há disputa de dono: o prato
nasce aqui, e o PDV é o destino. É o candidato mais seguro para o primeiro
envio de verdade.

---

## 5. Como o de-para aguenta a mão inversa

O vínculo hoje é (`services/pdv/vinculo.py`):

- `produtos.codigo_pdv` — o código **principal**, único e visível na tela
- `codigos_externos` com `sistema = 'PDV_LEGAL'` — os **apelidos** (33 hoje;
  `ENTREGA` sozinho tem quatro códigos apontando para o mesmo produto)

⚠️ **Na leitura, apelido é solução; na escrita, é ambiguidade.** Ao enviar um
produto que tem quatro códigos lá, **para qual deles se escreve?** A resposta
provável é "o principal, e só ele" — mas isso precisa estar decidido e escrito,
senão o primeiro produto com apelido vira um envio que ninguém sabe onde caiu.

⚠️ **Produto sem `codigo_pdv` é `save`; com, é `update`.** E o `save` tem de
devolver o código para gravarmos — senão o envio seguinte cria um duplicado, que
é o defeito que o botão **Vincular** existe para consertar depois.

---

## 6. O que ainda não sabemos, e como descobrir barato

O catálogo em `pdv-legal-help.html` é só o **índice**: 173 rotas com uma linha de
descrição cada, sem os corpos. Os modelos estão nas páginas de detalhe do
próprio `/help`, uma por rota:

```
GET /Help/Api/POST-produtos-save
GET /Help/Api/PUT-produtos-update
GET /Help/Api/POST-tabelapreco-save
GET /Help/Api/PUT-tabelapreco-update
GET /Help/Api/POST-grupoprodutos-save
GET /Help/Api/POST-impressoras-save
GET /Help/Api/POST-produtos-saveunidades
```

São **páginas de documentação, leitura pura** — não mexem em dado nenhum. Só
precisam do Bearer token, como o `/help` que já foi lido uma vez.

Perguntas que elas respondem:

1. O `update` aceita ser endereçado pelo **nosso** código (o "externo")?
2. Que campos são **obrigatórios** no `save` — grupo? impressora? unidade? NCM?
3. O `save` devolve o código criado?
4. `tabelapreco` exige os **impostos** junto do preço? (Se exigir, o Botané não
   tem esse dado e o envio de preço fica bloqueado por cadastro fiscal.)
5. Há envio em **lote**? Só `produtos/saveunidades` diz "uma lista"; se o resto
   for um-a-um, 534 produtos são 534 chamadas, e volta a pergunta de cota.

---

## 7. Riscos que precisam de resposta antes do código

- **Não há ambiente de teste.** O modo simulado do Botané é nosso, com fixtures;
  o PDV do cliente é o que está no balcão. O primeiro `save` de verdade acontece
  em produção, durante o expediente de alguém.
- **`produtos/delete` existe e é definitivo.** Nenhuma rotina nossa deve
  chamá-lo — se um produto sai do cardápio, quem tira é gente, lá.
- **A janela.** Enviar cadastro no meio do almoço mexe no cardápio de quem está
  vendendo. Se houver envio automático, ele precisa de hora escolhida, como as
  agendas do Omie e do PDV já têm.
- **Cota e bloqueio.** O Omie ensinou que consumo demais bloqueia a integração
  inteira. Não se sabe o limite do PDV Legal; o envio precisa nascer com
  intervalo entre chamadas, como o `cliente.py` do Omie.
- **Auditoria.** Toda escrita para fora tem de ir para a auditoria com o que foi
  mandado — é a única forma de responder "quem mudou o preço deste prato".

---

## 8. Ordem sugerida, se o dono aprovar

1. Corrigir a conta errada em `pdv-legal-api.md` e escrever a guarda de CNPJ.
2. Buscar as sete páginas de modelo e responder as cinco perguntas do item 6.
3. **Decidir quem é o dono do preço.** Sem isso, parar aqui.
4. Construir o envio de **um produto novo** (`produtos/save`), disparado à mão,
   com prévia do que vai ser mandado — nunca automático na primeira versão.
5. Só depois, o preço, e com a leitura desligada do lado que passar a ser espelho.

⚠️ **Nada disso deve nascer automático.** A busca já é agendada porque errar
para menos custa uma venda não importada; errar para mais, na escrita, custa o
cardápio do cliente.


---

## 9. O desenho pedido pelo dono (29/08/2026)

> **Passo 1 FEITO** (migração 040): o interruptor `enviar_ao_pdv` na tela de
> Integrações e a marca `integrado_pdv` no cadastro do produto, com a carga dos
> 744 que já tinham ligação e o gatilho que marca quem ganhar a ligação depois.
> **Passo 1b FEITO** (migração 041): a mesma marca em **setor** e
> **categoria** — 29 categorias e 3 setores (VITRINE, BAR, COZINHA) marcados
> pela carga. E os três campos só APARECEM com o envio ligado, pela dica que
> viaja no `/auth/me`.
> **Passo 2 FEITO** (migrações 042 e 043): a fila, a tela **Cadastros ▸
> Exportação para o PDV** com as três abas, e a tabela intermediária
> `pdv_pendencias` alimentada por gatilho. **Exercitado contra a conta real**:
> 29 categorias e 3 setores adotados, `codRefExterna` gravado lá.
> Falta o produto — a função do gatilho já o trata e o `CREATE TRIGGER` está
> escrito e comentado na 043.

> Um parâmetro nas integrações do PDV, "Enviar informações ao PDV". Habilitado,
> aparece em Cadastros um item novo — como Exportações — listando tudo que está
> **pendente de envio**, em três abas: **pendente**, **enviado** e **com erro**,
> para ajustar e ver qual foi o erro. E em produto, ficha e categoria, um campo
> novo "Integrado com PDV", com um script para marcar os registros atuais.

A forma está certa e resolve o problema central: **de 3.301 produtos, só uns 500
têm o que fazer no PDV**, e sem uma marcação por registro o envio teria de
adivinhar quais. Abaixo, o que o desenho implica e o que ele ainda não decide.

### 9.1 A marcação: o que ela quer dizer, exatamente

⚠️ **`integrado_pdv` e `codigo_pdv` são coisas diferentes, e a diferença É a
fila.**

| `integrado_pdv` | `codigo_pdv` | significa | ação |
|---|---|---|---|
| ✔ | vazio | *deve* existir lá e não existe | `produtos/save` |
| ✔ | preenchido | existe lá | `produtos/update`, **se mudou** |
| ✘ | preenchido | veio de lá, mas não mandamos nada | nada — **nunca apagar** |
| ✘ | vazio | insumo de compra; não é assunto do PDV | nada |

**O script de marcação dos registros atuais** sai desses fatos, sem palpite:

- **produtos**: `integrado_pdv = (codigo_pdv IS NOT NULL)` — 534 hoje.
- **categorias**: verdadeiro para a categoria que **classifica ao menos um
  produto que já existe no PDV**. É fato, não semelhança de nome.
- **setores**: idem (ver 9.4).

### 9.2 A fila tem de ser DERIVADA, não mantida

🔑 A tentação é uma coluna `pendente_pdv` marcada quando alguém salva. **É a
armadilha do nome em maiúsculas, ao contrário.** O nome de um produto é escrito
em cinco lugares — o formulário, o catálogo do Omie, o cardápio do PDV, a
criação a partir do item da nota e a fusão de cadastros. Uma fila mantida à mão
precisaria ser alimentada nos cinco, e **o sexto — que vai existir — nasceria
sem ela**: o produto mudaria aqui e nunca apareceria como pendente.

A saída é a mesma que o gatilho usou: **não depender de memória**. O envio grava
a **impressão** (hash) do que mandou; a aba *pendente* é uma consulta —

```
integrado_pdv = true
E ( nunca enviado  OU  impressão do que seria enviado agora ≠ a do último envio OK )
```

Assim a fila está sempre certa, venha a mudança de onde vier — inclusive de uma
tela que ainda não foi escrita.

### 9.3 As três abas, e o que cada uma é

| aba | o que é | de onde sai |
|---|---|---|
| **pendente** | consulta derivada (9.2) | calculada na hora |
| **enviado** | o histórico do que foi | `pdv_envios` com estado OK |
| **com erro** | a última tentativa que falhou, com a mensagem e o que foi mandado | `pdv_envios` com estado ERRO |

⚠️ **A aba "com erro" só serve se guardar o CORPO enviado.** "Erro 400" sozinho
não diz o que ajustar; com o payload ao lado, quem olha vê que faltou o grupo ou
que o NCM foi recusado.

⚠️ **Enviado é histórico e cresce para sempre** — entra paginada, pelo padrão da
casa (`usePaginacao` + `X-Total`), com o corte no servidor.

⚠️ **Toda tentativa vai para a auditoria**, com o que foi mandado. É a única
forma de responder depois "quem mudou o preço deste prato no caixa".

### 9.4 A ordem importa: categoria antes de produto

O produto no PDV tem **grupo** (`nomeGrupo`) e **impressora** (`nomeImpressora`).
Mandar um produto cuja categoria ainda não existe lá tende a falhar — e a aba
"com erro" encheria de falhas de dependência que não são erro nenhum, só ordem.

Então a fila é **por tipo, em ordem**: categorias → (setores) → produtos.

⚠️ **E falta o de-para dos dois.** `categorias` e `setores` não têm coluna de
código do PDV; o vínculo com `grupoprodutos` e `impressoras` **não existe** e
precisa nascer com este trabalho — senão cada envio recria o grupo lá.

⚠️ **O dono não citou setor.** Mas se o produto vai com impressora, o setor vai
junto por consequência. Decidir se ele entra agora ou se o produto sai sem
impressora (e alguém escolhe lá).

### 9.5 A ficha é a peça que não tem encaixe do outro lado

⚠️ **Não existe rota de receita no PDV** — nenhuma das 173. E o modelo de
`produtos/get` **não tem campo de custo nem de preço**: o preço mora em
`tabelapreco`, e custo não aparece em lugar nenhum do produto.

Então "ficha integrada com PDV" precisa de significado. As leituras possíveis:

1. **O prato da ficha deve existir no PDV** — mas isso já é o
   `integrado_pdv` do *produto*; a ficha não acrescenta nada.
2. **Mandar o custo que a ficha calcula**, para os relatórios do PDV baterem com
   os daqui. Só caberia dentro de `tabelapreco/save` (*"preços e impostos"*), e
   **não se sabe se ele tem campo de custo** — é uma das perguntas do item 6.
3. **Marcar quais fichas estão prontas** para o prato poder ir (ficha homologada
   como pré-condição do envio). Isso é uma regra da FILA, não um campo na ficha.

**Pergunta para o dono:** qual das três? Hoje a (2) é a única que manda algo novo
para o PDV, e depende de um campo que talvez não exista.

### 9.6 O parâmetro, e o que ele protege

`integracoes.enviar_ao_pdv` na linha do PDV_LEGAL, **por loja**, **desligado por
padrão** — como as agendas. Desligado, o item de menu não aparece e nenhuma rota
de escrita responde.

⚠️ **A guarda do CNPJ (item 1) vale por lote, no servidor**, e não é substituída
por este parâmetro: um está ligado e o outro está certo são coisas diferentes.

⚠️ **O envio nasce MANUAL.** A busca é agendada porque errar para menos custa uma
venda não importada; errar para mais, na escrita, custa o cardápio do cliente no
meio do expediente.

### 9.7 O que este desenho ainda não decide

1. **A ficha** (9.5) — qual dos três significados.
2. **O preço** entra no envio? Volta a decisão do item 4: quem é o dono do preço
   de venda. Se entrar, a leitura do preço tem de sair.
3. **Setor/impressora** entra agora (9.4)?
4. As cinco perguntas do item 6, que só as páginas de modelo respondem.


---

## 10. O produto — o mapa de estados (29/08/2026)

Medido nos modelos reais (`/Help/Api/POST-produtos-save` e `POST-tabelapreco-save`).

### 10.1 O que a API oferece

`produtos` tem **`CodRefExterna`** (o nosso id) e — o que muda o desenho —
**`CodGrupoExterno`**: o produto aponta para o grupo pelo **nosso** id de
categoria. Foi para isso que adotar as 29 categorias serviu; sem aquilo, cada
produto precisaria carregar o código do grupo de lá.

Campos que nos interessam:

| PDV | daqui |
|---|---|
| `CodRefExterna` | `produtos.id` |
| `Codigo` | `produtos.codigo_pdv` (0 quando ainda não existe lá) |
| `DescricaoCupom` | `nome_curto` — é o que sai no cupom |
| `DescricaoDetalhada` | `nome` |
| `CodGrupoExterno` | `id_categoria` |
| `CodigoImpressora` | `setores.codigo_pdv` do `id_setor` |
| `Unidade`, `CodigoNCM`, `CodigoCest`, `CodigoEAN` | os campos do cadastro |
| `Status` (bool) | `ativo` |

**O preço vai por outra rota**, `tabelapreco/save|update`
(`Fiweb.Models.Produtos.Impostos`):

- **`CodProduto` é o ÚNICO campo obrigatório** — e é o código DELES, por isso
  `produtos.codigo_pdv` precisa estar gravado antes de qualquer preço sair.
- `Valor` é o preço de venda; `CodFilial` diz de qual loja.
- 🔑 **Todos os campos fiscais são opcionais** (CFOP, CSOSN, PIS, Cofins…).
  Isso responde a pergunta 4 do item 6: **mandar preço não depende de cadastro
  fiscal nenhum.**
- 🔑 **Existe `ValorCusto`.** É o encaixe que faltava para a ficha técnica
  (item 9.5): o custo calculado aqui tem para onde ir, e os relatórios do PDV
  passariam a bater com os daqui.

### 10.2 O mapa de estados

| # | aqui | no PDV | ação |
|---|---|---|---|
| 1 | novo, marcado, ativo | não existe | **CRIAR** |
| 2 | marcado, ativo | existe, sem dono (`codRefExterna` = 0) | **ADOTAR** |
| 3 | marcado, ativo | é nosso, e algo que ele enxerga mudou | **ATUALIZAR** |
| 4 | marcado, ativo | é nosso, mas está **inativo lá** | **REATIVAR** |
| 5 | **desmarcado** | é nosso e ativo lá | **DESATIVAR** |
| 6 | **inativado aqui** | é nosso e ativo lá | **DESATIVAR** |
| 7 | desmarcado | não existe lá | nada |
| 8 | marcado, mudou só o **preço** | é nosso | **PREÇO** (`tabelapreco`) |

⚠️ **Tudo passa pela fila.** Nenhum desses estados escreve no PDV ao salvar: o
gatilho registra a pendência e alguém manda pela tela de Exportação.

### 10.3 A assimetria com a categoria, e por que ela é segura

Na categoria, `ativo` **não** se sincroniza — PASCOA e DIA DOS NAMORADOS ficam
ativas aqui o ano todo e são ligadas e desligadas lá conforme a época, e
sincronizar reativaria a Páscoa em agosto.

No produto, você pediu o contrário: desativar aqui deve desativar lá. O risco é
o mesmo — um prato de inverno desligado no cardápio e ainda ativo aqui.

🔑 **O que torna as duas coisas compatíveis é a PENDÊNCIA.** É a mudança feita
*aqui* que autoriza mexer no `ativo` de *lá*:

- desativei o produto aqui → pendência → o envio desativa lá ✔
- alguém desativou no PDV e nada mudou aqui → **sem pendência, sem ação** ✔

A diferença de `ativo` **nunca sozinha** gera envio; só a mudança registrada
gera. Assim o dono do estado continua sendo quem mexeu por último em cada lado,
e não há ping-pong.

### 10.4 A decisão que ainda é sua: o preço tem dois donos

⚠️ **Hoje o Botané LÊ o preço do PDV.** `services/pdv/cardapio.py` importa
`tabelapreco/get` e grava em `produto_precos` "só quando muda" — 629 de 630
preenchidos vieram de lá.

Se o preço passar a ser enviado **sem** a leitura mudar, os dois sistemas
brigam: um preço alterado no PDV volta por cima do que mandamos, o próximo
envio o desfaz, e a tabela de preços — que existe para responder *"quando o
preço subiu?"* — vira ruído.

As saídas, e nenhuma é técnica:

1. **O Botané passa a ser o dono**: envia preço e **para de importar** preço do
   cardápio. É o que fecha o ciclo do sistema (custo → food cost → decisão de
   preço → caixa).
2. **O PDV continua dono**: o preço não entra no envio, e a integração de
   produto manda só cadastro. O ciclo fica pela metade.

**Decidido em 29/08/2026: a saída 1 — o Botané é o dono do preço.**

O que isso mudou, em concreto:

- `enviar_preco()` faz **ler → mudar só `valor` → gravar** em `tabelapreco`. A
  linha inteira volta como veio; o único campo tocado é o preço.
- ⚠️ **`cardapio.importar` PARA de importar preço** quando `enviar_ao_pdv` está
  ligado naquela loja. Sem isso a briga aconteceria mesmo com o envio certo: o
  preço de lá voltaria por cima na sincronização seguinte. Só o preço para de
  vir — nome, grupo, impressora e NCM continuam sendo importados.
- ⚠️ **Nenhum imposto é enviado.** Os campos fiscais estão preenchidos em 629 de
  630 no PDV (CFOP 5102, CSOSN 102, CST 00, PIS/Cofins e o objeto da reforma
  tributária) e o Botané **não tem nenhum deles**. Mandá-los zerados derrubaria
  a emissão fiscal do cliente. O corpo do produto leva descrição, grupo,
  impressora, unidade, NCM, CEST, EAN e status — e nada mais.
- ⚠️ `produtos/delete` **nunca** é chamado. Sair do cardápio é `status: false`.

O que o Botané manda, então, é: **valor, nome, setor e categoria.**

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

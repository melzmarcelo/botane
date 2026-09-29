# Pedidos pelo catálogo — estudo

🔑 **Pedido do dono (28/09/2026):** *"inicia o estudo para o cliente poder realizar pedidos
diretamente na tela de catálogo. Criar esta opção ao criar um catálogo do tipo Produtos. Aí
teremos um carrinho de compras para enviar pedidos ao sistema. Teremos uma tela com pedidos e
também um painel para acompanhar e aviso na tela inicial. Neste momento o pagamento não será
pelo sistema. Terá uma opção de mensagem sobre isto, onde o pagamento será na entrega, na
retirada, ou realizado via WhatsApp."*

Estado: **construído em 28/09/2026** (migração 101). Decisões na seção 0; o que foi feito e as armadilhas em `docs/memoria/catalogos.md`. Este documento diz o que já existe e serve ao pedido, como
fica para o cliente e para a casa, o modelo de dados, e o que precisa ser decidido — em
especial a relação do pedido com a VENDA (seção 6), que é onde isto pode dar errado.

---

## 0. O que o dono decidiu (28/09/2026) — isto manda sobre o resto do documento

| # | Pergunta | Decisão |
|---|---|---|
| 1 | Pedido e venda | **O pedido NÃO vira venda.** A casa lança o pedido no PDV, e a venda chega pela busca de sempre. No Botané, a pessoa só registra que lançou: **"lançado no PDV"**, com o **número do cupom** (opcional). Mandar o pedido ao PDV fica para quando o envio de informações for ligado |
| 2 | Retirada, entrega, taxa, mínimo | **Configurável**: modos (retirada e/ou entrega), taxa de entrega e pedido mínimo |
| 3 | Encomenda | **Sim**: o cliente escolhe **dia e hora**; antecedência mínima e máxima configuráveis |
| 4 | Aceite | **A casa sempre aceita** (não há confirmação automática) e **pode trocar produtos** antes de confirmar |
| 5 | Quais catálogos | **Os que forem configurados para aceitar pedidos**, só de origem **Produtos** (nunca PDF). A configuração é do catálogo, não da loja |
| 6 | Esgotado | **Não haverá pausa**: se está no catálogo, aceita |
| 7 | WhatsApp | **Só "pedido confirmado"**, por enquanto |
| 8 | Comanda | Sem impressora térmica: **PDF simples**, se precisar. A cozinha trabalha pelo pedido do PDV |

### O que as decisões mudam no desenho

- **Situações** (substitui o diagrama da seção 3):
  ```
  NOVO ──confirmar (com ou sem trocas)──▶ CONFIRMADO ──▶ ENTREGUE
    │                                         │
    └──recusar──▶ RECUSADO                   └──cancelar──▶ CANCELADO
  ```
  "Em preparo / pronto / saiu" ficam de fora: a cozinha trabalha pelo PDV, e colunas que
  ninguém move viram painel que mente. **"Lançado no PDV" é MARCA, não situação**
  (`lancado_pdv_em`, `lancado_por`, `cupom_pdv`): um pedido confirmado pode estar lançado ou
  não, e é essa a pergunta que o painel faz — *"confirmados que ainda não foram para o PDV"*.
- **Trocar produtos**: antes de confirmar, a casa pode mudar quantidade, tirar item, pôr
  outro item do mesmo catálogo (pelo preço vigente) — o total recalcula no servidor, e o
  **histórico guarda o que o cliente pediu e o que foi trocado**. O cliente vê o pedido como
  ficou (em "Meus pedidos") e recebe o "pedido confirmado" já com o total final.
- **O cupom liga o pedido à venda, sem criar venda**: com o número do cupom informado, quando a
  busca do PDV trouxer a venda com aquele documento, o pedido mostra "venda importada ✓" com o
  link para ela. É só uma ligação para conferir — nada muda em estoque, receita ou CMV.
- **Painel** com três colunas: *novos (confirmar)* · *confirmados, falta lançar no PDV* ·
  *para hoje / próximos* (encomendas por dia e hora). E o alerta no Início para pedido NOVO
  parado e para confirmado sem lançamento no PDV.
- **Catálogo por loja**: o catálogo continua podendo estar em várias lojas; o pedido nasce na
  loja que o cliente escolheu no site, e aparece só para ela.
- **Sem pausa de item** e **sem pagamento online**: o texto da casa sobre pagamento (na
  entrega, na retirada, via WhatsApp) é o que o cliente lê antes de enviar.

## 1. O que já existe e o pedido aproveita

| Já existe | Serve para |
|---|---|
| Catálogo de origem **Produtos** (categorias, subcategorias, itens, ordem) | É a vitrine: o carrinho nasce em cima dele, sem montar nada de novo |
| Cardápio público já sai com o **preço vigente da loja** (preço da loja → preço da casa) e **sem preço quando não há** | O carrinho usa o mesmo preço; item sem preço não entra no carrinho |
| **Nome de vitrine**, **foto** e **texto ao cliente** (aba Catálogo do produto) | O item do carrinho aparece como o cliente o leu |
| Cliente do portal **identificado pelo telefone**, cadastro único na rede, **termo de consentimento** | Quem pede já está identificado — sem criar login novo |
| Catálogo que **exige cadastro** para abrir | O mesmo mecanismo vale para pedir |
| Catálogo **por loja** (`catalogo_lojas`) e site com **duas lojas** | O pedido já nasce sabendo de qual loja é |
| **WhatsApp por loja** (API da Meta), com avisos, fila, histórico e resposta do cliente | Avisar "pedido recebido / pronto / saiu para entrega" sem inventar canal |
| Horário de funcionamento e **exceção do dia** (Portal) | Dizer se a loja aceita pedido agora, e para quando |
| Alertas e painel do **Início** | O aviso de pedido novo mora onde a casa já olha |

## 2. Como fica para o cliente (no site)

1. Abre o catálogo de produtos — igual a hoje.
2. Cada item com preço ganha **"adicionar"** e um contador (− 1 +). Uma barra fixa no pé mostra
   o **carrinho**: quantos itens e o total.
3. **Revisar pedido**: itens, quantidades, uma **observação por item** ("sem cebola") e uma
   geral, e o total.
4. **Como receber**: *retirar na loja* ou *entrega* (com endereço e, se a casa quiser, taxa).
   Quando: *o quanto antes* ou um horário dentro do funcionamento.
5. **Como pagar**: as opções que a casa ligou — *na retirada*, *na entrega*, *combinar pelo
   WhatsApp* — com a **mensagem da casa** sobre o pagamento ("O pagamento é feito na entrega,
   em dinheiro, cartão ou Pix. Não cobramos pelo site.").
6. **Identificação**: o telefone e o nome, o mesmo fluxo da reserva (e o termo, se for o
   primeiro cadastro).
7. **Enviar** → tela de confirmação com o **número do pedido** e a situação; e, se o WhatsApp
   estiver ligado, a mensagem "recebemos seu pedido nº 128".
8. **Meus pedidos**, como já existe "Minhas reservas": a situação de cada um, e cancelar
   enquanto a casa ainda não aceitou.

⚠️ **O carrinho vive no navegador do cliente** (a mesma sessão da aba que a reserva usa) até o
envio — nada vai ao servidor antes disso. Pedido só existe depois de enviado.

⚠️ **O preço é conferido no SERVIDOR no envio.** O site manda produto e quantidade; quem
calcula o valor é o servidor, pela mesma cascata do cardápio. Preço vindo do navegador é
preço que qualquer um edita.

## 3. Como fica para a casa

**Ao criar/editar um catálogo do tipo Produtos**, um cartão novo *Pedidos pelo site*:
- **aceita pedidos** (liga/desliga — padrão desligado);
- **modos**: retirada, entrega (ou os dois); taxa de entrega fixa, pedido mínimo;
- **pagamento**: quais opções aparecem (na entrega, na retirada, via WhatsApp) e o **texto
  sobre o pagamento** que o cliente lê antes de enviar;
- **quando**: só no horário de funcionamento, ou também agendado para depois; antecedência
  mínima (ex.: 30 min) e máxima (ex.: 3 dias — para encomenda de bolo);
- **confirmação**: automática ou a casa aceita cada um.

**Tela Pedidos** (Portal de Clientes ▸ Pedidos): grid paginado com número, cliente, telefone,
retirada/entrega, para quando, total, pagamento e situação; filtros por situação e dia; abrir o
pedido mostra itens, observações, endereço e o histórico de situações.

**Painel de pedidos** (a tela da operação, para o balcão/cozinha deixar aberta): colunas por
situação — *novos · em preparo · prontos · saiu para entrega* —, com o tempo desde que entrou,
atualizando sozinho, e um aviso sonoro opcional quando chega pedido novo. Cada cartão avança de
coluna com um toque.

**Início**: o cartão "Pedidos de hoje" (novos esperando aceite em destaque, e os do dia) e um
alerta **"pedido esperando há mais de X minutos"** — pedido parado é cliente esperando.

### As situações

```
NOVO ──aceitar──▶ ACEITO ──▶ EM_PREPARO ──▶ PRONTO ──▶ (retirada) ENTREGUE
  │                                            └────▶ SAIU_PARA_ENTREGA ──▶ ENTREGUE
  └──recusar──▶ RECUSADO          (qualquer um antes de ENTREGUE) ──cancelar──▶ CANCELADO
```

Com confirmação automática, o pedido já nasce ACEITO. O cliente cancela sozinho só enquanto
NOVO; depois, fala com a casa. Recusar e cancelar pedem motivo, que o cliente vê.

**Avisos por WhatsApp** (novos eventos no catálogo de avisos da loja, cada um ligável):
pedido recebido, aceito (com previsão), pronto para retirar, saiu para entrega, recusado/
cancelado. O mesmo mecanismo dos avisos de reserva — modelo aprovado pela Meta, fila,
histórico.

## 4. Pagamento — fora do sistema, mas registrado

- O sistema **não cobra**: só registra **como o cliente disse que vai pagar** (retirada,
  entrega, WhatsApp) e mostra o texto da casa.
- Na tela do pedido, a casa marca **pago** quando recebe (com a forma: dinheiro, cartão, Pix),
  para a lista responder "o que falta receber".
- "Combinar pelo WhatsApp" abre, depois do envio, a conversa com a loja já com o número do
  pedido no texto (o `wa.me` que o site já usa).
- ⚠️ Pagamento online (Pix com QR, cartão) fica para uma fase futura — muda obrigações (taxa,
  estorno, conciliação) e não foi pedido agora.

## 5. Modelo de dados proposto

```
catalogo_pedidos_config  -- por catálogo: aceita, modos (RETIRADA/ENTREGA), taxa_entrega,
                         --   pedido_minimo, formas_pagamento[], texto_pagamento,
                         --   confirmacao (AUTOMATICA/MANUAL), antecedencia_min/max, so_no_horario
pedidos                  -- id, numero (sequência por loja/dia ou por loja), id_unidade,
                         --   id_catalogo, id_cliente (reserva_clientes), nome, telefone,
                         --   modo, endereco, para_quando, forma_pagamento, observacao,
                         --   subtotal, taxa_entrega, total, situacao, motivo,
                         --   pago_em, pago_como, id_venda (ver seção 6), criado_em
pedido_itens             -- id_pedido, id_produto, nome (como o cliente leu — congelado),
                         --   quantidade, preco_unitario (congelado no envio), observacao
pedido_historico         -- id_pedido, de, para, quando, quem (usuário ou "cliente")
```

- **Preço e nome congelados no item**, como a venda congela o custo: mudar o preço amanhã não
  pode mudar o pedido de hoje.
- **Número curto e legível** para o balcão ("pedido 128"), além do id interno.
- **Idempotência do envio** (regra 8): o site manda uma chave do carrinho; o índice único impede
  que um toque duplo crie dois pedidos.
- Permissões novas: `pedidos.ver`, `pedidos.operar` (aceitar, avançar, marcar pago),
  `pedidos.configurar`. Como o resto do portal, só existem com o Portal ligado na loja.

## 6. ⚠️ O pedido e a VENDA — a decisão que manda em tudo

Hoje as vendas da casa **entram pelo PDV** (cupom fiscal), e é de lá que saem a baixa de
estoque, a receita e o CMV. Se o pedido do site também virasse venda no Botané, e a casa
registrasse o mesmo pedido no PDV para emitir o cupom, **a venda contaria duas vezes** — em
estoque, receita e CMV — e nada avisaria.

| Caminho | Como funciona | Risco |
|---|---|---|
| **A. O pedido NÃO vira venda** (recomendado para começar) | O pedido é operação e comunicação. A casa registra no PDV como sempre, e a venda chega pela integração. O relatório de pedidos mostra quanto entrou pelo site | Nenhum para o CMV. O pedido e o cupom ficam sem ligação entre si |
| **B. O pedido vira venda ao ser ENTREGUE** | Na entrega nasce uma venda no Botané (origem `PEDIDO`), com baixa e custo congelado | Dupla contagem se a casa também lançar no PDV. Só serve a casa SEM PDV |
| **C. O pedido vai ao PDV** | O Botané manda o pedido ao PDV (a integração de envio já existe para cadastro) e a venda volta pela importação | Depende de o PDV aceitar pedido pela API — a verificar |

**Recomendação:** começar pelo **A**, com a opção B existindo mas desligada por padrão (para uma
casa sem PDV). Investigar o C à parte.

## 7. O que pesa na operação

- **Estoque**: o catálogo não sabe se há produto. Opções: nenhuma trava (a casa recusa o que não
  tem), ou o item poder ser **pausado** no catálogo ("esgotado hoje") com um toque, sem mexer no
  cadastro. Recomendado: o pausar.
- **Horário**: fora do horário, o catálogo mostra os produtos mas o botão diz "a loja abre às
  9h — agendar para depois" (se agendamento estiver ligado) ou "pedidos fechados agora".
- **Encomenda** (bolo para sábado): é pedido com *para quando* longe — a antecedência máxima
  decide se isso vale.
- **Endereço de entrega**: texto livre com bairro, e a taxa fixa. Taxa por bairro/distância é
  evolução.
- **Impressão**: a comanda do pedido para a cozinha, em PDF no tamanho de bobina térmica
  (80 mm), do mesmo jeito que as etiquetas imprimem no tamanho do rolo.

## 8. Perguntas para o dono (respondidas — ver seção 0)

1. **Pedido e venda (seção 6)**: a casa vai lançar os pedidos no PDV para emitir o cupom?
   Se sim, o caminho é o **A** — o pedido não vira venda aqui.
2. **Retirada, entrega ou os dois?** Tem entrega própria? Taxa fixa? Pedido mínimo?
3. **Só para agora, ou também encomenda** para outro dia? Com quanta antecedência?
4. **A casa aceita cada pedido**, ou entra direto como aceito?
5. **Quais catálogos** vão aceitar pedido (todos os de produtos, ou um específico, tipo
   "Delivery")? E em quais lojas?
6. **Esgotado**: quer poder pausar item do catálogo no dia?
7. **Avisos por WhatsApp** do pedido: todos, ou só "recebido" e "pronto"?
8. **Comanda impressa** na cozinha: tem impressora térmica de cupom?

## 9. Ordem de construção (revista com as decisões)

1. **Configuração no catálogo** (aceita pedidos, modos, taxa, mínimo, encomenda e antecedência,
   formas e texto de pagamento) + tabelas + a API pública de envio (preço conferido no
   servidor, idempotência).
2. **Carrinho e envio no site**: retirada/entrega, dia e hora, identificação pelo telefone, a
   mensagem de pagamento, a confirmação com o número; **Meus pedidos**.
3. **Tela Pedidos**: grid, detalhe, **confirmar com trocas**, recusar, cancelar, **lançado no
   PDV com o cupom**, marcar pago, entregue; PDF simples do pedido.
4. **Painel de pedidos** (três colunas, atualização automática, som) e o **aviso no Início**.
5. **WhatsApp "pedido confirmado"**.
6. A ligação automática cupom ↔ venda importada.

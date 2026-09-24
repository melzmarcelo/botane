# Plano de Fidelidade no Portal de Clientes — estudo

🔑 **Pedido do dono (24/09/2026):** *"inicia uma análise para implementar dentro do portal do
cliente um plano de Fidelidade."*

> ✅ **Decidido e construído em 24/09/2026: cartão por VISITA com check-in pelo QR da mesa**
> (migração 091) — ver `docs/memoria/reservas.md`, seção "Fidelidade". As seções abaixo sobre
> pontos por real e cupom do PDV ficam como registro das alternativas.

Estado original: **análise, nada construído.** Este documento levanta o que o sistema já tem, o
problema que decide o desenho, as opções, um modelo de dados que segue as regras da casa, e as
perguntas que só o dono responde. A referência de mercado é o LeadsFood, que o dono já usa
(ver `reservas-esboco.md`: *"o LeadsFood é um hub: cardápio, catálogos, fidelidade, selos"*).

---

## 1. O que já existe e serve ao programa

| Peça | Onde | Serve para |
|---|---|---|
| **Cadastro único por telefone** | `reserva_clientes` (082, 087) | a identidade do participante — sem login nem senha, como o site já faz |
| Nascimento, cidade, gênero | 086 | bônus de aniversário, segmentação |
| **Aceite do termo, com versão** | 090 | base legal (LGPD) — ⚠️ mas o texto atual não fala em fidelidade (ver §6) |
| Site com identificação por telefone | `site/index.html` | "Meus pontos", pontuar e resgatar sem app |
| Limite de abuso por telefone e origem | `reserva_clientes.marcar_tentativa` | conter quem tenta pontuar cupom alheio |
| **Cupons do PDV Legal importados** | `vendas` (origem `PDV_LEGAL`) | o valor da compra vem do caixa, não digitado por ninguém |
| Grid de Clientes | `reservas/clientes/` | ganha as colunas saldo e última compra |
| Razão append-only com `FOR UPDATE` | regra 1 e 3 (estoque) | o mesmo desenho serve ao saldo de pontos |

Números da base local (24/09/2026): 995 cupons PDV Legal desde 26/08, **ticket médio R$ 118,50**;
571 vendas manuais (294 com pessoa — são consumo de equipe); 1 cliente cadastrado pelo site.

## 2. O problema que decide tudo: a compra não sabe quem comprou

`vendas.id_pessoa` existe (055), mas aponta para `fornecedores` (a tabela de pessoas da casa) e
só é preenchido no lançamento manual — é o consumo de funcionário. **Nenhum cupom do PDV tem
dono.** O cupom do PDV Legal traz um campo `clientes` (vazio na fixture `cupom_get.json`), e o
importador o ignora.

Sem ligar compra a cliente não há programa: há cadastro. As formas de fazer a ligação:

| | Como | Atrito do cliente | Atrito do caixa | Fraude | Depende de |
|---|---|---|---|---|---|
| **A. CPF/telefone no PDV** | o caixa informa o cliente no cupom; a importação lê `clientes` | nenhum | digitar no PDV | baixa | o PDV Legal preencher `clientes` — **não verificado** |
| **B. Lançar no Botané** | tela "pontuar": telefone + nº do cupom | nenhum | segunda tela | baixa | nada — mas é trabalho a mais no balcão |
| **C. O cliente reivindica** | QR code no cupom/mesa → site → telefone + nº do cupom | médio | nenhum | média (cupom alheio) | o cupom já estar importado |
| D. Só reservas | pontua quem reservou e compareceu | nenhum | nenhum | baixa | — mas quase ninguém reserva para um café |

🔑 **Em todas, o VALOR vem do cupom importado**, nunca digitado: digitar valor é o jeito de
pontuar R$ 1.000 num café. O cupom é a prova; o telefone só diz de quem ela é.

**Recomendação:** A se o PDV Legal suportar (é a única sem trabalho para ninguém); **C como
complemento** (o cliente que esqueceu de dar o telefone pontua depois); B só como correção
manual, com permissão própria. D fica de fora como mecanismo — no máximo um bônus.

⚠️ **C tem uma latência**: o cupom só existe no Botané depois da sincronização do PDV
(`services/pdv/agenda.py`). Se ela roda de hora em hora, o cliente que tenta pontuar na mesa
ouve "cupom não encontrado". A tela tem de dizer "seu cupom ainda não chegou; tente mais tarde"
— e o sistema pode guardar a reivindicação pendente e casar sozinho quando o cupom chegar.

## 3. Que programa

| Modelo | Como o cliente entende | Prós | Contras |
|---|---|---|---|
| **Pontos por real** + catálogo de recompensas | "1 ponto a cada R$ 1; 300 pontos = um café" | flexível, recompensa escolhida pela casa, custo controlável | exige catálogo e conta de "quanto vale um ponto" |
| **Carimbo** (visitas) | "a cada 10 visitas, 1 café" | o mais simples de explicar, clássico de cafeteria | ignora o valor — quem gasta R$ 20 e R$ 300 vale igual |
| Cashback em R$ | "5% volta para a próxima compra" | direto | é desconto em dinheiro: vira passivo financeiro e mexe no CMV/receita |
| Níveis (bronze/prata/ouro) | "cliente ouro ganha X" | engaja o frequente | complexidade — fica para depois |

**Recomendação para começar:** pontos por real com catálogo de recompensas em **produtos**
(um café, uma fatia de bolo). Recompensa em produto custa à casa o **CMV** do item, não o preço
de venda — e o sistema já sabe o custo de cada ficha. Carimbo é um caso particular (1 ponto por
visita, recompensa com 10 pontos) e cabe no mesmo modelo como configuração.

## 4. O resgate — onde a recompensa encontra o caixa

O Botané **não escreve venda no PDV** (só cadastro de produto — ver `vendas.md`). Então o
resgate não pode ser "o desconto aparece sozinho no caixa":

1. O cliente escolhe a recompensa no site → o Botané debita os pontos e gera um **voucher**
   (código curto, validade de dias, uso único).
2. No caixa, a atendente digita o código numa tela do Botané ("validar resgate") → ele diz o
   que entregar e marca como **usado**. No PDV, o item sai como cortesia/desconto, como hoje.
3. Voucher vencido sem uso **devolve os pontos** (estorno no razão, nunca UPDATE).

⚠️ O item entregue sai do estoque pelo PDV como qualquer venda com desconto — o CMV já o
enxerga. O que o Botané precisa é **ligar o voucher ao cupom** para o relatório de custo do
programa (quanto a fidelidade custou no mês).

## 5. Modelo de dados proposto (seguindo as regras da casa)

```
fidelidade_config        -- por REDE (ver pergunta 5): pontos por real, validade, recompensa de aniversário, ligado
fidelidade_recompensas   -- nome, pontos, id_produto (opcional), ativa, lojas onde vale
fidelidade_movimentos    -- O RAZÃO. append-only (regra 1): id_cliente, tipo (CREDITO|RESGATE|ESTORNO|EXPIRACAO|AJUSTE),
                         --   pontos (numeric, com sinal), id_venda, id_resgate, id_unidade, motivo, criado_por, criado_em
fidelidade_saldos        -- id_cliente, saldo — travado com SELECT … FOR UPDATE (regra 3), só o service escreve
fidelidade_resgates      -- voucher: código, id_recompensa, pontos, status (EMITIDO|USADO|VENCIDO), vence_em, usado_em, usado_por, id_unidade
fidelidade_reivindicacoes-- (opção C) telefone + nº do cupom pendente de chegar do PDV
```

- ⚠️ **Idempotência é do BANCO** (regra 8): índice único parcial em
  `fidelidade_movimentos (id_venda) WHERE tipo = 'CREDITO'` — o mesmo cupom não pontua duas
  vezes, venha da importação, do balcão ou do site, em qualquer ordem.
- ⚠️ **Venda cancelada depois de pontuar → ESTORNO**, gerado pela própria importação quando o
  cupom volta cancelado. É o que o PDV faz com cupom cancelado, e ele já é reimportado.
- ⚠️ **Venda com `id_pessoa` (consumo de equipe) NÃO pontua**: é desconto de funcionário, e
  pontuar em cima dele seria dar benefício duas vezes.
- Pontos em `numeric` (regra 2) — "1,5 ponto por real" existe.
- `id_unidade` em todo movimento (regra 5), mesmo com saldo de rede.
- Datas: vencimento calculado na casa (`America/Sao_Paulo`, regra 6).

## 6. LGPD — o termo precisa de versão nova

O termo aceito hoje (versão `2026-09-24`) fala em reservas, cardápios e **ofertas por
WhatsApp/SMS**, mas **não em programa de fidelidade** nem em ligar as compras ao cadastro.
Ligar o histórico de consumo à pessoa é uma finalidade nova:

- nova versão do termo citando o programa e o uso do histórico de compras;
- **participar é opt-in**: quem aceitou a versão antiga continua cliente, mas só pontua depois
  de aceitar a nova (o site pergunta na próxima identificação — `termo_versao` já diz quem
  precisa);
- sair do programa = revogar o consentimento: o saldo é zerado por movimento (`EXPIRACAO` com
  motivo), e o histórico de compras deixa de ser ligado.

## 7. Telas

**Sistema — Portal de Clientes → Fidelidade**
- Configuração (regra de pontos, validade, aniversário) — `fidelidade.configurar`
- Recompensas (catálogo, com o custo da ficha ao lado dos pontos)
- Validar resgate (campo do código, grande, para o balcão) — `fidelidade.operar`
- Extrato do cliente (a partir do grid de Clientes, que ganha saldo e última compra)
- Painel: participantes, pontos emitidos x resgatados, **custo do programa em R$ (CMV das
  recompensas)**, recorrência de quem participa x quem não participa

**Site do cliente**
- "Meus pontos" depois do telefone: saldo, extrato, o que falta para a próxima recompensa
- "Pontuar um cupom" (opção C)
- "Resgatar": escolhe a recompensa → recebe o código

Permissões novas: `fidelidade.ver`, `fidelidade.operar`, `fidelidade.configurar`.

## 8. Perguntas para o dono

1. **O PDV Legal registra o cliente no cupom hoje?** (CPF na nota, cliente cadastrado no PDV)
   Se sim, a opção A resolve quase tudo. → verificar num cupom real que tenha CPF na nota.
2. **Pontos por real ou carimbo por visita?** E quanto vale: quantos reais por ponto, quantos
   pontos por recompensa. (Referência: a casa quer devolver quanto % do faturamento? 2–5% é o
   comum.)
3. **Quais recompensas?** Produtos (café, doce), desconto, experiência?
4. **O cliente pode pontuar sozinho** pelo número do cupom (opção C), ou só o caixa pontua?
5. **Pontos valem na rede toda** ou por loja? (O cadastro já é da rede.)
6. **Validade dos pontos?** (12 meses é o comum; sem validade o passivo só cresce.)
7. **Bônus de aniversário?** Pontos, ou uma recompensa direta no mês?
8. **Comunicação:** avisar saldo/aniversário por WhatsApp exige a API do WhatsApp Business
   (custo e aprovação de modelo) — hoje o site só abre o `wa.me`. Fica para uma segunda fase?

## 9. Ordem de construção sugerida

0. **Verificar o campo `clientes` do cupom no PDV Legal** (pergunta 1) — muda o desenho.
1. Razão de pontos + configuração + crédito automático na importação (se A) ou pelo balcão (B);
   saldo no grid de Clientes; termo versão 2 com opt-in.
2. "Meus pontos" no site.
3. Recompensas, resgate com voucher e a tela de validação no balcão.
4. Reivindicação de cupom pelo cliente (C), com a fila de pendentes.
5. Expiração e aniversário (job diário, como o de e-mail de prazo).
6. Painel do programa (custo, participação, recorrência).

Cada fatia entra com a sua suíte `smoke_fidelidade_*.py` e a memória em
`docs/memoria/fidelidade.md` (módulo novo dentro do Portal de Clientes).

## 10. Riscos

- **Pontuar cupom alheio** (opção C): o cupom é da mesa, não da pessoa. Mitigação: janela
  curta depois da compra, um cupom pontua uma vez, limite por telefone/origem já existente.
- **Passivo de pontos** sem validade e sem painel: a casa deve pontos que não sabe que deve.
- **Caixa que esquece de identificar o cliente** (opção A): o programa parece não funcionar.
  A opção C existe para isso.
- **Recompensa cara demais** descoberta tarde: por isso o catálogo mostra o CMV do item ao lado
  dos pontos exigidos, e o painel mostra o custo do mês.

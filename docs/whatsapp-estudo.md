# Mensagens por WhatsApp — estudo

🔑 **Pedido do dono (28/09/2026):** *"envio de mensagens via WhatsApp para clientes, como
reservas, confirmação de reserva, prêmios e outros assuntos. Podemos ter isto de forma
configurável. E, caso possível, a opção de confirmação de presença via WhatsApp, recebendo a
opção selecionada pelo cliente."*

Estado: **análise, nada construído.** O WhatsApp automático foi adiado de propósito três
vezes neste projeto (ver `docs/memoria/reservas.md`): enviar sem o cliente abrir a conversa
exige a API oficial, um provedor e modelos aprovados. Hoje o sistema só **abre** a conversa
(`wa.me`), e quem digita é o cliente. Este estudo diz o que muda, o que precisa ser decidido
e o que dá para construir antes de a conta ficar pronta.

---

## 1. O que é possível — e a confirmação de presença É possível

| Quer | Dá? | Como |
|---|---|---|
| Mandar "sua reserva está confirmada" | Sim | Mensagem de **modelo** (template) aprovado pela Meta, categoria *utilidade* |
| Lembrar a reserva no dia | Sim | Modelo agendado — ex.: 3 horas antes |
| **Confirmar presença com um toque** | **Sim** | Modelo com **botões de resposta rápida** ("Confirmo" / "Preciso cancelar"). O toque do cliente chega ao Botané por **webhook**, com o botão escolhido |
| Avisar "você ganhou um prêmio" / "seu prêmio vence em 3 dias" | Sim | Modelo de *utilidade* |
| Aniversário, promoções, novidades | Sim, com regra | Modelo de *marketing*: mais caro, e o cliente precisa ter aceitado receber (o termo já cita "novidades e ofertas por WhatsApp") |
| Responder livremente o que o cliente escrever | Sim | Dentro da **janela de 24 h** depois da última mensagem DELE — aí não precisa de modelo |

⚠️ **Mensagem que a casa inicia é SEMPRE um modelo pré-aprovado**, com as partes variáveis
marcadas ({nome}, {data}, {hora}). Texto livre só vale respondendo o cliente, dentro das 24 h.
É por isso que "configurável" aqui quer dizer: **ligar/desligar cada aviso, escolher quando e
editar o texto do modelo** — e o texto editado volta para aprovação da Meta (costuma levar de
minutos a um dia).

## 2. Por onde enviar — a decisão principal

| Caminho | Custo | Prós | Contras |
|---|---|---|---|
| **API oficial da Meta (Cloud API), direto** | Sem mensalidade; paga por mensagem de modelo enviada | Oficial, sem intermediário; botões e webhook nativos; o Botané fala direto com a Meta | A configuração na Meta é trabalhosa na 1ª vez (conta Business, app, token, webhook) |
| **Provedor oficial (BSP)** — ex.: Zenvia, Take Blip, Twilio, Gupshup, 360dialog | Mensalidade e/ou taxa por mensagem, além do custo da Meta | Suporte (alguns em português), painel próprio, ajudam na aprovação | Mais um contrato e mais um custo; cada um tem a sua API |
| **Não oficial** (conecta pelo WhatsApp Web: Z-API, Evolution API…) | Barato | Sem modelo, sem aprovação | **Viola os termos do WhatsApp: o número pode ser BANIDO** — o número da casa, com os clientes dele. Não recomendado |

**Recomendação: a API oficial da Meta, direto.** É o único caminho sem mensalidade e sem
risco de banimento, e o que o Botané precisa dela é pouco (enviar modelo, receber webhook).

**Custo (ordem de grandeza, conferir na tabela da Meta no dia):** a Meta cobra por mensagem
de modelo entregue, por categoria e por país. No Brasil, *utilidade* sai por centavos de real
por mensagem e *marketing* custa bem mais; responder o cliente dentro das 24 h não é cobrado.
Uma casa com ~20 reservas/dia, mandando confirmação + lembrete, gasta pouco por mês — o que
pesa é marketing em massa.

## 3. O número

- **Número novo, só para o sistema**: o caminho mais limpo.
- **O número atual (47 99910-5033)**: a Meta permite hoje usar o mesmo número no app WhatsApp
  Business e na API ao mesmo tempo ("coexistência"), mantendo as conversas no celular. Precisa
  ser conferido na hora de ligar — as condições da Meta mudam.
- ⚠️ Nos dois casos, o nome exibido ("Botané Deli e Café") passa por aprovação da Meta.

## 4. O que o dono precisa fazer (e o Botané não consegue fazer por ele)

1. Criar/usar um **portfólio empresarial na Meta** (business.facebook.com) e, se pedido,
   **verificar a empresa** (CNPJ, documento) — é o que libera volume de envio.
2. Criar o **app** com o produto WhatsApp e adicionar o **número**.
3. Gerar um **token permanente** (usuário de sistema) — ele vai para Integrações no Botané,
   cifrado, como as chaves do Omie e do PDV.
4. Cadastrar a **URL do webhook** que o Botané informar
   (`https://sistema.botanedeliecafe.com.br/api/publico/whatsapp/webhook`).
5. Submeter os **modelos** — os textos o Botané já entrega prontos.

## 5. Como fica dentro do Botané

**Configuração — Portal de Clientes → WhatsApp**
- **Conexão**: número, token (em Integrações), estado ("conectado" / "modo simulado").
- **Avisos**, cada um com liga/desliga, quando mandar e o modelo:

  | Aviso | Quando | Botões | Categoria |
  |---|---|---|---|
  | Reserva recebida (aguardando a casa) | ao marcar pelo site, com confirmação manual | — | utilidade |
  | Reserva confirmada | ao confirmar (na hora ou pela casa) | — | utilidade |
  | **Lembrete + confirmação de presença** | X horas antes (padrão 3 h) | **Confirmo · Preciso cancelar** | utilidade |
  | Reserva cancelada pela casa | ao cancelar no balcão | — | utilidade |
  | Prêmio conquistado | ao completar o cartão | — | utilidade |
  | Prêmio vencendo | N dias antes (padrão 3) | — | utilidade |
  | Aniversário | no dia, de manhã | — | marketing |

- **Histórico de mensagens**: para quem, qual aviso, quando, e o estado (na fila, enviada,
  entregue, lida, respondida, falhou — com o motivo). É a resposta para "ele disse que não
  recebeu".

**A confirmação de presença, ponta a ponta**
1. No horário, o Botané manda o lembrete com os dois botões.
2. O cliente toca **Confirmo** → a Meta chama o webhook → a reserva ganha "presença
   confirmada pelo WhatsApp" (✓ na agenda) → o cliente recebe "Obrigado, até logo!".
3. O cliente toca **Preciso cancelar** → a reserva vai para **cancelada** pela mesma regra de
   status de hoje (a mesa volta a ficar livre) → a agenda mostra "cancelou pelo WhatsApp".
4. Sem resposta até a hora → a agenda mostra "não confirmou" — é a lista de quem ligar.

**Por dentro**
- **Fila de saída** (`whatsapp_mensagens`): cada aviso vira uma linha; um serviço de fundo
  envia o que venceu, com nova tentativa quando falha. ⚠️ Idempotência pelo **banco** (regra
  8): um índice único por (aviso, reserva) impede o mesmo lembrete de sair duas vezes num
  reinício.
- **Webhook** público, com a **assinatura da Meta conferida** (`X-Hub-Signature-256`) —
  quem não assina não mexe em reserva nenhuma. Atualiza os estados (entregue, lida) e trata
  os botões.
- **Opt-out**: quem responder "PARAR" (ou pedir para não receber) sai dos avisos de
  marketing; os de utilidade da própria reserva continuam, que é o que o termo já cobre.
- **Modo simulado**: sem token configurado, as mensagens vão para o histórico marcadas
  "simulada", sem sair. É o mesmo desenho do Omie — e é o que permite **construir e testar
  tudo antes de a conta na Meta ficar pronta**.

## 6. Ordem de construção sugerida

1. **Já dá para começar, sem conta na Meta**: fila de mensagens, avisos configuráveis, modo
   simulado, histórico, e o disparo nos pontos certos (reserva criada, confirmada, cancelada;
   prêmio ganho). A tela funciona inteira em modo simulado.
2. **Lembrete + confirmação de presença**: o agendamento, os botões e o webhook (testado com
   chamadas simuladas assinadas); o ✓/✗ na agenda.
3. **Ligar na Meta** (depois do passo do dono na seção 4): token, número, modelos aprovados,
   webhook no ar, primeiros envios reais com o número da casa.
4. Prêmio vencendo e aniversário (este último depende de a casa querer marketing).

## 7. Perguntas para o dono

1. **Caminho**: API oficial da Meta direto (recomendado) ou um provedor? Algum já usado pela
   casa (o LeadsFood envia por qual)?
2. **Número**: o atual (coexistência) ou um número novo só para o sistema?
3. **Quais avisos na primeira fase?** (sugestão: confirmada + lembrete com confirmação de
   presença + cancelada pela casa + prêmio conquistado)
4. **Antecedência do lembrete** (sugestão: 3 horas; ou véspera às 18 h?)
5. Aniversário e promoções entram, ou fica só utilidade por enquanto?

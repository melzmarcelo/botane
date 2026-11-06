# Assistente de processos pelo WhatsApp — estudo (06/11/2026)

🔑 **Pedido do dono:** *"ter um número de WhatsApp sem precisar comprar chip ou celular, só para
uma integração no sistema … um bot assistente de processos: vinculo meu telefone no usuário, de
manhã mando um áudio ou texto pedindo minhas pendências de hoje, ele responde 'produzir 10 pães',
peço a receita, ele manda, confirmo a produção e o sistema lança e põe no estoque."*

**Resposta curta: dá, e o Botané já tem as três peças mais caras prontas.** Falta a cola.

## 1. O que já existe e é reaproveitado

| Peça | Onde | O que faz hoje | Papel no assistente |
|---|---|---|---|
| WhatsApp oficial (Cloud API da Meta) | `services/whatsapp.py`, aba WhatsApp da loja | envia avisos a clientes, recebe webhook (botões do lembrete), vários números por loja | é o "telefone" do assistente: recebe a mensagem do funcionário e responde |
| Catálogo de ferramentas do conector | `services/mcp_ferramentas.py` (`FERRAMENTAS`, `chamar`) | ~200 ferramentas que o Claude usa pelo claude.ai, cada uma = rota existente, chamada **com a credencial de quem pediu** | é o "cérebro com mãos": as mesmas ferramentas, agora chamadas a partir do WhatsApp |
| Chave da Anthropic | `integracoes` serviço `ANTHROPIC` (`services/traducao.py`) | tradução do cardápio | o assistente usa a mesma chave para conversar |

O exemplo do dono já cabe nas ferramentas atuais:

| Fala | Ferramentas |
|---|---|
| "quais minhas pendências hoje?" | `agenda_producao`, `alertas`, `vencimentos`, `painel_de_etiquetas`, `painel_de_pedidos` |
| "me manda a receita do pão" | `ficha_tecnica` + `necessario_para_produzir` (já escala para 10 un. e diz se falta insumo) |
| "pode lançar" | `item_da_agenda` (prévia) → `produzir_da_agenda` (lança, baixa insumos, dá entrada no produzido) |

⚠️ **Nada de regra de negócio nova**: permissão, loja, setor, estoque append-only e custo
congelado continuam valendo, porque tudo passa pelas rotas de sempre.

## 2. O número sem chip e sem celular

A Cloud API **não precisa de aparelho**: o número mora na Meta, e o Botané fala com ela pela
internet. O que a Meta exige é só **um código de verificação uma única vez**, por SMS **ou por
ligação de voz**. Por isso servem números que nunca tiveram chip:

| Opção | Como | Custo | Observação |
|---|---|---|---|
| **Número virtual (VoIP/DID) brasileiro** — recomendado | contratar um número fixo virtual numa operadora VoIP; a verificação da Meta vem por ligação, atendida no app/softphone da operadora | mensalidade baixa de telefonia | número próprio, definitivo, com o DDD da casa. Conferir antes que a operadora entrega ligação recebida |
| **Fixo da casa que não usa WhatsApp** | verifica por ligação | zero | só se a linha não estiver em nenhum WhatsApp |
| **Número de teste da Meta** | vem pronto no app da Meta | zero | só para desenvolver: fala com até 5 números cadastrados e não pode ir a produção |

### Operadoras pesquisadas (06/11/2026 — preços ANUNCIADOS nos sites, conferir na contratação)

| Operadora | Preço anunciado | O que diz sobre WhatsApp |
|---|---|---|
| [Telera](https://telera.com.br/numero-virtual-fixo/) | plano fixo ~R$ 10,99/mês | o plano **fixo** recebe a ligação de verificação; o móvel recebe SMS |
| [BRCel](https://brcel.com/) | a partir de R$ 19,90/mês | o fixo atende a ligação e mostra o código no painel |
| [Digital Vox](https://digitalvoxtelecom.com.br/numero-virtual/) | R$ 24,90/mês | diz que todos os números servem ao WhatsApp Business |
| [Numio](https://numio.com.br/) | R$ 25,90/mês | foco em WhatsApp Business |
| [Directcall](https://directcall.com.br/produtos/numero-fixo-para-whatsapp/) | R$ 25/número + ativação | ⚠️ fidelidade de 36 meses |
| [Avoip](https://avoip.com.br/numeros-virtuais) | a partir de R$ 17–27/mês | **cita a API oficial e a verificação da Meta**; homologada Anatel |
| [BRDID](https://brdid.com.br/br-did-operadora-virtual/) | R$ 20–80/mês, sem instalação | número virtual para WhatsApp e PABX |

Nenhum site confirmou o DDD 47 nem prova a compatibilidade com a Cloud API. **Antes de pagar,
perguntar por escrito:** (1) tem DDD 47?; (2) o número recebe a ligação de verificação do
WhatsApp, e o código aparece no painel/app?; (3) já ativaram número na **API oficial** (Cloud
API), não só no app?; (4) taxa de ativação e fidelidade; (5) a linha fica em nome da empresa (CNPJ).
⚠️ Na hora da verificação, desligar URA e desvio de chamada: a ligação da Meta não navega menu.
⚠️ Número virtual **gratuito** costuma ser recusado (compartilhado, marcado como VoIP).
🔑 **Sugestão:** Telera (mais barato, diz explicitamente que o fixo recebe a ligação) ou Avoip
(a única que fala da API oficial) — pedir confirmação às duas e ficar com a que responder sim
às cinco perguntas. Plano mensal, sem fidelidade longa: é um teste.

⚠️ Regras que valem para qualquer um: o número **não pode estar ativo no app WhatsApp** (se
estiver, apagar a conta nele antes), e o nome exibido passa por aprovação da Meta.
🔑 **Recomendação: um número SÓ para o assistente interno**, separado do que fala com clientes
(o 47 99910-5033). Mistura de cliente e funcionário no mesmo número confunde o roteamento, a
cobrança e quem pode o quê. 🔑 **E um só para a casa toda** (decisão do dono, 06/11/2026): quem
tem duas lojas pergunta uma vez e recebe as pendências das duas — ele mora em Integrações, não
na loja.
❌ **Não usar provedor não oficial** (Z-API, Evolution e afins, que imitam o WhatsApp Web): o
próprio `whatsapp-estudo.md` já descartou — risco de banimento.

**Custo de mensagem:** quando o funcionário escreve primeiro, abre-se a janela de 24 h e as
respostas dentro dela não são cobradas pela Meta. Só pagaria a mensagem que o **sistema inicia**
(ex.: "bom dia, suas pendências") — um modelo de *utilidade*, centavos. Conferir tabela no dia.

## 3. Como funciona por dentro

```
Funcionário (WhatsApp)
   │ texto ou áudio
   ▼
Meta ──webhook──► POST /whatsapp/webhook   (já existe; ganha o ramo "número do assistente")
                      │
                      ├─ 1. quem é? telefone → usuário (vínculo verificado, ver §4)
                      ├─ 2. áudio? baixa da Meta e transcreve → texto
                      ├─ 3. conversa: Claude API + ferramentas de mcp_ferramentas,
                      │      chamadas com a credencial DESSE usuário
                      ├─ 4. gravação? pergunta antes, com botões [Confirmar] [Cancelar]
                      └─ 5. responde pela Cloud API (texto livre, dentro das 24 h)
```

Peças novas:
1. **Vínculo telefone ↔ usuário** — coluna/tabela nova (`usuario_whatsapp`: telefone E.164,
   verificado_em, ativo). Migração idempotente, como sempre.
2. **Conversa** — `assistente_conversas` / `assistente_mensagens`: histórico curto (últimas
   N mensagens ou 2 h) para o "pode lançar" saber do que se fala, e a ação pendente de
   confirmação.
3. **O laço do Claude** — `services/assistente.py`: monta o pedido à API da Anthropic com as
   ferramentas do catálogo (o mesmo `FERRAMENTAS`, filtrado pela chave do usuário), executa as
   chamadas com `mcp_ferramentas.chamar` e devolve o texto. ⚠️ Rodar **fora** do webhook (fila,
   como o `laco` do WhatsApp): a Meta quer resposta 200 rápida e reenvia se demorar.
4. **Transcrição de áudio** — o WhatsApp entrega o áudio em OGG/Opus. Hoje o caminho seguro é
   transcrever num serviço de fala-para-texto (Whisper e similares, cobrança por minuto, centavos)
   e mandar o texto ao Claude. Rodar Whisper dentro do App Platform não compensa (CPU/memória).
   Conferir no dia se a API do Claude já aceita áudio direto — se sim, uma peça a menos.
5. **Respostas curtas** — instrução de sistema própria: "você fala por WhatsApp; respostas
   curtas; listas de no máximo 10 itens; quantidades com unidade". A ficha técnica vai formatada
   para tela de celular.

## 4. Segurança — onde está o risco

- 🔴 **O telefone é a senha.** Vincular exige prova: o usuário cadastra o número na tela (Meu
  usuário), o sistema mostra um código, e ele manda esse código para o número do assistente.
  Só então liga. Número desconhecido recebe "este número não está vinculado" e nada mais.
- **Permissão própria** `integracao.whatsapp_assistente` — o dono decide quem tem o assistente.
- **Mesmas permissões da tela**: a chave interna do assistente é do usuário; quem não pode lançar
  produção na tela também não pode pelo WhatsApp. "Permite alterar" separado, como no conector.
- 🔑 **Toda gravação pede confirmação explícita por botão**, mostrando a prévia (o que vai baixar
  de insumo, o que entra). Texto "sim" solto não basta — botão tem id, não se confunde com
  conversa. Confirmação expira em minutos.
- **Auditoria** marca a origem `whatsapp` em tudo que o assistente grava.
- Teto de uso por usuário/dia (custo da Anthropic e da transcrição) e desligamento por loja.
- LGPD: áudio não fica guardado depois de transcrito; histórico de conversa com prazo.

## 5. Ordem de construção sugerida

1. **Número + vínculo** ✅ *código entregue na 1.3.5 (migração 151) — falta o número de
   verdade*: número da casa em Integrações ▸ Assistente; Perfil ▸ Assistente no WhatsApp com código;
   webhook reconhece o funcionário e responde "olá, Fulano". Detalhes em
   `docs/memoria/administrativo.md`.
2. **Só leitura por texto** ✅ *1.3.6 (migração 152)*: pendências, receita, saldo, vendas de
   ontem, com as 96 ferramentas de leitura do conector, em todas as lojas do usuário. Sem gravar
   nada. Modelo e limite diário em Integrações ▸ Assistente.
3. **Áudio** ✅ *1.3.7 (migração 153)*: transcrição pela OpenAI ou pela Groq (mesmo formato de API,
   escolha em Integrações ▸ Assistente); a resposta mostra o que foi ouvido.
4. **Gravação com confirmação** ✅ *1.3.8 (migração 154)*: produzir da agenda e produção avulsa,
   com prévia do sistema e botão Confirmar (permissão própria). Etiqueta e saída/perda ficam para
   depois, pela mesma trilha.
5. **Bom dia proativo** ✅ *1.3.9 (migração 155)* — com a contagem da agenda e os botões "Ver
   pendências" / "Parar o bom dia"; casa liga em Integrações, cada pessoa no Perfil. Era (opcional): às 7h, modelo aprovado "Bom dia, {{1}}! Hoje: {{2}}" para
   quem ligou a opção — é a única parte com custo de mensagem.

Cada etapa com suíte de fumaça em modo simulado (o `whatsapp.py` já tem modo simulado; a
Anthropic e a transcrição ganham o seu), e a bateria do navegador cobrindo a tela de vínculo.

## 6. Perguntas para o dono

1. Já existe número conectado à Meta no ar (o de clientes)? Se sim, a conta Business e o app
   da Meta já estão prontos e o número do assistente entra ao lado.
2. Contratar número virtual — tem preferência de operadora, ou pesquisamos?
3. Quem terá o assistente no começo: só o dono, ou produção também?
4. Pode gravar desde o início, ou começamos só com consulta por algumas semanas?
5. O "bom dia" automático interessa, ou só responde quando chamado?

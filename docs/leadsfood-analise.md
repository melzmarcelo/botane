# LeadsFood × Portal de Clientes — o que compor

> Leitura feita em 30/10/2026 no painel da casa (`botanedeliecafe.leadsfood.com.br`) e no app
> público (`botanedeliecafe.leadsfood.app`), **só olhando** — nada criado, editado ou enviado.
> Sem dado pessoal aqui: só estrutura, números agregados e configuração.

## O retrato da casa no LeadsFood (30/10/2026)

| | |
|---|---|
| Base de contatos | **3.618** (2.937 no ano; 229 novos no mês) |
| Engajamento | 31 Morno · 20 Engajado · 12 VIP · o resto Frio |
| Reservas válidas | 170 (desde 11/2025) · 548 pessoas · **38 no-shows (22,4%)** |
| Grupos de 6+ | 57 reservas (33,5%), 509 pessoas, média 8,9 |
| Fidelidade | 127 participantes · 673 selos · 1 campanha ("10 almoços, 1 grátis") · 6 prêmios em aberto |
| QR codes | Fidelidade (631 leituras), Mesa (496), Inicial (533) |
| Cardápio | 3 catálogos (Menu Principal, Bebidas, Carta de Vinhos), 98 produtos |

Módulos **ligados** lá: reservas (aprovação manual, objetivo e observação), fila de espera,
fidelidade, avaliações com NPS, cardápio. Pagamento da reserva e roteador NPS → Google:
desligados.

## O que o Portal JÁ cobre (e em vários pontos vai além)

- **Reserva** pelo site e pelo balcão, salões/mesas/planta, calendário, bloqueios, confirmação
  automática ou manual, objetivo e observação, termo LGPD, duas lojas, EN/DE.
- **Fidelidade**: cartão por visita, QR na mesa, código de confirmação no caixa (= o PIN deles),
  selo manual com motivo, prêmio com validade e dias de consumo, painel.
- **Cardápio**: catálogos + Cardápio Vivo (pedido na mesa, vídeo, testes A/B) — o deles é só
  vitrine.
- **Clientes**: grid da rede, nascimento, gênero, cidade.
- **WhatsApp** (migração 099): reserva recebida/confirmada, lembrete com Confirmo/Cancelar,
  prêmio ganho/vencendo, aniversário. ⏳ Falta a casa concluir a parte da Meta. As "Respostas
  rápidas" deles (Confirmação, Avaliação, Aniversário, Fila) são o equivalente.

## O que eles têm e nós não — por valor

### 1. Importar a base antes de trocar (pré-requisito)
Trocar de sistema sem trazer os 127 cartões **zera o selo de quem está no meio da cartela** — o
cliente percebe no primeiro check-in. Trazer: contatos (telefone, nome, nascimento, gênero,
cidade, origem, data de cadastro), cartões com selos em aberto e os prêmios ainda não usados.
Caminho: o "Exportar" de Contatos/Prêmios/Checkins, ou a API pública deles (há token em
Configurações → Integrações). Idempotência pelo telefone, já única desde a 087.

### 2. Plano de ação de reservas — "dinheiro na mesa" ✅ feito em 30/10/2026, e o BI (Reservas ▸ Painel) também — falta só o ano contra ano
A tela mais útil deles, e **os dados já estão no nosso banco**. Listas com botão WhatsApp:
- **VIPs em risco**: 3+ reservas e não voltam há 120+ dias
- **Organizadores de grupo sumidos**: 2+ reservas de 6+ pessoas, sem voltar há 120+ dias
- **Adormecidos**: até 2 visitas, sumiram há 90+ dias (126 hoje lá)

Junto, o BI: reservas por dia da semana, por objetivo, evolução mensal, ano contra ano,
sazonalidade, taxa de no-show e o recorte de grupos grandes.

### 3. Origem do cliente + QR com contagem
Cada contato sabe de onde veio (Cardápio-link da bio, Cardápio-mesa, Catálogo de Cestas,
Catálogo de Encomendas, WhatsApp, Contato) e cada QR conta as leituras. Para nós: `origem`
no cadastro (gravada na primeira entrada, nunca sobrescrita) e um QR cadastrável com destino e
contador. O "cardápio pede o celular antes de abrir" deles é a mesma ideia do catálogo com
cadastro (086).

### 4. Ficha do cliente mais rica
Tags (com ícone, múltiplas), notas, e-mail, CPF, bairro e estado, quais campos são
obrigatórios (configurável) e idade mínima. Na ficha: histórico, reservas, check-ins e
prêmios numa tela só. Filtros prontos de **aniversariantes** (hoje, 7 dias, mês) e exportação.

### 5. Engajamento (Frio → Morno → Engajado → VIP)
Nota de 0 a 100 = **40% recência + 30% frequência + 30% qualidade**, recalculada após cada
evento e de madrugada (a recência cai com o tempo). Conta como presença: reserva comparecida,
fila sentada, check-in confirmado, avaliação, prêmio usado. **Não** conta: acessar o
cardápio, criar reserva, confirmar. No-show, cancelamento e prêmio vencido descontam. Faixas
ajustáveis por perfil (cafeteria × fine dining).

### 6. Avaliação com NPS
Pergunta de 0 a 10 depois da visita, mensagem por faixa, aviso de nota ruim por WhatsApp e
roteador: nota alta → manda para o Google. Ligado lá; não sabemos o volume.

### 7. Fila de espera
Ligado lá (estatísticas e tempo médio, chamada por WhatsApp, limite de pessoas, prioritários,
agrupamento). **Perguntar se usam de fato** antes de construir — é módulo inteiro.

### 8. Menores
- Fidelidade: limite diário de check-in por cliente, validade da cartela, **selo por valor
  gasto** (vazio lá) e "self check-in" ligável.
- Site: Facebook Pixel / Google Tag Manager.
- "Eventos recorrentes": aviso X dias antes (provavelmente aniversário).
- **LeadsAtend**: atendente de IA no WhatsApp com base de conhecimento e escolha de loja. É
  produto à parte; fica para depois do WhatsApp oficial estar no ar.

## Perguntas para a cliente
1. Usam a **fila de espera** no dia a dia? E as **avaliações/NPS** — quantas chegam?
2. Quem olha o BI/Plano de ação hoje, e manda as mensagens de reativação?
3. As **tags** que existem lá são usadas para quê?
4. Na troca, o cartão de fidelidade precisa vir com os selos? (recomendado: sim)

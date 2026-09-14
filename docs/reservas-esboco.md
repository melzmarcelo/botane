# Reservas — esboço para estudo

> Ideia do dono, 13/09/2026. **Isto é um estudo, não uma especificação fechada**:
> serve para decidir o que entra no primeiro corte e o que fica para depois.
> Nada foi construído.

O pedido: um módulo de reservas, ligado por parâmetro da loja, com o **mesmo
backend**; o controle interno em `sistema.botanedeliecafe.com.br` e um front do
cliente em `reservas.botanedeliecafe.com.br`, com seleção de loja quando houver
mais de uma com reserva ativa.

---

## O que já está pronto nesta casa — e é metade do trabalho

A lista de pilares do pedido reinventa, sem saber, várias coisas que o Botané já
tem. Mapeando antes de desenhar:

| O pedido pede | O que já existe aqui |
|---|---|
| Login individual, senha com hash, sessão com expiração | `usuarios`, `sessoes`, refresh, troca de senha obrigatória no primeiro acesso |
| Controle de acesso por função (garçom, recepção, gerente) | `papeis` + `permissoes` + `papel_permissoes`, com chave por recurso (`cadastros.produtos`) |
| **Permissão no backend, não só escondendo botão** | Já é a regra da casa: todo router declara a permissão que exige |
| Histórico de alterações / auditoria | `auditoria.registrar(cur, usuario, entidade, id, acao, antes, depois)` — usado em tudo |
| Cadastro do cliente com telefone, WhatsApp, e-mail, histórico | `fornecedores` **é a tabela de pessoas** (quem compra, quem trabalha e quem consome): nome, telefone, whatsapp, email, cupom |
| Ligar/desligar por loja | `parametros` (uma linha por `id_unidade`) — é onde moram `dia_fechamento_cmv`, `casas_decimais_qtd`… |
| Multi-loja com seleção | `unidades` + `X-Unidade` em toda requisição; o seletor de loja já existe na barra |
| Confirmação e lembrete por e-mail | `services/email.py`, com **modo simulado** que grava o `.eml` em disco quando não há SMTP |
| Backups | rotina de dump já usada antes de cada limpeza |

**O que é genuinamente novo**: mesas, disponibilidade, a reserva em si, o mapa do
salão, e o front do cliente.

⚠️ **2FA, criptografia de dados sensíveis e HTTPS** — o terceiro já existe (o App
Platform serve TLS); os dois primeiros não estão neste módulo: são decisões da
casa inteira, e entram no dia em que entrarem para todo mundo. Um módulo com 2FA
próprio seria uma segunda política de acesso para manter em dia.

---

## As quatro decisões que precisam sair antes do código

### 1. O cliente que reserva é uma "pessoa" ou é outra coisa?

A tabela `fornecedores` já é a agenda da casa: fornecedor, funcionário que
consome, e agora quem reserva. Reusá-la dá histórico de graça — a mesma pessoa
que trabalha e reserva é uma linha só.

⚠️ **O risco é misturar cadastro interno com público.** Reserva pelo site é
auto-cadastro, sem ninguém conferindo: em seis meses a agenda da casa tem mil
linhas que ninguém revisou, e a busca de fornecedor passa a devolver clientes.

**Recomendo**: mesma tabela, com o papel marcado (`cliente boolean`, como o
`fornecedor` que já existe) e **origem** registrada (balcão / site). A tela de
Pessoas filtra por papel. Se em um ano isso incomodar, separar depois é uma
migração simples; começar separado e ter de juntar é que é caro.

### 2. Um front novo ou uma rota pública no mesmo app?

O pedido fala em `reservas.botanedeliecafe.com.br`.

| | Domínio próprio | Rota pública no app de hoje |
|---|---|---|
| Infra | +1 componente no App Platform, +1 domínio, +1 build | nada |
| CORS | volta a existir (hoje não existe: web e API dividem o domínio) | continua não existindo |
| Deploy | dois artefatos para promover e conferir | um |
| Isolamento | o público nunca carrega o bundle interno | o bundle interno está lá, mesmo sem rota |

**Recomendo começar pela rota pública** (`/reservar`, sem login, fora do grupo
`(app)`), e mudar para o domínio próprio quando a reserva online estiver de pé e
valer o custo. ⚠️ Isso **não muda o backend**: a API é a mesma nos dois casos, e a
troca depois é de hospedagem, não de código.

### 3. O que "disponível" quer dizer — e onde essa regra mora

É o coração do módulo, e é onde a maioria dos sistemas de reserva erra.

A regra tem de ser **uma só, no servidor**, respondendo a uma pergunta: *dado dia,
hora e número de pessoas, o que dá para marcar?* Ela precisa considerar
capacidade da mesa, mesas que se juntam, tempo médio de permanência, intervalo
entre reservas, horário de funcionamento, dias fechados, bloqueios e o teto do
salão.

⚠️ **O cliente não escolhe mesa.** Ele vê "19:00 disponível" e a casa decide onde
sentar — é o que o pedido já diz, e é também o que evita que a escolha do cliente
trave a operação.

⚠️ **Duas pessoas reservando o mesmo horário ao mesmo tempo é o caso que define a
arquitetura.** Conferir e depois gravar é onde o overbooking nasce. Aqui já há
precedente na casa: o lançamento de estoque usa `SELECT … FOR UPDATE` no saldo, e
o lote de reembolso usa `pg_advisory_xact_lock`. A reserva fecha do mesmo jeito —
a verificação e a gravação na MESMA transação, com trava por (loja, dia).

### 4. WhatsApp fica de fora do primeiro corte

É o canal que a casa quer, e é o mais caro: exige conta no WhatsApp Business API,
provedor, modelos de mensagem aprovados e custo por conversa.

**E-mail já funciona hoje** e tem modo simulado para desenvolver sem SMTP. O
primeiro corte manda por e-mail; o WhatsApp entra como mais um "canal de aviso"
depois, sem mexer no resto.

---

## O modelo de dados, em cinco tabelas

> ⚠️ **Revisto em 14/09/2026** — ver a seção final. O salão entrou entre a loja e a
> mesa, e o horário virou tabela própria. O que está aqui é o primeiro corte do dia 13.

```
reserva_config      (id_unidade)   ← liga o módulo e guarda as regras da loja
  ligado, abertura, fechamento, dias_fechados,
  permanencia_min, intervalo_min, capacidade_salao,
  antecedencia_min_horas, antecedencia_max_dias, aceita_online

mesas               (id_unidade, nome, capacidade, capacidade_max, ativo,
                     pos_x, pos_y)        ← as duas últimas desenham o salão
mesa_grupos         (mesas que se juntam, e para quantos)

reservas            (id_unidade, id_pessoa, data, hora, pessoas, status,
                     origem, observacao_cliente, observacao_interna,
                     criado_por, criado_em)
reserva_mesas       (id_reserva, id_mesa)  ← uma reserva pode ocupar duas

bloqueios           (id_unidade, de, ate, motivo)  ← feriado, evento, manutenção
```

**Status**: `PENDENTE` → `CONFIRMADA` → `CHEGOU` → `ENCERRADA`, com `CANCELADA` e
`NAO_COMPARECEU` saindo de qualquer ponto. As cores do pedido casam com isso.

⚠️ **A reserva não se apaga: muda de status.** É a mesma disciplina do razão de
estoque — "cancelada" é um fato, e apagar a linha levaria junto a resposta para
"por que a mesa ficou vazia naquele sábado".

⚠️ **`reserva_mesas` separada** porque juntar mesas é requisito desde o começo; um
`id_mesa` na reserva obrigaria a inventar "mesa 3+4" como cadastro.

---

## O primeiro corte (MVP), na ordem de construir

1. **Parâmetro da loja** liga o módulo, e as permissões nascem (`reservas.ver`,
   `reservas.editar`, `reservas.configurar`). Sem isso o menu nem aparece.
2. **Mesas**: cadastro com capacidade. Sem mapa ainda — uma lista.
3. **A regra de disponibilidade no servidor**, com teste próprio. É a peça que
   tudo o mais consome, e a única que não pode ser refeita depois.
4. **Reserva pelo balcão**: criar, alterar, confirmar, cancelar, marcar chegada.
   Com a pessoa vindo da agenda que já existe.
5. **Agenda do dia**: a tela que a recepção olha o tempo todo — lista por horário,
   busca por nome/telefone, filtros por status.
6. **Auditoria** ligada (é uma linha por operação, e já existe).

Com isso a casa opera. **Fora do primeiro corte**, por ordem de valor:
mapa do salão (visual), reserva online, e-mail de confirmação e lembrete, lista
de espera, painel de indicadores, WhatsApp, sinal/pagamento.

⚠️ **O mapa do salão é o que mais impressiona e o que menos resolve** no começo: a
recepção precisa saber *se cabe às 20h*, e isso a regra de disponibilidade
responde sem desenho nenhum. Ele entra quando a operação já estiver rodando e o
salão já estiver cadastrado de verdade.

---

## O que eu faria diferente do esboço original

- **Sem "mesa reservada" na reserva do cliente online.** Ele reserva *lugar*, não
  *mesa*; a casa aloca. Isso evita 80% dos conflitos.
- **Sem 2FA no módulo.** Ou a casa inteira tem, ou ninguém tem.
- **Sem "tempo médio de ocupação" fixo no código**: é parâmetro por loja, e muda
  entre almoço e jantar. ⚠️ Duas permanências (almoço/jantar) é o mínimo útil.
- **A lista de espera é mais barata do que parece e vale cedo**: é a mesma tabela
  de reservas com status próprio, e resolve a sexta-feira cheia.
- **Indicadores só depois de existir dado.** Painel bonito com três reservas é
  enfeite; com três meses de agenda, é gestão.

---

## O que ainda não sei, e precisa de resposta da casa

1. **Quantas mesas e qual a capacidade?** Muda se o mapa vale a pena.
2. **A casa aceita reserva hoje, por telefone/WhatsApp?** Se sim, o primeiro
   corte precisa importar o que existe, nem que seja a mão.
3. **Reserva online precisa de confirmação da casa** (pendente → confirmada) ou
   entra confirmada direto? Muda o fluxo do cliente inteiro.
4. **Cobra sinal para grupos grandes?** Se sim, isso puxa pagamento — e pagamento
   é outro módulo, não um detalhe deste.
5. **Qual o horário de funcionamento e os dias fechados?** É o primeiro
   cadastro, e sem ele a disponibilidade não responde nada.

---

# Revisão de 14/09/2026 — o que o protótipo mudou

Depois de ver o site que a casa usa hoje (`botanedeliecafe.leadsfood.app`) e de montar um
protótipo navegável, três coisas do modelo acima ficaram erradas. O protótipo está em
[`apresentacao/reservas-prototipo.html`](../apresentacao/reservas-prototipo.html) — arquivo
local autocontido, publicado também como artifact (**republicar sempre na mesma URL**).

## Como o site de hoje se comporta

Lido da página real, em 13/09/2026:

- **Formulário de um passo só**: Dia da reserva, Horário, Pessoas, Objetivo da reserva,
  "Precisa de algo especial?" (0/2000) e CONTINUAR. Sem escolha de mesa pelo cliente.
- As regras vêm **impressas acima dos campos**: Ter-Sex 09h30–17h00, Sáb 9h–17h00,
  tolerância de 15 minutos, e **acima de 8 pessoas → WhatsApp 47 99910-5033**.
- Badge "Fechado no momento" quando fora do horário.
- O LeadsFood é um **hub**, não só reserva: cardápio, catálogos, fidelidade, selos. Foi daí
  que veio o pedido do dono — *"a reservas pode ter este mesmo estilo, onde dentro do sistema
  podemos criar catálogos, podemos importar o catálogo ou criar dentro do sistema mesmo"*.

⚠️ **O horário impresso já mostra que são DUAS horas diferentes**: "até 17h00" é a última
reserva, não o fechamento da loja — a casa fica aberta depois disso. A diferença entre as
duas é exatamente a permanência.

## A porta de entrada é o telefone

🔑 **Pedido do dono (13/09/2026):** *"pelo que vi é um cadastro simples, a partir do número de
telefone; caso tenha o número cadastrado, segue para a reserva; caso não tenha, faz o cadastro
com Nome, Data de nascimento, Gênero e Cidade. E segue para o agendamento."*

Isso resolve a decisão 1 acima de um jeito melhor do que o esboço propunha: não há login nem
senha. O telefone **é** a identidade, e é o campo pelo qual a casa já procura alguém.
`fornecedores` (a tabela de pessoas) já tem telefone e whatsapp; faltam `data_nascimento`,
`genero` e `cidade`, e a marca de origem (balcão / site).

⚠️ **Data de nascimento é dado pessoal.** Serve para o aniversário — e só vale guardar se a
casa for usar de verdade. Pedir por pedir é coletar risco sem troco. O protótipo tem um ajuste
"só o nome" justamente para a casa ver como fica sem.

## O modelo revisto

O que muda em relação às cinco tabelas do dia 13:

```
reserva_config      (id_unidade)
  ligado, aceita_online, folga_min, passo_min, tolerancia_min,
  antecedencia_min_horas, antecedencia_max_dias, teto_online

reserva_horarios    (id_unidade, dia_semana 0-6, aberto,
                     abre, fecha, ultima_reserva)          ← NOVA
reserva_permanencias(id_unidade, nome, de, ate, minutos)   ← NOVA

saloes              (id_unidade, nome, ativo)              ← NOVA
mesas               (id_unidade, id_salao, nome, lugares, capacidade_max,
                     junta_com, ativo, pos_x, pos_y)
reservas            (…como antes…)
reserva_mesas       (id_reserva, id_mesa)
bloqueios           (id_unidade, de, ate, motivo)
```

**1. `reserva_horarios` é tabela, não campo.** O esboço tinha `abertura`/`fechamento` na
config e `dias_fechados` como lista. Mas sábado abre 9h e fecha 18h30, e terça a sexta abrem
9h30 e fecham 18h — são horários **por dia da semana**, e cada dia carrega as três horas
(abre, fecha, última reserva). `dias_fechados` vira o `aberto` de cada linha; `bloqueios`
continua existindo para o que é pontual (feriado, evento, manutenção).

**2. `saloes` entra entre a loja e a mesa.** Salão principal, Varanda, Mezanino. Desligar o
salão tira as mesas dele da disponibilidade sem apagar cadastro nenhum — é a Varanda no
inverno. ⚠️ **Salão com mesa não se remove, desliga**: apagar levaria junto a resposta para
"onde aquela reserva de agosto sentou".

**3. `permanencia_min` vira faixa.** Um número só para o dia inteiro erra nas duas pontas:
café da manhã não segura a mesa como um almoço. Três faixas já resolvem esta casa (café 60,
almoço 90, tarde 60). É o que o próprio esboço já recomendava ("duas permanências é o mínimo
útil") — só que agora com hora de início e fim, porque é a hora da reserva que escolhe a faixa.

**4. Lugares e máximo são dois números.** `lugares` é o confortável; `capacidade_max` é com a
cadeira extra. A alocação usa o máximo, o relatório usa os lugares. Um campo só obriga a
escolher entre mentir para o cliente e recusar mesa que caberia.

**5. `junta_com` no lugar de `mesa_grupos`.** Para o caso real desta casa — a mesa vizinha que
encosta — um vínculo entre duas mesas basta, e é o que a recepção entende. ⚠️ **A junta vale
nos dois sentidos**: gravar de um lado só deixa a alocação achando um par que a outra mesa não
conhece. Se um dia aparecer "juntar três", aí sim `mesa_grupos` volta.

## A regra de disponibilidade, escrita

O protótipo implementa a regra inteira, e ela cabe em poucas linhas — o valor está em que ela
mora em **um lugar só** (no servidor, no sistema de verdade):

1. As mesas candidatas são as **ativas de salões ativos**.
2. Uma mesa está presa no horário `H` se existe reserva `R` **não cancelada e não
   não-comparecida** cujo intervalo `[R.hora, R.hora + permanência(R.hora) + folga)` cruza
   `[H, H + permanência(H) + folga)`.
3. Cabe o grupo de `P` pessoas se houver mesa livre com `capacidade_max >= P` — **a menor que
   serve** — ou um par `junta_com` com as duas livres e a soma dos máximos `>= P`.

⚠️ **"Esgotado" depende do tamanho do grupo.** No protótipo, sábado às 12:00 não tem mesa para
6 e tem para 2. Por isso lotação não é um número só, e por isso a lista de horários precisa ser
calculada **depois** de o cliente dizer quantas pessoas são.

⚠️ **Contar lugares livres não serve.** Quatro lugares livres em duas mesas de dois não sentam
um grupo de quatro. A regra tem de alocar mesa, não somar cadeira.

## Duas regras novas que o protótipo revelou

⚠️ **Reserva `PENDENTE` já segura a mesa.** Se não segurasse, a casa aprovaria no dia seguinte
e descobriria que não cabe. Pendente é reserva; só `CANCELADA` e `NAO_COMPARECEU` soltam.

⚠️ **O teto do site tem de caber no salão.** Se `teto_online` passar do que a maior mesa (ou
junta) acomoda, quem pedir mais que isso não acha horário nenhum e não descobre por quê. A
tela de configuração precisa avisar — o protótipo já avisa.

## O que o protótipo deixa pronto para a conversa

O ajuste **"depois de reservar: confirma na hora × fica aguardando a casa"** existe para
resolver a pergunta 3 das cinco abertas. É a única que muda o fluxo do cliente inteiro, e o
site de hoje não deixa ver de fora qual é.

Continuam sem resposta: quantas mesas de verdade (o protótipo chutou 12 em 2 salões), se a
casa aceita reserva por telefone hoje e precisa importar o que existe, e se cobra sinal para
grupo grande.

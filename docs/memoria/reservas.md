# Reservas

> O módulo de reserva de mesa: parâmetro da loja, configuração, e — depois —
> salões, mesas, agenda e a reserva em si.
> Leia antes de mexer neste módulo.

O estudo que originou tudo está em [`../reservas-esboco.md`](../reservas-esboco.md),
com a revisão de 14/09/2026 no fim. O protótipo navegável, que é onde as telas
foram acertadas com o dono antes de existirem, está em
[`../../apresentacao/reservas-prototipo.html`](../../apresentacao/reservas-prototipo.html).

## O que já existe (migração 068, 14/09/2026)

🔑 **Pedido do dono:** *"isto tudo vai ser habilitado via parâmetro na loja,
podemos iniciar criando este parâmetro e colocando no menu, caso habilitado a
opção de Reservas. E a primeira tela que é as configurações, e também, caso
tenha habilitado, disponibilizar nas permissões dos usuários os itens de Reserva
que vamos criando."*

- **`parametros.reservas_ligado`** é o interruptor, uma loja de cada vez.
  ⚠️ **Ele mora em `parametros`, não em `reserva_config`**: é de lá que a tela de
  Lojas já lê e escreve (`_CAMPOS_PARAM` sai do próprio modelo Pydantic, então
  o GET e o PUT o conhecem sem uma linha a mais) e é de lá que o `/auth/me`
  responde ao menu sem uma consulta extra. `reserva_config` guarda **como** o
  módulo se comporta; `parametros` diz **se** ele existe nesta loja.

- 🔑 **Ligar muda TRÊS coisas, e é isso que justifica o interruptor existir.** O
  commit anterior (`b3c21b5`) tinha acabado de tirar da tela de Lojas dois
  interruptores que ninguém lia — configuração que não muda nada ensina que a
  tela mente. Este muda: (1) o grupo Reservas no menu, (2) o acesso às telas e
  (3) a oferta das chaves `reservas.*` no catálogo de permissões.

- **Três permissões**: `reservas.ver`, `reservas.editar`, `reservas.configurar`.
  A divisão é a mesma que Transferências já faz entre enviar e receber: quem
  atende o telefone precisa marcar e cancelar, e não precisa poder mudar o
  horário de funcionamento da casa.

- **A primeira tela é `/reservas/configuracoes`**: horário de funcionamento,
  permanência e as regras da reserva.

## As armadilhas que este primeiro corte já pagou

- ⚠️ **`response_model` recorta o que não está no modelo.** `reservas_ligado`
  foi acrescentado ao dict de `/auth/me` e voltou **nulo**: faltava em
  `MeResponse`. É a mesma armadilha que o `porcao_qtd` da ficha já tinha pago —
  campo novo numa resposta com `response_model` precisa dos DOIS lugares.

- ⚠️ **A migração 002 re-semeia os papéis de sistema a cada start, e roda ANTES
  desta.** "Administrador: tudo" é um `CROSS JOIN permissoes` — só que, na
  primeira subida depois do deploy, o catálogo dela ainda não tem `reservas.*`.
  O administrador ficaria sem as chaves até o restart SEGUINTE, e um módulo que
  só funciona na segunda vez que o servidor sobe é o tipo de coisa que ninguém
  relaciona à causa. Por isso a **068 concede explicitamente**: Administrador e
  Gerente por regra, e **Salão** ganha ver e editar (garçom e recepção são quem
  atende o telefone). ⚠️ Conceder não liga nada — o módulo segue desligado em
  toda loja, e até lá as chaves nem aparecem no catálogo.

- ⚠️ **O catálogo de permissões pergunta "alguma loja", não "a loja atual"**
  (`ligado_em_alguma_loja`). Papel é global — não tem loja —, então filtrar pela
  loja do seletor faria o catálogo mudar conforme a loja escolhida, e um papel
  montado numa loja pareceria quebrado na outra.

- ⚠️ **Esconder do catálogo NÃO revoga nada.** Quem já tem a chave continua com
  ela, e as rotas continuam exigindo a permissão. Desligar o módulo é tirar da
  vitrine, não confiscar: religar devolve a lista como estava, sem ninguém ter
  de refazer papel. Quem recusa uma loja desligada é a trava do router (409),
  não a ausência da permissão.

- ⚠️ **A suíte precisou MONTAR o estado virgem, e a razão é outra checagem
  dela.** A seção 7 prova que desligar não apaga a configuração; logo a rodada
  seguinte encontrava a semana da rodada anterior e a seção 4 acusava de defeito
  exatamente o comportamento que a 7 exige. Quatro checagens caíram na primeira
  bateria por isso. Suíte que afirma "nasce assim" tem de apagar antes.

## As decisões de desenho

- 🔑 **São TRÊS horas por dia, não uma.** `abre` e `fecha` são a loja;
  `ultima_reserva` é até quando a agenda aceita marcar. O site que a casa usa
  hoje anuncia "Ter-Sex 09h30–17h00", e 17h ali é a **última reserva** — a casa
  continua aberta depois disso. A diferença entre as duas é exatamente a
  permanência de quem senta por último.

- 🔑 **`reserva_horarios` é TABELA, não campo.** Sábado abre 9h e fecha 18h30;
  terça a sexta abrem 9h30 e fecham 18h. Um par `abertura`/`fechamento` na
  configuração não teria como dizer isso, e `dias_fechados` como lista só
  responderia metade.

- ⚠️ **`dia_semana` é ISO: 1 = segunda … 7 = domingo**, igual ao
  `parametros.fechamento_dia_semana` que já existia, e igual ao que
  `extract(isodow from data)` devolve. **NÃO** é o `dow` do Postgres (0 =
  domingo) nem o `Date.getDay()` do JavaScript. O servidor manda a semana pronta
  com nome e ordem, justamente para não haver um segundo jeito de contar os dias
  dentro da tela. Duas convenções de dia da semana no mesmo sistema não dão erro
  em lugar nenhum: só marcam no dia errado.

- 🔑 **A permanência não descreve a casa: ela DECIDE disponibilidade.** É o que
  diz quando a mesa das 12h volta a aparecer como livre. Curta demais vende mesa
  ocupada; longa demais recusa mesa vazia. Nenhum dos dois erros aparece na
  tela — os dois aparecem no salão. Por isso é faixa (café 60, almoço 90, tarde
  60) e não um número só: um valor para o dia inteiro erra nas duas pontas.

- ⚠️ **Faixas de permanência não podem se sobrepor** (validado no modelo).
  Sobrepondo, duas respostas valeriam para a mesma hora e o cálculo pegaria a
  primeira — a mesa liberaria num horário que depende da ORDEM das linhas.

- 🔑 **A casa nasce FECHADA em todos os dias, e a tela DIZ isso.** Semear
  "segunda a sábado, 9h às 18h" faria a agenda afirmar um horário que ninguém
  conferiu. Mas nascer fechada sem avisar pareceria pronta — então o servidor
  devolve `dias_abertos` e a tela mostra o aviso. ⚠️ **As faixas, ao contrário,
  já nascem preenchidas**: elas não afirmam que a casa abre, só dizem quanto
  tempo uma refeição dura, e nascer vazio esconderia o conceito.

- ⚠️ **Dia fechado GUARDA o horário dele**: reabrir a segunda não obriga a
  redigitar. Por isso a validação da janela vale mesmo com o dia desmarcado —
  deixar passar um par inválido enquanto está fechado só adiaria o erro.

- ⚠️ **A configuração nasce na PRIMEIRA VISITA** (`_garantir`), como
  `parametros`. Semear na criação da loja obrigaria a lembrar disto em dois
  lugares, e o segundo nasceria sem — e ainda deixaria de fora as lojas que já
  existiam antes do módulo. ⚠️ As faixas só são semeadas quando **não há
  nenhuma**: semear uma a uma com `ON CONFLICT` faria a faixa que a casa apagou
  de propósito voltar sozinha na visita seguinte.

- ⚠️ **As faixas são REESCRITAS no salvar; os horários, ATUALIZADOS.** Faixa é
  regra de cálculo e ninguém aponta para ela — casar linha a linha só abriria
  caminho para faixa órfã. Já os sete dias têm chave (loja, dia) e precisam
  continuar existindo: apagar e reinserir faria a semana sumir dentro da
  transação, e um erro no meio deixaria a loja sem horário nenhum.

- ⚠️ **A configuração FICA na limpeza da base** (`PRESERVADAS` em
  `limpar_dados.py`): horário e permanência descrevem a casa, não a operação.
  🔑 **Mas as reservas em si, quando existirem, vão para `OPERACAO`** — elas
  apontarão para pessoas e mesas, que saem no TRUNCATE, e o guarda do script vai
  apitar no dia em que a tabela nascer.

## O que vem a seguir

Pela ordem do esboço, e nenhum deles começou:

1. **Salões e mesas** — cadastro com lugares, capacidade máxima e a mesa que
   junta. ⚠️ `lugares` (o confortável) e `capacidade_max` (com a cadeira extra)
   são dois números: a alocação usa o máximo, o relatório usa os lugares.
2. **A regra de disponibilidade no servidor**, com teste próprio. É a peça que
   tudo o mais consome e a única que não pode ser refeita depois. O protótipo já
   a implementa inteira em JavaScript — serve de especificação executável.
3. **Reserva pelo balcão** e a **agenda do dia**.
4. Só então a reserva online.

⚠️ **Duas regras que o protótipo revelou e que precisam valer desde a primeira
linha de código da agenda**: reserva `PENDENTE` já segura a mesa (senão a casa
aprova no dia seguinte e descobre que não cabe), e o teto do site tem de caber
no salão (quem pede mais que a maior junta não acha horário e não sabe por quê).

⚠️ **E a pergunta que continua aberta**: reserva online entra `PENDENTE` ou
`CONFIRMADA`? O campo `reserva_config.confirmacao` já existe e já é editável na
tela — a decisão é da casa, e agora ela tem onde ser tomada.

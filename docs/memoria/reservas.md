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

## Salões e mesas (migração 069, 14/09/2026)

🔑 **Pedido do dono:** *"para controle interno, ter o cadastro de salões, cadastro de
mesas, lugares por mesas."*

- 🔑 **O salão entra ENTRE a loja e a mesa**, e não é hierarquia decorativa: desligar o
  salão tira as mesas dele da disponibilidade sem apagar cadastro nenhum — é a Varanda no
  inverno, o Mezanino que só abre no fim de semana. Sem ele, a casa teria de desligar mesa
  por mesa e lembrar de religar todas.
  ⚠️ **`_mesas_vivas` exige as DUAS condições** (mesa ativa E salão ativo). Olhar só
  `mesas.ativo` faria o salão desligado continuar recebendo reserva, e ninguém entenderia.

- 🔑 **`lugares` e `capacidade_max` são dois números.** Lugares é o confortável; máximo é
  com a cadeira extra. A **alocação usa o máximo**, o relatório de ocupação usa os lugares.
  Um campo só obrigaria a escolher entre mentir para o cliente e recusar mesa que caberia.
  ⚠️ A coerência é verificada entre o valor NOVO e o que FICA, não entre dois novos: quem
  manda só `lugares` num PUT é comparado ao máximo já gravado. Sem isso dava para subir os
  lugares acima do máximo antigo e o banco só reclamaria no `UPDATE` seguinte.

- 🔑 **`junta_com` é RELAÇÃO, não atributo**, e é assim que um grupo de 8 senta em duas
  mesas de 4 sem ninguém cadastrar uma "mesa 7+8" que não existe no salão.
  ⚠️ **Vale nos dois sentidos, e quem garante é `casar_junta`.** Gravar de um lado só
  deixaria a alocação achando um par que a outra mesa não conhece — a 07 diria "encosto na
  08" e a 08 diria "não encosto em ninguém", e qual vale dependeria de por onde a consulta
  entrou.
  ⚠️ **Desfaz a junta anterior dos DOIS lados antes de criar a nova**, senão trocar o par
  da 07 da 08 para a 09 deixaria um triângulo que nenhuma das três descreve.
  ⚠️ **"Não mandou" e "mandou nulo" são coisas diferentes** — o router separa por
  `model_fields_set`. Sem isso, renomear a mesa 07 soltaria a 08 sem ninguém pedir.
  ⚠️ Mesas de salões DIFERENTES podem encostar (a da porta da varanda com a do canto do
  principal): a lista de candidatas exclui só a própria mesa.

- 🔑 **`maior_grupo` existe para comparar com `teto_online`**, e viaja nas duas respostas
  (salão e configuração). Se o teto do site passar do que a maior mesa — ou junta —
  acomoda, **quem pedir mais não acha horário nenhum e não sabe por quê**: a tela de
  disponibilidade não tem como explicar que o problema é o cadastro. Foi uma das duas
  descobertas do protótipo.

- ⚠️ **Chave composta `(id, id_unidade)` em `saloes`**, com a `mesas` se pendurando nela.
  Sem isso nada impediria uma mesa da loja A de apontar para um salão da loja B, e o erro
  só apareceria no dia em que a filial mostrasse uma mesa que não é dela.

- ⚠️ **Salão com mesa NÃO se exclui** (409, com a mensagem mandando desligar): o
  `ON DELETE CASCADE` da chave composta levaria as mesas junto, e com elas a resposta para
  "onde aquela reserva de agosto sentou".

- ⚠️ **Mesa se exclui enquanto ninguém sentou nela — e quem vai barrar é o BANCO.** Quando
  `reserva_mesas` nascer, a chave estrangeira dela recusa apagar mesa que já hospedou
  reserva, e a rota passa a devolver o erro sem ninguém ter de lembrar de acrescentar a
  regra. Mesma escolha de `_quem_referencia` em `limpar_dados.py`: perguntar ao Postgres em
  vez de manter uma lista que envelhece.
  ⚠️ Apagar solta a vizinha ANTES do `DELETE`: o `ON DELETE SET NULL` faria isso, mas
  depois — e a resposta desta transação já teria saído com o valor velho.

- ⚠️ **Cada recurso com o seu endereço, e não um PUT que reescreve tudo** (ao contrário da
  configuração). Ali as faixas não são apontadas por ninguém; aqui a mesa vai ser, e apagar
  e reinserir a cada gravação trocaria o `id` da mesma mesa física — a reserva de sábado
  passaria a apontar para outra.

- ⚠️ **`pos_x`/`pos_y` já existem e o mapa NÃO entra agora.** A recepção precisa saber *se
  cabe às 20h*, e isso a regra de disponibilidade responde sem desenho nenhum. As colunas
  ficam para não precisar de migração no dia.

## A usabilidade do cadastro (mesmo dia, depois de ver a tela)

🔑 **Pedido do dono:** *"daria para melhorar a usabilidade do cadastro do salão,
principalmente no cadastro de mesas que pode se tornar bem extenso. Poderia ser separado
por salão."*

- 🔑 **Um salão de cada vez, em abas.** A primeira versão empilhava um cartão por salão: a
  página crescia com o total de mesas da CASA. Agora ela tem o tamanho de um salão.
  ⚠️ A aba mora no ENDEREÇO (`useEstadoNaUrl`, sem atraso — aba é clique, não digitação),
  então recarregar, voltar e guardar o link caem no mesmo salão. Endereço apontando para
  salão que já não existe cai no primeiro, em vez de numa tela vazia sem explicação.
- 🔑 **A edição do salão foi para DENTRO da aba dele.** Antes havia uma tabela de salões no
  topo e os cartões embaixo — duas respostas para "onde eu mexo neste salão".
- ⚠️ **O seletor de junta continua oferecendo mesas de OUTROS salões** (a da porta da
  varanda encosta na do canto do principal), mas o nome do salão viaja junto na opção:
  "03" sozinho não diz de onde é.
- 🔑 **`POST /reservas/mesas/em-lote`** monta o salão de uma vez. É o trabalho real do
  cadastro, e acontece uma vez só — no dia em que a casa entra no sistema, que é
  exatamente quando ninguém tem paciência para clicar "+ mesa" doze vezes.
  ⚠️ **Pula os nomes já usados em vez de recusar o lote**: o nome é único por LOJA, e "já
  existe a 03" seria resposta inútil para quem só quis mais dez mesas. A busca do nome
  livre tem teto — sem ele, um prefixo que colidisse com tudo faria o laço rodar para
  sempre segurando a transação, e o sintoma seria a tela pendurada, não um erro.

### Três armadilhas de TESTE que esta fatia pagou

Nenhuma era defeito de produto, e as três são da mesma família — **o teste afirmando ter
esperado por algo que não provava o que ele achava**:

- ⚠️ **`clicarQuando` recebia a fonte de uma RegExp, e o rótulo dos botões começa com
  "+".** Escapar aquilo custou duas tentativas (a barra se perdia no caminho até o
  arquivo), e `new RegExp("+ salão")` estourava com "nothing to repeat" — derrubando a
  bateria INTEIRA, não só a checagem. Agora casa por **texto puro**: botão se identifica
  pelo que está escrito nele, e regex ali só acrescentava uma linguagem a mais para errar.
- ⚠️ **`esperarTexto` inclui o VALOR DOS CAMPOS.** A fase esperava por "Principal …" logo
  depois de DIGITAR esse texto no input do salão novo: a espera casava no mesmo instante
  com o que a própria bateria tinha escrito, e o endereço era lido antes de a ida ao
  servidor voltar. O texto estava certo e mesmo assim não provava nada. Agora espera o
  ENDEREÇO. ⚠️ É a mesma propriedade que, do lado oposto, fez uma checagem procurar em
  `innerText` o nome de uma faixa que morava num `<input>`.
- ⚠️ **Espera fixa de 1,5 s numa tela que carrega por XHR** (o seletor de versão da ficha):
  passou em duas rodadas e caiu na terceira, sem ninguém tocar na tela. Virou
  `waitForSelector`.

## A regra de disponibilidade e a reserva (migrações 070, 14/09/2026)

🔑 **É o coração do módulo, e onde a maioria dos sistemas de reserva erra.** Mora em
`services/reservas_agenda.py`, num lugar só: a tela consulta a MESMA regra que a gravação
aplica. O protótipo já a implementava em JavaScript e serviu de especificação executável.

A regra: as candidatas são as mesas **ativas de salões ativos**; uma mesa está presa se
alguma reserva viva cruza `[hora, hora + permanência + folga)`; cabe se houver mesa livre
com `capacidade_max >= N` — **a menor que serve** — ou uma junta com as duas livres.

- ⚠️ **"Esgotado" depende do TAMANHO DO GRUPO.** Às 12h pode não haver mesa para 6 e haver
  para 2. Por isso a tela pergunta as pessoas **antes** do horário: a ordem é a regra, não
  preferência de layout.
- ⚠️ **Contar lugares livres não serve.** Seis lugares livres numa mesa de 2 e numa de 4 não
  sentam um grupo de 5. A regra aloca MESA.
- 🔑 **Mesa inteira ganha da JUNTA, e isso é produto.** Juntar mesas é trabalho físico e
  fragmenta o salão: só se faz quando não há mesa que sirva. ⚠️ A primeira versão da suíte
  esperava a junta com a mesa de 6 ainda livre e **acusou de defeito o comportamento certo**.
- 🔑 **A menor mesa que serve, não a primeira que couber.** Pôr um casal na mesa de 8 é o que
  faz o grupo de 8 não caber meia hora depois — e a recusa apareceria como "esgotado" sem
  nada no salão estar cheio.
- ⚠️ **Reserva PENDENTE segura a mesa.** Só `CANCELADA` e `NAO_COMPARECEU` soltam.
  `ENCERRADA` continua segurando: a mesa FOI usada, e a agenda tem de continuar explicando
  por que esteve ocupada.
- ⚠️ **Verificação e gravação na MESMA transação**, com `pg_advisory_xact_lock` por
  (loja, dia). É o caso que define a arquitetura — conferir e depois gravar é onde o
  overbooking nasce. Precedente da casa: `SELECT … FOR UPDATE` no razão, o lote de reembolso
  do outro sistema.
- ⚠️ **O teto e a antecedência valem para o SITE, não para o balcão.** Quem liga fala com
  uma pessoa, e essa pessoa pode aceitar um grupo maior sabendo que vai juntar mesas na mão.
- ⚠️ **`reserva_bloqueios` é diferente de fechar o dia da semana**: o horário vale toda
  semana, o bloqueio vale uma vez. Resolver o Natal desmarcando a quarta fecharia todas as
  quartas do ano. E o bloqueio **não cancela o que já estava marcado** — a casa precisa da
  lista para ligar para cada um; a resposta diz quantas são.

### Remarcar

🔑 **É a ligação mais comum depois de marcar** (*"dá para passar para as 13h?"*). Sem ela, a
recepção cancelaria e recriaria, perdendo o histórico.

- ⚠️ **A reserva não pode disputar mesa CONSIGO MESMA**: passar das 12h para as 12h30
  esbarraria na própria permanência, e o sistema diria "não há mesa" apontando para a mesa
  que ela mesma ocupa. É para isso que `disponibilidade` tem o `ignorar`, e o remarcar é o
  único chamador dele.
- ⚠️ **Mudando de dia, os DOIS dias são travados — do menor para o maior.** Sem a ordem
  fixa, remarcar sábado→domingo e domingo→sábado ao mesmo tempo daria impasse: cada um
  seguraria o dia que o outro espera.
- ⚠️ **Falhando, a reserva fica COMO ESTAVA.** Uma remarcação recusada que deixasse a
  reserva sem mesa seria pior que a recusa.
- ⚠️ **Só o que ainda não sentou se remarca.** `CHEGOU` quer dizer que as pessoas estão na
  mesa; mudar o horário delas não descreve nada que aconteça no salão.

### O 500 que virou 409, e a promessa que se fechou

🔑 A migração 069 prometia que apagar mesa com reserva seria barrado "pelo BANCO, quando
`reserva_mesas` nascer". Nasceu com `ON DELETE RESTRICT` e barrou — **com um 500 e texto de
Postgres**, que derrubou a bateria do navegador inteira num "Internal Server Error".
⚠️ **Quem GARANTE é o banco; quem EXPLICA é a rota.** A pergunta antes não substitui a chave
estrangeira (é ela que não envelhece quando outra tabela apontar para `mesas`) — acrescenta
a frase em português, como `_recusar_nome_repetido` faz com o índice único.
⚠️ E a suíte afirmava só `st >= 400`, o que **deixou o 500 passar**. Virou `st == 409` com a
mensagem.

## O que vem a seguir

⚠️ **Esta lista esteve ERRADA por uma semana, e o erro é instrutivo.** Ela dizia
"nenhum deles começou" sobre os itens 2 e 3 — que a migração 070 já tinha
entregado, e que as seções acima deste mesmo arquivo descrevem em detalhe. Foi
escrita quando era verdade e não foi revista quando deixou de ser.
🔑 **Lista de pendências envelhece pior que decisão**: a decisão continua
valendo, a pendência vira mentira no dia em que alguém a cumpre. Ao fechar uma
fatia, o risco a fechar junto é esta seção.

Pela ordem do esboço (conferido no código em 21/09/2026):

1. ~~Salões e mesas~~ — **feito**, migração 069.
2. ~~A regra de disponibilidade no servidor, com teste próprio~~ — **feito**,
   migração 070. Mora em `services/reservas_agenda.py`; a seção "A regra de
   disponibilidade e a reserva" acima é a documentação dela.
3. ~~Reserva pelo balcão e a agenda do dia~~ — **feito**, migração 070, com
   ciclo de status, remarcar e bloqueios.
4. **A reserva pelo site do cliente — o único que não começou.**

**O que o módulo tem hoje**, medido: 18 rotas em `routers/reservas.py`, os dois
serviços (`reservas.py` e `reservas_agenda.py`), quatro telas
(`agenda`, `salao`, `configuracoes` e o `escolher-horario.tsx` que as duas
primeiras compartilham), **166 checagens** em três suítes de API
(`smoke_reservas_config`, `_disponibilidade`, `_salao`) e **55 checagens de
navegador** na fase 12 da bateria — incluindo o caso de estar desligado.

⚠️ **E ele está DESLIGADO em todas as lojas** (`reservas_ligado = false`), o que
é o nascimento certo — ver a primeira seção — mas quer dizer que nada disto está
em uso. Construído e testado não é o mesmo que ligado: quem for avaliar o módulo
precisa acender o interruptor na tela de Lojas primeiro, senão encontra um menu
sem o grupo e conclui que não existe.

⚠️ **O terreno da reserva online já está preparado**, e é de propósito:
`reserva_config` tem `aceita_online` (hoje `false`), `teto_online` e
`confirmacao`, e a regra que o site consumiria é a MESMA que a agenda usa. Não
há uma segunda regra a escrever — há uma porta a abrir.

⚠️ **Duas regras que o protótipo revelou e que precisam valer desde a primeira
linha de código da agenda**: reserva `PENDENTE` já segura a mesa (senão a casa
aprova no dia seguinte e descobre que não cabe), e o teto do site tem de caber
no salão (quem pede mais que a maior junta não acha horário e não sabe por quê).
🔑 A primeira **já vale** — ver "Reserva PENDENTE segura a mesa" acima. A
segunda espera a reserva online, e é o que `maior_grupo` existe para comparar.

⚠️ **E a pergunta que continua aberta**: reserva online entra `PENDENTE` ou
`CONFIRMADA`? O campo `reserva_config.confirmacao` já existe, já é editável na
tela e está em `AUTOMATICA` — a decisão é da casa, e agora ela tem onde ser
tomada.

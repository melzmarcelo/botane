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

## O site do cliente (21/09/2026)

🔑 **Pedido do dono:** *"agora vamos criar o site para o cliente, onde o front será separado,
no oficial vamos colocar em `reserva.botanedeliecafe.com.br`. Os itens serão: Reserva,
Catálogos cadastrados e ativos, Entre em Contato (onde vai abrir o whatsapp para enviar
mensagem para o número cadastrado para a empresa). Montar assim e depois vamos melhorando."*

⚠️ **O esboço recomendava rota pública no mesmo app; o dono escolheu front separado.** A
decisão é dele e está tomada — e o que o esboço previa como preço é exatamente o que
aconteceu: **o CORS voltou a existir**. Hoje `web` e `api` dividem o domínio e o problema não
existe; com o site em `reserva.…` ele precisa da origem em `CORS_ORIGINS`, senão o site sobe,
abre bonito e **não carrega nada** — sem cardápio, sem horário e sem o WhatsApp. E o navegador
não diz por quê na tela.

- **`site/index.html`**, sem build. São três telas que leem a API: um arquivo que abre direto
  carrega mais rápido no celular de quem está na rua do que qualquer bundle, publica como site
  estático e não tem build para quebrar numa promoção. ⚠️ **É decisão de hoje**: com login do
  cliente e "minhas reservas", vale o app — e a troca é de hospedagem, não de backend.
  ⚠️ **A paleta é a do PROTÓTIPO**, não a do sistema interno: lá dentro é ferramenta de
  trabalho com dado denso; aqui é a casa se apresentando a quem vai jantar.

- 🔑 **`routers/publico.py` é o ÚNICO router sem permissão da casa**, e por isso é o mais
  estreito. A regra que substitui a permissão é a do CONTEÚDO: só sai dali o que a casa já
  decidiu publicar. ⚠️ **Cada resposta é montada à mão** — a tentação é reaproveitar o
  serializador de dentro, e o preço é vazar o que ninguém pediu: quantas mesas a casa tem,
  quantas reservas existem hoje, o nome de quem atendeu. A suíte cobra a AUSÊNCIA disso.
  ⚠️ **A loja vem no CAMINHO** (`/publico/{id_unidade}/…`), não no `X-Unidade`: o site não tem
  sessão, e um dia haverá duas casas com reserva, cada uma no seu endereço.
  ⚠️ **404, nunca 403**, para casa com reserva desligada: um 403 diria ao público que aquele
  número corresponde a uma casa real.

- 🔑 **Os horários vêm da MESMA `reservas_agenda`** que a agenda do balcão usa. Uma segunda
  regra para o público divergiria, e a divergência apareceria como mesa prometida ao cliente e
  indisponível na casa. ⚠️ Mas a resposta é **podada**: `mesas_livres` por horário é
  informação de operação, e o público não precisa saber se o salão está cheio para escolher as
  19h.

- 🔑 **`wa.me` é só um LINK.** O esboço deixou o WhatsApp para depois pensando no envio
  automático de confirmação — que exige Business API, provedor e modelo aprovado. **Abrir** a
  conversa não exige nada disso, e é o que o dono pediu. ⚠️ O número sai de `empresa.whatsapp`
  e é limpo no servidor (`_so_digitos`): o cadastro aceita "(47) 99910-5033" e o `wa.me` só
  aceita dígitos. ⚠️ **Sem número cadastrado vem NULO**, e o site diz isso — um placeholder
  faria o cliente mandar mensagem para um desconhecido.

- 🟡 **A reserva ainda NÃO grava pelo site.** Ele mostra os horários livres, de verdade, e ao
  escolher um monta a mensagem pronta para o WhatsApp. ⚠️ **A tela não promete o que não faz**:
  dizer "reservado" faria o cliente aparecer na porta sem mesa.
  **O que falta para fechar:** identificar quem reserva (o esboço já decidiu: `fornecedores` é
  a tabela de pessoas, e a chave é o telefone) e **conter abuso** — essa é a diferença entre
  ler e gravar numa rota pública, e sem limite o salão amanhece lotado de reservas que ninguém
  fez. A trava de concorrência já existe desde a 070 (`_travar_o_dia`, por loja e dia).


### O texto do WhatsApp mora na configuração, não no site (migração 081)

🔑 **Pedido do dono:** *"nos botões, colocar centralizado o texto, e somente o texto
necessário, exemplo, Reserve sua Mesa, Catálogo Y, Entre em Contato. Em configurações da
reserva, colocar o texto padrão configurável para o whatsapp."*

⚠️ **As duas frases estavam ESCRITAS DENTRO DO SITE.** Texto de cliente em código é texto que
só muda quando alguém publica: a casa que quisesse trocar o tom da mensagem — ou escrever em
outro idioma, ou citar uma promoção — teria de pedir uma versão nova do site.

- 🔑 **São DOIS textos, não um** (`whatsapp_texto` e `whatsapp_texto_reserva`). Quem toca em
  "Entre em Contato" ainda não escolheu nada; quem vem da reserva já tem dia, hora e quantas
  pessoas. Uma frase só nos dois lugares ou perde o que o cliente já disse, ou manda
  "reservar para {pessoas}" sem pessoas nenhuma.
- 🔑 **Moram em `reserva_config`, não em `empresa`.** O número do WhatsApp é da empresa; a
  MENSAGEM é do site de reservas e muda com o que a casa está oferecendo. Dois donos, duas
  decisões — e foi onde o dono pediu.
- 🔑 **Os marcadores chegam CRUS ao site** (`{casa}`, `{pessoas}`, `{data}`, `{hora}`). Quem
  troca é o JavaScript no clique, porque só ele sabe o que a pessoa escolheu na tela. O
  servidor resolver `{pessoas}` exigiria que ele soubesse de uma escolha que ainda não virou
  requisição.
- ⚠️ **Campo em branco vira NULO, não string vazia**, e o site cai no padrão dele. A string
  vazia passaria pelo `or` do JavaScript igualzinho, mas guardaria no banco uma mensagem que
  existe e não diz nada — e a tela mostraria o campo preenchido com o vazio.
- ⚠️ **Limite de 400 caracteres**, porque o texto vira `wa.me?text=`. Recusar na gravação é
  melhor do que gerar um link que o WhatsApp corta pela metade.
- ⚠️ A migração semeia o padrão **só onde está nulo**: migração roda de novo em toda base que
  ainda não a tem, e a casa que já escreveu o texto dela não pode perdê-lo.

🔑 **Os botões do site são só texto, centralizado.** Saíram o ícone, a seta e o subtítulo —
três elementos que competiam com a única informação que importa. ⚠️ **Dado de contato não é
botão**: endereço, telefone e e-mail viraram linhas `.dado` (rótulo em cima, valor embaixo),
porque centralizar um endereço o faz parecer clicável e ele não é.

### A bateria parou de apagar a reserva da casa — `preservar_reserva`

⚠️ **As três suítes de reserva DESMONTAVAM a casa e não a remontavam.** Elas desligam o
módulo, apagam a semana, apagam salões e mesas — e **precisam** mesmo: metade do que provam é
como o sistema se comporta com o módulo desligado e o salão vazio. O defeito nunca esteve no
que fazem no meio, e sim **no estado que deixavam no fim**: módulo desligado e loja sem nada,
que era "limpo" só enquanto nenhuma loja usava reserva de verdade.

🔑 **Foi assim que a configuração da loja 1 se perdeu, nesta sessão.** Uma rodada morreu no
meio e deixou a reserva desligada; as duas suítes seguintes respeitaram esse estado, e o sinal
que sobrou foi **o site do cliente respondendo 404 para a própria casa**. Quem roda a bateria
não tem como ligar uma coisa à outra.

🔑 **`comum.py` ganhou `preservar_reserva(unidade)`**, no mesmo padrão de
`preservar_credenciais` e `preservar_logo`: fotografa o interruptor e as oito tabelas do
módulo (configuração, semana, permanências, bloqueios, salões, mesas, reservas e o vínculo
reserva↔mesa), e devolve tudo no `atexit`. **Suíte devolve o que encontrou**, não um estado
que ela supõe ser o certo.

- ⚠️ **No `atexit`, não no fim do roteiro.** É a mesma lição da credencial do Omie: bastou a
  suíte estourar no meio para o que ela guardava se perder. Guardar e não repor é pior que não
  guardar — dá sensação de proteção.
- ⚠️ **Sem reserva nenhuma também é um estado a devolver**: a loja que chega sem salão sai sem
  salão, e o interruptor volta a desligado.
- 🔑 **`ON CONFLICT DO NOTHING` sem alvo**, na reposição: cada uma dessas tabelas tem uma chave
  diferente (`id`, `id_unidade`, o par reserva+mesa), e nomear a coluna erraria só numa delas.
- ⚠️ A ordem é a das chaves estrangeiras: apaga-se de baixo para cima, repõe-se de cima para
  baixo — `reserva_mesas` nem tem `id_unidade`, pendura na reserva.

⚠️ **Arquivo descartável não se escreve dentro de `api/`.** O reloader do uvicorn observa a
pasta: gravar um script temporário ali reinicia a API e derruba a conexão da chamada em curso
— foi exatamente o que matou a rodada que começou tudo isto.

🔑 **A bateria do NAVEGADOR tinha as duas mesmas faltas**, e as duas foram corrigidas junto:

1. **O interruptor voltava fixo em `false`**, com o comentário *"uma casa que não faz reserva
   não pode terminar a bateria com o módulo ligado"*. O argumento era verdadeiro quando foi
   escrito e envelheceu: agora a casa faz reserva. ⚠️ **A fase precisa mesmo COMEÇAR
   desligada** — ela afirma que o menu não tem o grupo. O que não pode é o estado de teste
   sobrar no fim. Agora ela fotografa o parâmetro e o devolve.
2. **Os salões da casa ficavam DESLIGADOS e os de teste ficavam no cadastro.** Desligar os
   existentes é o jeito certo de a fase começar limpa (excluir é recusado, e com razão: o
   salão é a resposta para onde aquelas pessoas sentaram) — mas ninguém os religava, e cada
   rodada deixava mais um `Principal 4779526` na tela de quem usa o sistema.

⚠️ **Salão com reserva pendurada NÃO pode ser excluído, e não há rota que apague reserva** —
a exclusão de reserva não existe de propósito: reserva é registro do que aconteceu, e vira
`CANCELADA`/`ENCERRADA`, não some. 🔑 **A consequência é que a bateria não consegue limpar
tudo**: o salão onde ela criou reserva fica apenas *desativado*, com a reserva encerrada
junto. É resíduo conhecido e inofensivo (salão inativo sai da disponibilidade), mas cresce uma
linha por rodada — vale uma limpeza manual de tempos em tempos.


## A reserva marcada pelo site, e quem a marca (migração 082, 21/09/2026)

🔑 **Pedido do dono:** *"para a realização de reserva, precisamos de um cadastro simples do
usuário. Clica em Reserve sua Mesa, abre uma tela com o número do telefone; caso não tenha
cadastrada, realiza o cadastro com Nome, telefone, gênero e cidade."*

🔑 **É o primeiro lugar deste sistema em que a INTERNET grava.** Tudo o que o público
alcançava até aqui só mostrava o que a casa já tinha publicado. Uma rota que cria registro
muda a pergunta: não basta cuidar do que sai, é preciso cuidar de **quanto entra**. Era a
pendência que o esboço carregava desde o começo, e ela é metade deste trabalho.

### Onde mora quem reserva

⚠️ **O esboço dizia `fornecedores`, e isso estava ERRADO.** Aquela decisão é anterior à
integração com o Omie; desde então a casa aprendeu, na conta real, o que custa misturar as
duas coisas — uma conta com 919 cadastros despejou **888 clientes** dentro dos fornecedores, e
a saída foi filtrar por etiqueta no servidor. Mandar para lá quem reserva mesa é refazer à mão
o problema que aquele filtro resolveu, e a tela de Fornecedores passaria a listar quem jantou
no sábado. E `fornecedores` nem tem gênero.

🔑 **`reserva_clientes`, por loja, com o telefone como chave.** ⚠️ **Só dígitos**: o mesmo
número digitado como `(47) 99910-5033` e como `47999105033` tem de achar o MESMO cadastro,
senão a pessoa se recadastra a cada visita e a casa fica com três fichas dela, cada uma com
parte do histórico. ⚠️ **`reservas.id_pessoa` continua existindo e apontando para
`fornecedores`** — é o vínculo do balcão; quem vem do site entra por `id_cliente`. São dois
caminhos para a mesma pergunta, e aproveitar a coluna de um para o outro quebraria a agenda de
quem já usa.

### O nome é o que prova que o telefone é seu

🔑 **Decisão do dono (21/09/2026)**, entre três caminhos: a tela **confirma** o nome, não o
revela. Quem já tem cadastro vê a dica mascarada (`M••••• D•••••`) e digita o próprio nome.

- ⚠️ **Sem isso o site seria uma consulta aberta de telefone→nome.** Não há login nenhum na
  frente: bastaria digitar números em sequência para colher o dono de cada um.
- ⚠️ **A resposta tem a MESMA forma nos dois casos** — um booleano e uma dica que pode ser
  nula. Devolver 404 para telefone desconhecido e 200 para conhecido diria exatamente a mesma
  coisa que mostrar o nome, só que pelo código de status.
- ⚠️ **Confere só o PRIMEIRO nome, sem acento e sem caixa.** Exigir o nome completo idêntico
  ao que a pessoa digitou meses atrás faria a **dona** do cadastro ser recusada no próprio
  telefone — e a saída dela seria se cadastrar de novo, que é o que o índice único impede.
- 🔑 O caminho que de fato prova o telefone é o código por WhatsApp, e ele foi **recusado de
  propósito**: exige Business API, provedor e modelo aprovado — justamente o que o site evitou
  ao usar só o link `wa.me`.

### Conter abuso: dois limites, porque são dois ataques

- **Por telefone** (3 reservas vivas e futuras): protege o **salão**, não o servidor. Sem ele,
  uma pessoa marca todos os horários do sábado "para decidir depois" e a casa recusa clientes
  de verdade a noite inteira. ⚠️ Conta só o que está vivo e à frente — somar cancelada e
  passada faria o cliente fiel ser barrado por ser fiel.
- **Por origem** (20 tentativas por hora): contém o roteiro que inventa um telefone novo a
  cada requisição, para quem o primeiro limite não existe. ⚠️ **A busca de cadastro também
  conta**, embora não grave nada: é por ela que uma varredura passaria.
- ⚠️ **Guarda-se o HASH da origem, não o endereço.** Contar quantas vieram do mesmo lugar não
  exige saber qual lugar é, e IP de visitante é dado pessoal que a casa não tem por que
  acumular. ⚠️ E `X-Forwarded-For` é o que vale atrás do App Platform: sem ele tudo chega com
  o IP do balanceador e o limite por origem vira um limite global que barra a casa inteira.

### A porta que já existia

🔑 **`reserva_config.aceita_online` existia desde a migração 068 e não fazia nada** — o
terreno estava preparado e a porta, fechada. Agora ela abre. ⚠️ **O site pergunta ANTES de
mostrar o botão** (`GET /publico/{loja}/reserva`): sem isso a tela mentiria por um fluxo
inteiro — a pessoa digitaria telefone, nome, gênero e cidade para descobrir no fim que a casa
não marca pelo site, e a saída dela seria fechar a página, não pegar o WhatsApp.
🔑 **A regra que aloca a mesa é a MESMA do balcão** (`reservas_agenda.criar`, com o
`pg_advisory_xact_lock` por loja e dia). Uma segunda regra para o público divergiria, e a
divergência apareceria como mesa prometida ao cliente e indisponível na casa.
⚠️ **O status sai da configuração**: `AUTOMATICA` nasce confirmada, `MANUAL` nasce pendente —
e a tela de "Pronto!" diz coisas diferentes nos dois casos. Dizer "sua mesa está reservada"
numa casa que confirma à mão seria prometer o que ela ainda não decidiu.

### Armadilhas que esta fatia pagou

- ⚠️ **`min_length` do Pydantic dispara ANTES do serviço**, e devolve *"String should have at
  least 8 characters"* — em inglês, falando de caracteres, para quem só errou o telefone. O
  modelo deixou de opinar sobre o tamanho; quem explica é `telefone_valido`, que sabe dizer
  que falta o DDD. A suíte pegou isto na primeira rodada.
- ⚠️ **`display` explícito VENCE o `[hidden]` do navegador.** `.regras` é `display: flex`, e
  toda caixa de aviso com `hidden` continuava ocupando espaço — uma **moldura vazia** sob o
  botão de confirmar, sem texto e sem explicação. O site não tinha `[hidden] { display: none
  !important }`; agora tem. Valia também para `.itens`, `.horarios` e `.dupla`.
- ⚠️ **`.regras` é flex em COLUNA**: texto solto e um `<a>` viram linhas separadas, e a frase
  saía quebrada com o ponto final órfão embaixo do link. Todo conteúdo de aviso vai dentro de
  um `<span>`.
- ⚠️ **A tela de configuração prometia DATA DE NASCIMENTO** em "cadastro completo" — era o
  desenho da 068, e não foi o que o dono pediu. Tela que descreve um campo que o site não
  pergunta ensina a não confiar na tela.

### Duas armadilhas de LIMPEZA, e as duas vieram da mesma correção

🔑 **`preservar_reserva` (feito horas antes) destapou uma dependência de ORDEM que estava
escondida havia semanas.** Enquanto cada suíte terminava apagando tudo, a seguinte sempre
encontrava a loja vazia — e podia supor isso sem dizer. Quando elas passaram a **devolver o
que encontraram**, a suposição virou defeito.

- ⚠️ **Mesa com reserva pendurada NÃO se apaga**: `reserva_mesas_id_mesa_fkey` é
  `ON DELETE RESTRICT`, de propósito — a mesa é a resposta para onde aquelas pessoas sentaram.
  `smoke_reservas_salao` fazia `DELETE FROM mesas` cru no preparo e quebrava com um
  `RestrictViolation` **antes da primeira checagem**. A ordem é vínculo → reserva → mesa →
  salão. A suíte nova nasceu com o mesmo erro e o pagou na primeira rodada.
- ⚠️ **Limpeza no MEIO do roteiro tem de tirar só o que o teste sujou.** A suíte do site usava
  o mesmo `esvaziar_a_loja` entre seções, e ele levava as mesas junto: as três checagens
  seguintes passaram a recusar por *"não há mesa livre"* enquanto mediam outra coisa
  (confirmação manual, teto do site, cadastro simples). Viraram duas funções: uma esvazia a
  loja (preparo e fim), outra tira só quem reservou.
- 🔑 **O teste de que uma suíte é sã é rodá-la DUAS vezes seguidas** e conferir o estado da
  casa entre as rodadas. Suíte que depende do rastro da vizinha passa ou falha pela ordem do
  `glob`, e ninguém relaciona a quebra à mudança que a causou.


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
4. ~~A reserva pelo site do cliente~~ — **feita**, migração 082. O site identifica pelo
   telefone, cadastra quem é novo (nome, gênero, cidade) e **grava a reserva**, pela mesma
   regra do balcão. Os dois pontos que faltavam — identificar quem reserva e conter abuso —
   são a seção "A reserva marcada pelo site" acima.
   ⚠️ **Mas a porta continua FECHADA até a casa abrir**: `aceita_online` nasce desligado, e
   sem salão e mesas cadastrados não há horário a oferecer.

**O que o módulo tem hoje**, medido: 18 rotas em `routers/reservas.py`, os dois
serviços (`reservas.py` e `reservas_agenda.py`), quatro telas
(`agenda`, `salao`, `configuracoes` e o `escolher-horario.tsx` que as duas
primeiras compartilham), **169 checagens** em três suítes de API
(`smoke_reservas_config`, `_disponibilidade`, `_salao`) e **55 checagens de
navegador** na fase 12 da bateria — incluindo o caso de estar desligado.

⚠️ **Ele nasce DESLIGADO em toda loja** (`reservas_ligado = false`), que é o
nascimento certo — ver a primeira seção. Construído e testado não é o mesmo que
ligado: quem for avaliar o módulo numa loja nova precisa acender o interruptor
na tela de Lojas primeiro, senão encontra um menu sem o grupo e conclui que não
existe.
🔑 **Na loja 1 ele está LIGADO desde 21/09/2026**, com a semana cadastrada, e é o
que o site do cliente lê. ⚠️ **Não desligar** — foi pedido explícito do dono
(*"Ajustes, sem desativar o reservas"*), e desligar deixa o site no ar
respondendo 404 para a própria casa.

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

🔑 **A pergunta sobre `PENDENTE` ou `CONFIRMADA` está RESPONDIDA na arquitetura**: quem decide é `reserva_config.confirmacao`, a rota do site o obedece e a tela de "Pronto!" muda de texto conforme. O que resta é a casa escolher.

⚠️ **A pergunta original, para registro**: reserva online entra `PENDENTE` ou
`CONFIRMADA`? O campo `reserva_config.confirmacao` já existe, já é editável na
tela e está em `AUTOMATICA` — a decisão é da casa, e agora ela tem onde ser
tomada.

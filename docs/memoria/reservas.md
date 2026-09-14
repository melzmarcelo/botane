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

## O que vem a seguir

Pela ordem do esboço, e nenhum deles começou:

1. ~~Salões e mesas~~ — **feito** na migração 069, acima.
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

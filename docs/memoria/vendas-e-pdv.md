# Vendas e PDV

> Extraído do CLAUDE.md original (seções "O que já existe" e "Armadilhas já pagas").
> Consultar antes de mexer nesta área do sistema.

## O que já existe

- ⚠️ **A busca da integração vive na tela do ASSUNTO, não só em Integrações.** `/vendas` ganhou
  **Buscar no PDV** (27/08/2026), gêmeo do "Buscar no Omie" de `/compras`, mais o
  **Reconciliar N pendente(s)** quando há item de venda sem produto. Quem abre Vendas para ver as
  vendas não vai lembrar que a busca mora noutra tela — e venda não buscada é receita faltando no
  CMV do período, sem nada denunciando.
  ⚠️ **O `modo` viaja na resposta de `/pdv/sincronizar`**, como já viajava na do Omie: sem ele,
  quem está em simulado importa venda de demonstração e não tem como saber — os números aparecem
  no CMV como se fossem da casa. A tela escreve "(modo simulado — dados de demonstração)".

- **PDV Legal: as vendas entram sozinhas** (`services/pdv/`, `routers/pdv.py`, 26/08/2026).
  🔑 **CREDENCIAL DE INTEGRAÇÃO NÃO DIZ DE QUEM ELA É — conferir o CNPJ ANTES de importar.**
  O primeiro par de chaves (`client_id: 31121`) autenticava, respondia tudo e apontava para
  **outra empresa**: `CAFE DA CLINICA LTDA`, CNPJ 59.938.158/0001-50. Nada na resposta gritava —
  `/pdv/testar` dizia "autenticou", o cardápio veio, as vendas vieram. Foram 46 vendas e 165
  pratos de terceiro dentro da base antes de alguém reparar no nome. O par certo é
  `client_id: 25527`, filial **30638**, `BOTANE DELI E CAFE LTDA`, CNPJ 45.304.800/0001-34,
  Blumenau/SC. Primeira chamada de conta nova é sempre `GET /filial/get`, e o que ela devolver
  se compara com o CNPJ que o cliente informou. ⚠️ O CNPJ vem **sem pontuação** nesta conta e
  **com** pontuação na outra — comparar só os dígitos.
  🔑 **O catálogo de endpoints não é público, mas apareceu em `GET /help`** — a página de ajuda
  do ASP.NET Web API, que **só responde com o Bearer token** (sem token dá 500). São 173 rotas
  com parâmetros e tipos. O que interessa está em **`docs/pdv-legal-api.md`**, e o HTML cru em
  `docs/pdv-legal-help.html`. Antes de pedir documentação a suporte de API fechada, vale tentar
  `/help`, `/swagger*`, `/openapi.json` — **com o token**.
  ⚠️ **A busca é DIA A DIA, e isso decide se o número está certo.** O `cupom/get` devolve no
  máximo 100 registros num intervalo de até 10 dias — *exceto quando data inicial = data final,
  que não tem teto*. A conta do cliente faz **48 cupons num dia comum**: pedir "os últimos 10
  dias" traria 100 e calaria o resto, e ninguém veria falta nenhuma porque 100 é um número
  plausível. O CMV do período sairia com receita a menos.
  ⚠️ **A gravação NÃO acontece no router do PDV.** Ele busca, traduz e chama o mesmo
  `/vendas/importar` da planilha — mesmo de-para, mesmo custo congelado da ficha, mesma baixa de
  estoque. Era o que o mapeamento previa: *"muda a fonte e não o resto"*. Duas gravações seriam
  duas contas de CMV conforme a origem.
  ⚠️ **Cancelamento em DOIS níveis**: `iscancelado`/`isestornado` no cupom e `iscancelado` no
  item. O segundo é o que passa despercebido — um cupom válido com uma linha cancelada dentro
  infla receita e CMV teórico. Cupom que fica sem item nenhum some.
  ⚠️ **`valortotal` do item é o total da LINHA**, não o unitário — e quantidade zero existe em
  cupom cancelado, então a divisão precisa de guarda.
  ⚠️ **`valorcusto` é o custo que o PDV acha, e NÃO vira o nosso.** O CMV teórico é
  `quantidade × custo da ficha daqui`; trocar um pelo outro seria conferir a casa contra o
  cadastro do PDV.
  ⚠️ **`0001-01-01` é o vazio do .NET**, não uma data: vem em `dtestorno` de tudo o que não foi
  estornado, e tratá-lo como data poria venda no ano 1.
  ⚠️ **`expires_in` veio 43.199 s (12 h)**, não as ~6 h da documentação pública. O código usa o
  que o servidor manda, com 5 min de folga.
  ⚠️ **Fixture com id REAL bloqueia a venda de verdade.** A primeira versão da fixture copiou os
  `venda_id` que eu tinha lido: a venda de demonstração entrou primeiro e a real foi descartada
  como "repetida" — sem nada denunciando, porque repetida é o caso normal. Número de
  demonstração tem de ser **impossível de existir** na conta.
  🔑 **O cardápio e o de-para** (`services/pdv/cardapio.py`): a fonte é **`produtos/get`**,
  que devolve uma LISTA. O vínculo mora em `codigos_externos` com `sistema = 'PDV_LEGAL'`, e a
  chave é o `codigo` do PDV, que chega no item da venda como `codproduto`.
  ⚠️ **`getlistaresumida` traz MENOS itens e não avisa** — 570 de 630 na conta real, sessenta
  pratos a menos, calada. E só tem quatro campos, então o rascunho nasceria vazio. Ficou como
  reserva; quando ela é usada, lembrar que a resposta é um **ENVELOPE** `{total_count, total,
  pagina, data}` e não uma lista — tratá-lo como lista daria "4 itens" para as quatro CHAVES.
  🔑 **A impressora do PDV vira SETOR e o grupo vira CATEGORIA** (26/08/2026). `nomeImpressora`
  (VITRINE 183, BAR 132, COZINHA 66) diz onde o item é preparado, que é o que setor significa
  aqui; `nomeGrupo` dá as 30 categorias do cardápio. Vêm junto `codigoNCM` (463 de 464) e
  `unidade`. É o que transforma 464 rascunhos vazios em 464 já classificados — de outro jeito
  alguém digitaria isso 630 vezes. ⚠️ **"Nenhum" não é setor**: é o texto do PDV para "não
  imprime em estação nenhuma". ⚠️ A categoria nasce com `tipo = 'PRODUZIDO'`, não `INSUMO` —
  senão a tela ofereceria "Sanduíches" para classificar um quilo de farinha.
  ⚠️ **O grupo NÃO diz se o item é revenda ou produção própria**: "PRODUTOS MERCEARIA" e
  "CATERING" caem os dois em "Nenhum", e um é comprado pronto e o outro é feito na casa. `tipo`,
  `modo_producao` e `id_local_padrao` ficam de fora do que o cardápio ensina — chutar poria o
  prato na fila errada, a de "falta ficha" em vez da de "falta compra".
  ⚠️ **EAN que já pertence a OUTRO produto é PULADO, não gravado.** `codigo_barras` tem índice
  único (`ux_produto_barras`), e a gravação batia nele — **derrubando a importação INTEIRA**, não
  só aquele item, porque a transação é uma só e nada entrava. O cenário tem três tempos, e nenhum
  deles é estranho: o item entra sem EAN e vira rascunho; depois o catálogo do Omie traz o produto
  de verdade, com o EAN; depois alguém preenche o EAN no PDV. Na reimportação **o item já está
  vinculado — o primeiro passo da cascata responde antes do EAN** —, e a colisão acontece.
  ⚠️ **O conflito é INFORMAÇÃO, não erro**: dois cadastros disputando o mesmo EAN são o mesmo
  produto. Ele vira `ean_de_outro` no resumo e uma frase que manda abrir o produto e usar
  **Vincular** — que sabe mover os códigos, os itens de venda e o custo junto. **Repontar o vínculo ali seria
  errado**: as vendas passadas ficariam presas no rascunho.
  ⚠️ **Corolário que vale para toda a cascata: o passo do EAN só decide na PRIMEIRA vez que o
  item aparece.** Depois de vinculado, o vínculo manda — inclusive quando o EAN chega depois.
  ⚠️ **Reimportar o cardápio COMPLETA o que está em branco, nunca sobrescreve** (`_completar`).
  Sem isso a reimportação não fazia nada (o item já vinculado caía num `continue`) e os
  rascunhos de uma versão anterior ficariam vazios para sempre; sobrescrevendo, ela desfaria a
  correção de quem arrumou a categoria à mão. Mesma regra do importador de fornecedores do Omie.
  ⚠️ **Item fora do cardápio nasce INATIVO, não deixa de nascer.** São 166 dos 630 na conta
  real. Venda antiga aponta para eles: sem cadastro, seria uma venda sem vínculo que ninguém
  consegue resolver depois. Inativo fecha os dois lados — o de-para existe, o histórico fecha, e
  a fila de "falta ficha" continua mostrando só os 464 que ainda se vendem.
  ⚠️ **O EAN é passo EXATO da cascata**, antes do nome (`ux_produto_barras` é único, então não
  há ambiguidade). É ele que impede o mesmo pacote de virar dois cadastros — um pelo Omie, outro
  pelo cardápio.
  🔑 **Mas o PDV desta conta NÃO tem código de barras em lugar nenhum — conferido nos três
  lugares possíveis (27/08/2026), para ninguém repetir a investigação:**
  1. `produtos/get` → `codigoEAN`: existe no modelo, **vazio em 630 de 630**
  2. `produtos/getlistaresumida` → `listaUnidadeCompra[].codEAN` (com `unidade` e
     `fatorconversao` junto — é o único lugar da API com fator de embalagem): a **lista inteira
     vem vazia em 570 de 570**
  3. item do cupom: **não existe** campo de código de barras no modelo
  ⚠️ **O contraste explica o porquê**: NCM está preenchido em 463 de 464, EAN em zero. O NCM é
  obrigatório para emitir o cupom fiscal; o EAN é opcional, e num café ninguém bipa nada — o
  operador toca um botão numa tela agrupada por VITRINE/BAR/COZINHA. O campo nunca teve a quem
  servir.
  ⚠️ **Consequência prática: nesta conta o passo do EAN NÃO dispara**, por mais cheio que esteja
  o nosso lado (1.150 dos 2.190 produtos do Omie têm EAN, e o XML da NF-e traz `cEAN` por item).
  Quem defende contra duplicado aqui é o botão **Vincular**, não o EAN. `por_ean` viaja no
  resumo justamente para esse zero ficar visível em vez de parecer uma trava funcionando.
  ⚠️ Existe saída, e ela é um **write no PDV do cliente** (`produtos/update`/`produtos/save`,
  ainda não usados — até aqui só lemos de lá): mandar o EAN daqui para os itens de mercearia,
  que são os que têm código impresso na embalagem. Decisão de quem opera, não efeito colateral.
  ⚠️ **NUNCA case código de cardápio com código da casa — são espaços de nome diferentes.** A
  primeira versão fazia isso e, numa base com 2.189 insumos do Omie, **os 78 vínculos criados
  assim estavam TODOS errados**: REDBULL virou LIMÃO TAITY, PÃO COM MANTEIGA virou MANJERICÃO,
  BOLO virou ADESIVO VINIL PRETO. Nenhum daria erro em lugar nenhum — só o CMV teórico sairia
  com o custo do insumo errado, para sempre.
  🔑 **A cascata por NOME também saiu** (27/08/2026): nem semelhança, nem nome idêntico. Restam
  duas portas, e nenhuma é palpite — o **código do PDV** e o **EAN**, que é identificador global.
  Não achou? Nasce rascunho, e quem reconhece o produto usa o botão Vincular na tela dele.
  🔑 **O PREÇO DE VENDA vem junto, e de OUTRA rota**: `tabelapreco/get/{filial}`, não o cadastro
  do produto. `valor` preenchido em **629 de 630** na conta real. Durante toda a primeira versão
  os 630 pratos nasceram sem preço nenhum, com o número a uma chamada de distância. Grava em
  `produto_precos` e **só quando muda** — uma linha por importação transformaria "quando o preço
  subiu" em ruído, que é a pergunta que a tabela existe para responder.
  ⚠️ Preço é **por filial**: sem filial, nenhum preço. Melhor prato sem preço do que prato com o
  preço de outra loja.
  ⚠️ **O item do cardápio que não existe aqui nasce PRODUZIDO/RASCUNHO com `producao_propria`**,
  código `PDV-<codigo>`: é isso que o põe na fila de "produzido sem ficha", que é a lista que
  alguém precisa percorrer. Na conta real foram **627 pratos**, 463 deles ativos.
  ⚠️ `cardapio.reconciliar` passa o de-para nos itens de venda pendentes e **recalcula o custo
  AGORA** — item que entrou sem produto entrou sem custo, e ao ganhar produto precisa do custo
  de hoje. Existe separado porque o de-para também se arruma à mão na tela de Vendas.
  ⚠️ Os itens sem de-para caem na fila que já existia (`GET /vendas/sem-vinculo`), mostrada na
  tela de Vendas. **Enquanto ela não for resolvida, o CMV teórico é zero**: 100 itens de 57
  produtos distintos entraram sem vínculo na primeira importação real.
  ⚠️ **Nada volta em claro — nem o usuário.** Os quatro campos saem mascarados; campo em branco
  MANTÉM o guardado, e exigir redigitar a senha para mudar o modo é o caminho mais curto para
  alguém anotar a credencial num bloco de notas.
  ⚠️ **Modo real exige os quatro.** Sem isso a primeira chamada devolve "não autorizado", e quem
  configurou vai procurar a credencial errada.
  ⚠️ O Bearer token vale ~6 h e fica **só na memória**, num cache de CLASSE protegido por lock:
  cada requisição HTTP monta um cliente novo, e sem o cache duas telas abertas pediriam dois
  tokens. Renova com 5 min de folga — usar até o último segundo faz a requisição da virada
  falhar com 401, que parece credencial errada. Um 401 tenta UMA vez com token novo; mais que
  isso é queimar tentativa de login.
  ⚠️ `POST /token` é **formulário**, não JSON — é o `password grant` do OAuth 2. A exceção leva a
  mensagem do servidor, **nunca o que foi enviado**: o corpo tem a senha, e exceção vira log.
  ⚠️ A suíte **nunca põe em modo real**: a credencial de teste é de mentira, e serviço de
  autenticação conta tentativa falha.
  ⚠️ **Mas ela DEVOLVE o modo que encontrou** (`devolver_o_modo_original`, no `atexit`). Antes
  ela terminava sempre em `simulado` — e, agora que a casa tem credencial de verdade, rodar a
  bateria desligaria a integração do cliente sem dizer nada: a busca de vendas pararia de trazer
  cupom e nada explicaria por quê. Mesma lição do Omie. ⚠️ O registro vem **antes** do
  `preservar_credenciais`, porque o `atexit` roda na ordem inversa: a credencial verdadeira volta
  primeiro e o modo real só depois — ao contrário, a integração ficaria "real" apontando por um
  instante para a credencial de mentira.
  ✅ **Exercitado contra a conta REAL em 26/08/2026**: 630 itens de cardápio (627 criados, 164
  inativos), e **1.375 vendas de 1.451 cupons** em 30 dias (28/07 a 26/08), 6.356 itens,
  R$ 187.348,50 de receita, **zero item sem vínculo**. Todos os 6.356 sem custo — porque não há
  ficha técnica nenhuma ainda, que é o item que falta para a variância existir.

- **Cada venda tem endereço** (27/08/2026): `/vendas` é só a LISTA, `/vendas/lancar` lança
  (à mão ou colando a planilha, em abas) e `/vendas/[id]` mostra — cabeçalho, itens com o custo
  congelado de cada um, e os movimentos que a venda causou no estoque. Mesmo corte de Compras, e
  pela mesma razão: os dois formulários ocupavam a primeira dobra e as vendas — o assunto da
  página — começavam abaixo do campo de colar texto. Com 1.375 vendas num mês isso é a tela
  errada. A fila de de-para virou `/vendas/sem-vinculo`, que é uma **fila de trabalho** e não um
  aviso: alguém percorre, cadastra ou vincula, e volta.
  ⚠️ **O detalhe mostra o custo CONGELADO, não o de hoje.** Recalcular na hora de mostrar faria a
  tela discordar do relatório, e a diferença apareceria como variância sem causa.
  ⚠️ **Item sem ficha é CONTADO, e o aviso vem ANTES dos números.** Com um item sem custo a
  margem sai alta demais; quem lê o número primeiro já formou a impressão errada. Os cartões
  dizem "(parcial)" e o aviso nomeia quantos itens estão sem ficha.
  ⚠️ **O estorno NÃO se acha pela origem da venda.** Ele nasce com `origem_tipo = 'ESTORNO'` e
  `origem_id` apontando para o movimento que desfaz, não para a venda — procurar só por
  `origem_tipo = 'VENDA'` mostrava a saída e escondia a devolução, e a tela de uma venda
  cancelada dizia que o produto saiu e nunca voltou.
  ⚠️ **`GET /vendas/{id}` é declarado DEPOIS de `/vendas/sem-vinculo`.** O FastAPI casa rotas na
  ordem de declaração: com o parâmetro na frente, "sem-vinculo" viraria um id e o pedido morreria
  em 422 antes de chegar à fila.
  ⚠️ **A listagem não filtrava por `id_unidade`** — somava as vendas de todas as lojas. Idem
  `/vendas/sem-vinculo` e o cancelamento. Corrigido; a busca por documento vai ao servidor.

- **A busca das vendas no PDV pode rodar sozinha** (`services/pdv/agenda.py`, 27/08/2026):
  `MANUAL` (o padrão), `HORARIA` ou `DIARIA` numa hora escolhida, com janela opcional em dias.
  Venda de sábado que ninguém importa é receita que falta no CMV do fim de semana — e a variância
  sai boa demais, porque o teórico não conta o que foi vendido.
  ⚠️ **Não precisou de migração**: as colunas `agenda_*` de `integracoes` nunca tiveram nada de
  específico do Omie, e a linha do PDV mora na mesma tabela.
  ⚠️ **A regra "chegou a hora?" mora em `services/agenda_integracao.py`**, um lugar só. Ela
  estava dentro do agendador do Omie; copiá-la faria os dois divergirem na primeira correção, e o
  sintoma seria uma integração buscando na hora certa e a outra não, sem nada explicando.
  ⚠️ **Locks DIFERENTES** (`8_120_331` no Omie, `8_120_332` no PDV): com o mesmo número, a busca
  de vendas ficaria esperando a de notas sem ter nada a ver com ela. A suíte cobra isso.
  ⚠️ **Dois laços no `lifespan`, não um.** As integrações falham por motivos diferentes; um laço
  só faria a busca de notas esperar a de vendas, e um erro no meio derrubaria as duas.
  🔑 **A agenda do PDV GRAVA VENDA — e venda tem dono.** Ao contrário da do Omie, que só puxa
  para uma tabela de integração, esta baixa estoque, entra no razão e vai para a auditoria; toda
  escrita dessas carrega `id_usuario`, e o agendador não tem sessão. Quem SALVA a agenda passa a
  assiná-la (`integracoes.agenda_id_usuario`, migração 034); sem assinatura o agendador **recusa
  rodar e diz por quê**, em vez de gravar venda sem dono. Inventar um "usuário do sistema" seria
  pior: uma conta real, com senha e permissões, que ninguém vigia e que aparece como autor de mil
  vendas.
  ⚠️ **Cada DIA da janela é uma requisição** (é o único jeito sem teto de 100 cupons): a horária
  com janela de 30 dias são 720 chamadas por dia para reler o mesmo mês. A tela diz a conta,
  porque "a cada hora" não parece caro até alguém multiplicar.

- 🔑 **Enviar ao PDV — passo 1: o interruptor e a marca** (migração 040, 29/08/2026). A
  integração com o PDV Legal sempre foi de mão única: lemos cardápio, preços e vendas.
  Escrever de volta mexe no sistema que a casa usa para VENDER, no meio do expediente de
  alguém — então o caminho começa por duas coisas que **não enviam nada**.
  **`integracoes.enviar_ao_pdv`** (por loja, nasce FALSO) e **`produtos.integrado_pdv`**.
  ⚠️ **`integrado_pdv` NÃO é `codigo_pdv is not null`, e a diferença É a fila**: marcado sem
  código = deve existir lá e não existe (criar); marcado com código = existe (atualizar se
  mudou); **desmarcado com código = veio de lá e não queremos que o Botané mexa** — estado
  legítimo, e é ele que impede o campo de ser derivado.
  🔑 **Quem ganha o código do PDV é marcado por um GATILHO**, pela mesma razão do 036: o
  `codigo_pdv` é escrito em QUATRO lugares — o formulário, a importação do cardápio e as duas
  rotas do Vincular. Marcar na aplicação exigiria lembrar nos quatro, e o quinto nasceria sem
  a marca: o produto passaria a existir no PDV e **nunca apareceria na fila de envio**.
  ⚠️ **Só na transição de vazio para preenchido.** Um gatilho que forçasse `true` sempre que
  houvesse código destruiria o desmarque no primeiro save.
  ⚠️ A carga marcou **744** produtos (533 ativos) por FATO — código principal ou apelido em
  `codigos_externos` —, nunca por semelhança de nome. E `AND NOT integrado_pdv` deixa o
  script barato ao repetir e **não desfaz o desmarque de ninguém** no próximo deploy.
  ⚠️ **Setor e categoria também têm a marca** (migração 041): o produto no cardápio do PDV
  carrega grupo (`nomeGrupo`) e impressora (`nomeImpressora`), que são a categoria e o setor
  daqui — mandar produto cujo grupo não existe lá tende a falhar, então a fila é por tipo e em
  ordem. A carga marcou **29 categorias** e **3 setores**, e os três são exatamente VITRINE,
  BAR e COZINHA. ⚠️ Por FATO — "classifica ao menos um produto que já existe no PDV" —, nunca
  casando o nome com os grupos do cardápio: é o palpite que este projeto já removeu uma vez,
  quando a semelhança ligou REDBULL a LIMÃO TAITY.
  ⚠️ **Sem gatilho na 041, e a ausência tem razão**: categoria e setor não têm coluna de código
  do PDV — o de-para com `grupoprodutos` e `impressoras` ainda não existe. Quando nascer, esta
  marca vai precisar do mesmo cuidado da 040.
  ⚠️ **A marca só APARECE com o envio ligado** — controle para recurso desligado é ruído. Mas
  desligar **não desmarca ninguém**: o valor gravado fica e volta a aparecer quando religarem.
  🔑 **O portão vem no `/auth/me`, não do `/pdv/config`.** Quem cadastra produto não tem
  `integracao.pdv` para perguntar à configuração — e `/auth/me` é o que toda tela já carrega
  uma vez, então a dica não custa uma requisição por tela. É dica de INTERFACE, não permissão:
  quem barra continua sendo o servidor. ⚠️ Ele resolve a loja ATUAL (`unidade_atual`), porque
  o envio é configurado por loja. ⚠️ E a tela de Integrações chama `recarregar()` depois de
  salvar: sem isso, quem acabou de ligar o envio não veria a marca em lugar nenhum até dar F5
  e concluiria que o interruptor não fez nada.
  ⚠️ **O `SELECT` do "antes" da auditoria precisou do campo novo** nos dois routers — sem ele,
  marcar ou desmarcar entraria na auditoria como se nada tivesse mudado. Mesma lição do
  `um_estoque` que faltava no PUT do produto.

- 🔑 **A fila de envio ao PDV** (migração 042, `services/pdv/envio.py`, tela
  **Cadastros ▸ Exportação para o PDV**, 29/08/2026). Três abas: **pendentes** (com o botão
  de enviar), **integrados** e **erros** — este com a mensagem do PDV **ao lado do corpo
  mandado**, porque "erro 400" sozinho não diz o que ajustar.
  🔑 **A pendência mora numa TABELA INTERMEDIÁRIA (`pdv_pendencias`, migração 043), e quem a
  alimenta é o BANCO.** Alterar um cadastro aqui **não escreve no PDV**: gera pendência, que
  espera alguém abrir a tela, conferir e mandar. Escrever no cardápio de quem está vendendo não
  pode ser efeito colateral de salvar um formulário.
  ⚠️ **Gatilho, não código.** Um `INSERT` de pendência escrito na aplicação teria de existir em
  todo lugar que salva um cadastro — e o próximo lugar, que vai existir, nasceria sem ele. É a
  mesma razão da maiúscula (036) e da marca de integrado (040).
  ⚠️ **Uma pendência ABERTA por registro** (índice único parcial): dez correções seguidas dão
  uma linha, não dez. E **o motivo mais recente manda** — quem alterou e depois desmarcou quer
  sair, não atualizar.
  ⚠️ **São DOIS gatilhos por tabela**, e não um: `AFTER UPDATE OF nome` dispara quando a coluna
  é ESCRITA, mesmo com o mesmo valor — abrir um cadastro e salvar criava pendência do nada. O
  `WHEN (OLD.x IS DISTINCT FROM NEW.x)` filtra, e não convive com `INSERT` no mesmo gatilho
  porque ali não existe `OLD`. (`IS DISTINCT FROM`, não `<>`: com nulo dos dois lados, `<>` é
  nulo e o gatilho não dispararia nem quando deveria.)
  ⚠️ **`ativo` NÃO gera pendência** — é a decisão mais importante da 043, e vem do achado de
  que o campo tem donos diferentes dos dois lados: PASCOA e DIA DOS NAMORADOS entrariam na fila
  a cada virada de estação, e o envio as reativaria no cardápio.
  ⚠️ **A pendência só fecha com envio que deu CERTO** — no erro ela fica aberta, e é isso que
  faz o registro voltar para Pendentes depois de corrigido, sem precisar mexer no cadastro só
  para reenfileirar.
  ⚠️ **Pendência sem o que fazer também fecha**, sem `id_envio`: tirar do PDV uma categoria que
  já está desativada lá pede uma ação que não existe, e a pendência ficaria aberta para sempre.
  Fila com linha que ninguém resolve é fila que ninguém mais lê.
  ⚠️ **Produto: a função do gatilho já o trata, o `CREATE TRIGGER` está escrito e comentado.**
  Ligar hoje faria 533 produtos gerarem pendência que ninguém consegue enviar — não há montador
  de corpo nem rota. Vira uma linha descomentada quando o envio de produto existir.
  ⚠️ **A pendência manda, mas a REALIDADE tem voto**: a fila ainda entra em Pendentes quando o
  que está lá difere do que temos, mesmo sem pendência registrada. É a rede que pega o que
  mudou por fora (uma carga, um `UPDATE` na mão) e o que o gatilho não viu porque nasceu depois.
  ⚠️ **A impressão é do CORPO**, não de uma lista de campos: quando o corpo ganhar um campo
  novo, a fila passa a notar mudanças nele sozinha.
  🔑 **E a fila PERGUNTA AO PDV o que já existe lá — sem isso ela é perigosa.** `pdv_envios` só
  sabe o que este sistema mandou, e numa casa que usa o PDV há anos ele nunca mandou nada: a
  fila concluiria "nunca enviado, logo CRIAR" para os **30 grupos que já estão no cardápio**, e
  apertar Enviar duplicaria o cardápio do cliente. Foi o primeiro estado da fila, e o teste
  mostrou. Agora a ação é **ADOTAR** — 29 categorias e 3 setores, nenhum como criar.
  ⚠️ **Adotar é um update que só toca no de-para**: `{**o_que_esta_lá, codRefExterna: nosso_id}`
  — medido, o nome, a cor e o `ativo` ficam intactos. Mandar os NOSSOS campos numa adoção
  reescreveria a cor que alguém escolheu lá. Adotar é reconhecer, não impor.
  ⚠️ **Falhar a leitura do PDV NÃO vira "então crie tudo"**: sobe 502 e a tela diz que não deu
  para ler o cardápio. O padrão seguro é não agir.
  ⚠️ **O casamento por NOME só decide a ADOÇÃO, e uma vez** — dali em diante manda o
  `codRefExterna` (categoria) ou o `codigo_pdv` guardado (setor). Não é a cascata por
  semelhança que este projeto removeu: é igualdade exata, e a pessoa confirma na tela.
  ⚠️ **No modo simulado o envio RECUSA, não finge.** Um "gravado com sucesso" de mentira
  encheria a aba de integrados com registros que o PDV não tem — e a próxima leitura do
  cardápio não os acharia, num estado que ninguém explica olhando a tela.
  ⚠️ **200 com `erro: true` existe** na Tablet Cloud: tratar o status HTTP como resposta faria
  uma recusa dela virar sucesso. E o `delete` responde uma STRING pura, não um objeto.
  ⚠️ **A conta é conferida por lote** (`conferir_a_conta`), comparando só os DÍGITOS do CNPJ
  contra `filial/get`. Sem CNPJ na tela de Empresa, o envio recusa e explica.
  🔑 **UMA TRANSAÇÃO POR ITEM — o PDV não volta atrás e o banco daqui volta.** O primeiro
  envio real rodou o laço inteiro dentro de um `with get_cursor()`: um item levantou no fim, a
  transação foi desfeita, e os **29 registros das categorias já adotadas no PDV sumiram
  daqui**. Ficou o cardápio alterado do outro lado e nenhum registro deste — o pior dos dois
  mundos, porque a fila não sabia mais o que tinha mandado. Cada item agora grava a sua linha,
  comitada, antes do próximo. ⚠️ Sobra uma janela de UM item (processo morto entre a chamada e
  o commit), e ela é aceitável porque se conserta sozinha — a fila relê o cardápio e vê que
  aquele registro já está adotado. **Foi o que aconteceu**: as 29 voltaram como "integradas"
  sem nenhum registro local, e é a prova de que a fila derivada aguenta perder o histórico.
  🔑 **`ativo` NÃO se sincroniza, e o campo tem DONOS DIFERENTES dos dois lados.** Aqui quer
  dizer "uso este cadastro"; lá quer dizer "aparece no cardápio para vender AGORA". Quatro
  categorias estavam ativas aqui e inativas lá — **PASCOA, DIA DOS NAMORADOS**, FOODBY e
  MERCEARIA PRESENTES: sazonais, ligadas e desligadas lá conforme a época. Mandar o nosso
  `ativo` **reativaria a Páscoa em agosto** no cardápio de quem está vendendo. Quem existe lá
  fica com o `ativo` DE LÁ; só o que nasce daqui nasce visível; e `ativo` ficou fora da
  comparação, senão as quatro apareceriam como pendentes para sempre.
  🔑 **Adotar um SETOR não escreve no PDV — não há onde.** A impressora não tem campo de
  código externo, então reconhecê-la é guardar o `codigo_pdv` deste lado e mais nada. A
  primeira versão mandava um `impressoras/update`: escrita sem propósito no cardápio de quem
  está vendendo, que ainda por cima falhou e derrubou o lote.
  🔑 **Um PUT que NÃO manda o campo MANTÉM o valor** (`coalesce`). `PUT /pdv/config`
  substitui a linha inteira, e com `False` de padrão qualquer chamada que omitisse
  `enviar_ao_pdv` **desligava o envio em silêncio** — um cliente antigo, uma tela que só salva
  a agenda, um script de restauro. Foi o que o restaurador da agenda na suíte de navegador
  fez, e o sintoma é o pior possível: a tela de Exportação some do menu e nada explica.
  ⚠️ **`EXCLUDED` não serve nesse `coalesce`**: ele carrega a linha já montada para inserir,
  onde o nulo virou `false`. Quem responde "veio ou não veio?" é o parâmetro CRU, e por isso
  ele entra duas vezes no comando.
  ⚠️ **Desmarcado que JÁ SAIU daqui não some da tela**: vai para **Integrados** dizendo o que
  virou ("desativada" / "fora da integração"). Antes ele desaparecia das três abas no instante
  do envio — quem tinha acabado de desativar uma categoria não via nem que deu certo, nem que
  ela continua vinculada lá. No SETOR esse é o estado FINAL: a impressora não tem campo
  `ativo`, então não há como desativá-la pela API.
  🔑 **Três checagens caíram por descreverem O ESTADO DO DIA, não uma propriedade** — "BAR está
  pendente como ADOTAR", "o interruptor está desligado", "ele nasce desligado". Todas passaram
  a falhar no instante em que a casa usou o sistema de verdade (adotou os setores, ligou o
  envio), acusando de defeito uma decisão do dono. Viraram afirmações sobre invariantes:
  *nunca propor CRIAR para o que já existe lá*, *a caixinha reflete o servidor*, *o campo é
  booleano*. **Teste que descreve o estado do dia envelhece no primeiro uso real.**
  ⚠️ **A suíte devolve o `enviar_ao_pdv` que ACHOU**, nunca `False` fixo — ela rodou depois de
  o dono ligar o envio e o deixou desligado, e a tela de Exportação sumiu do menu sem nada
  explicar. Mesma lição do `devolver_o_modo_original`. O teste de navegador também **desliga
  para testar o portão** em vez de supor que já estava desligado.
  ⚠️ **O estudo do envio está em [`docs/pdv-envio.md`](docs/pdv-envio.md)**, com o que ainda
  não está decidido: o que a ficha envia (não há rota de receita no PDV, nem campo de custo no
  produto), se o preço entra (e aí quem passa a ser o dono dele), e se setor/impressora vai
  junto. ⚠️ E `docs/pdv-legal-api.md` documenta a conta ERRADA — lendo, isso já custou 46
  vendas de terceiro na base; escrevendo, cadastraria produto do Botané no PDV de outra
  empresa. A guarda de CNPJ por lote é pré-requisito de qualquer rota de escrita.

- ⚠️ **Três checagens caíram no dia 31, e duas pela MESMA causa: corte no topo** (31/08/2026).
  1. O rótulo da apuração exigia as duas pontas ("01/08 a 31/08") porque o mês estaria em
     curso — mas **no último dia do mês o recorte É o mês inteiro**, e o nome curto está certo.
     O teste envelhecia todo fim de mês, longe de qualquer commit.
  2. e 3. `/vendas/sem-vinculo` devolve **os 100 de maior receita**, e o item fantasma de R$ 10
     das suítes saiu do topo assim que a base ganhou venda de verdade. É a lição do ranking de
     margem outra vez: **relatório cortado no topo esconde o registro que se procura**, e "não
     achei" lê como "já foi resolvido". A fila ganhou **busca** por código ou descrição — não
     para o teste: com 100 pendências, achar a que se quer resolver é o que uma pessoa faz.

- 🔑 **O botão "Importar cardápio" virou o momento de ALINHAR com o PDV** (30/08/2026,
  decisão do dono). Ele sobrescreve nome curto, categoria, setor, unidade, NCM, CEST, EAN,
  **situação** e **preço**. Antes só preenchia o que estava em branco, com a regra "reimportar
  não desfaz correção de quem cadastrou aqui" — e o efeito era que nome, situação e preço
  alterados no PDV **nunca** chegavam.
  ⚠️ **"O que o PDV TEM", não "o que o PDV mandou".** Campo vazio de lá NÃO apaga o daqui: o
  cardápio real tem produto com NCM e CEST em branco, e sobrescrever com vazio destruiria dado
  que alguém preencheu. É a condição que o dono pôs na própria frase: *"com todas as
  informações presentes no PDV, caso contrário não"*.
  ⚠️ **`ativo` é a exceção e entra SEMPRE** — booleano nunca é "vazio", e o falso ali É a
  informação. É por aqui que a desativação feita no PDV finalmente volta.
  🔑 **O `nome` respeita o DONO.** Produto que também veio do Omie mantém o `nome` fiscal (o da
  nota do fornecedor, o que se procura ao conferir uma compra); o do PDV vai para o
  `nome_curto`, que é onde ele já morava. Só quem NÃO tem `codigo_omie` recebe o
  `descricaoDetalhada` como nome. Sem isso, uma importação apagaria o nome fiscal de 2.189
  cadastros — sem volta a não ser reimportando o catálogo do Omie inteiro.
  🔑 **E o preço voltou a ser lido, mesmo com o Botané dono dele.** Houve uma versão que parava
  de lê-lo quando `enviar_ao_pdv` estava ligado, para evitar o ping-pong; o remédio era pior
  que a doença, porque o valor alterado lá simplesmente se perdia. **O que evita o ping-pong é
  isto ser MANUAL**: esta função só roda pelo botão, e a busca de vendas — que roda por agenda
  — chama a `reconciliar`, nunca a importação. "Ser dono do preço" quer dizer *o preço daqui é
  o que SAI*; alinhar os dois é um clique de alguém.
  ⚠️ **Venda de produto que só existe no PDV NÃO cria cadastro.** A importação de venda liga
  por id, código e, em último recurso, nome exato de produto ativo; não achando, o item fica
  **sem vínculo** (e o CMV teórico dele é zero) até alguém importar o cardápio. Cadastro não
  nasce de efeito colateral de uma venda.
  ⚠️ **Decidido NÃO construir o "trazer do PDV" por linha** na fila de exportação: com o botão
  alinhando em lote, um segundo caminho para a mesma coisa seria duas regras para o mesmo
  dado. A fila fica só com a VISÃO da divergência.

- 🔑 **O preço divergente era INVISÍVEL dos dois lados** (30/08/2026). Com o Botané dono do
  preço, `cardapio.importar` parou de lê-lo — e a fila comparava só nome, grupo e impressora.
  Preço alterado no PDV não constava em lugar nenhum aqui, e o envio seguinte o sobrescrevia
  calado. Agora `_o_que_existe_la` lê `tabelapreco` e a fila mostra **os dois valores na
  linha**. Não é o preço "voltando": é ele deixando de sumir sem ninguém ver.
  ⚠️ **Comparado em CENTAVOS**: `19,90 != 19,9000000001` poria todo produto como eternamente
  pendente — a doença que a cor e o `ativo` já tiveram nesta mesma comparação.
  ⚠️ **Sem preço de um dos lados não é divergência**: forçar isso jogaria o cadastro inteiro
  na fila no primeiro dia.
  ⚠️ **Exige a FILIAL configurada** (`_filial`, agora num lugar só): preço é POR filial, e
  comparar com a loja errada é pior que não comparar. Sem ela o preço também não é enviado, e
  a busca de vendas nem roda.

- 🔑 **O código do PDV não voltava para o produto** (30/08/2026). O router gravava `codigo_pdv`
  só para SETOR. O primeiro cadastro real foi criado lá (10735980) e ficou com o campo nulo
  aqui; o que segurou a fila foi o `codRefExterna` gravado do outro lado — mas ele é a REDE,
  não o vínculo: `codigo_pdv` é o que a tela mostra, o que o `enviar_preco` usa e o que
  sobrevive a alguém limpar o campo externo lá.

- 🔑 **"Poucos por natureza" era suposição, e a base real desmentiu** (30/08/2026): 184
  locais, 86 categorias, 52 setores. **Tabelas de apoio** e **Exportação para o PDV** ganharam
  rodapé de página.
  ⚠️ **Nas duas o corte é do NAVEGADOR, e não é a mentira que a regra da casa proíbe.** A
  regra existe para lista que cresce sem teto. Aqui as tabelas de apoio vêm inteiras porque a
  própria tela as usa para EDITAR, e a fila do PDV é DERIVADA da comparação com o cardápio
  inteiro — não há `LIMIT` no servidor que a barateie, e o botão Enviar precisa saber de
  TODOS os pendentes, não dos vinte à vista. O total exibido é o total de verdade.
  ⚠️ **A aba entra como filtro**: trocar de aba volta à primeira página, senão quem estava na
  página 5 dos locais cairia numa tela vazia nas unidades de medida.
  ⚠️ **A caixinha do cabeçalho marca a PÁGINA**, não a fila inteira: uma caixinha que
  selecionasse 600 linhas invisíveis é armadilha — e quem quer mandar tudo já tem o botão,
  que sem seleção vale por todos. ⚠️ O rodapé fica FORA do `overflow-x-auto`: dentro dele,
  numa tabela larga, sairia da vista junto com as colunas da direita.

- 🔑 **A HORA do cupom estava sendo jogada fora** (30/08/2026). A coluna `vendas.hora` existe
  desde o começo e `mapeadores.cupom` já lia `dtrecebimento` — o `INSERT` da importação é que
  não incluía o campo. Agora ela atravessa da busca no PDV até a tela, e a lista ordena pelo
  relógio dentro do dia.
  ⚠️ **Data e hora vêm de campos DIFERENTES, de propósito**: a data é `dtmovimento` (a do
  negócio), a hora é `dtrecebimento` (a do caixa). Numa casa que fecha depois da meia-noite os
  dois discordam — e quem decide o dia do CMV é a data.
  ⚠️ **Venda digitada continua sem hora**: `horaBr` devolve vazio, nunca "00:00". Meia-noite é
  um horário, e quem lesse concluiria que a casa vendeu na virada do dia.

- ⚠️ **A limpeza da base derrubou SEIS checagens, e nenhuma por defeito** (30/08/2026) — todas
  supunham a precondição em vez de garanti-la. É a lição do "teste que descreve o estado do
  dia", agora com a lista completa dos disfarces:
  1. `smoke_utensilios` contava com o grupo semeado pela migração 037 — e **migração não
     reexecuta**: quem limpa as tabelas de apoio leva o grupo junto. Cria se faltar.
  2. `smoke_alertas` só AJUSTAVA o usuário de cozinha `if existente:` — depois de uma limpeza
     que leva os usuários de teste, o login voltava 401 e a checagem iterava a MENSAGEM de
     erro como se fosse a lista de alertas, com traceback longe da causa.
     ⚠️ **`smoke_kits` tinha a mesma doença e ficou de fora daquela correção**, e apareceu em
     01/09/2026 com o usuário deixado INATIVO por outra rodada: a falha dizia "usuário de
     cozinha disponível: falso", que não fala do sistema. Ao corrigir uma armadilha destas,
     **procurar todos os chamadores** — não só o que está vermelho naquele dia.
     ⚠️ **E `smoke_pdv_legal` tinha a versão dela pela ponta da CONFIGURAÇÃO** (01/09/2026):
     o restauro do `enviar_ao_pdv` era feito EM LINHA, no meio da suíte, devolvendo o
     interruptor para o que a casa tinha — e o bloco seguinte, escrito depois, precisa dele
     LIGADO. A suíte passava só quando a casa por acaso estava com o envio ligado, e quebrou
     com 409 no dia em que ele estava desligado. Restauro de configuração vai no **`atexit`**,
     como `preservar_credenciais` e `devolver_o_modo_original` — que era o que o comentário ao
     lado dele já mandava fazer.
  3. `smoke_pdv_legal` contava com a CAFETERIA e o BAR deixados pela importação do cardápio.
     ⚠️ E `_garantir` precisou comparar **sem caixa**: a unicidade do nome ignora maiúsculas,
     então o POST devolve 409 para "BAR" quando existe "Bar" — e a busca exata não achava o
     registro que o próprio servidor acabou de citar.
  4. 🔑 **A pior delas passava por SORTE há muito tempo:** *"o de nome idêntico acha dono"*
     exigia que a importação vinculasse um prato criado com o nome exato do cardápio — mas a
     **cascata por nome foi REMOVIDA** deste projeto. Ela passava porque o `PDV-10689993` de
     uma rodada anterior entrava como `ja_vinculados`, por CÓDIGO. A base virgem expôs. Agora
     afirma a regra: nome idêntico NÃO liga, e nenhum item fica órfão.
  5. `smoke_exportacoes` exigia `> 10` linhas na prévia do CMV — sem venda, a margem por prato
     vem vazia e o arquivo tem só as 10 da apuração. Passou a afirmar a SOMA: apuração + anexo.
  6. A checagem do preço do cardápio virou pergunta ao `/pdv/config`: com o envio ligado o
     Botané é dono do preço e o cardápio deixa de trazê-lo.

- 🔑 **O painel abre no dia da ÚLTIMA venda** (`GET /inicio/dia`, cartão "Vendas do dia",
  03/09/2026, pedido do dono). A tela inicial respondia pelo período inteiro e não dizia como
  foi o último dia — que é a primeira coisa que se olha de manhã. Três números: **quantidade de
  vendas, valor total e ticket médio**, com setas na data para andar para trás e para a frente.
  🔑 **Abre no dia da última venda, NÃO em hoje.** De manhã, ou num dia em que a busca no PDV
  ainda não rodou, "hoje" é um dia sem venda nenhuma — e um cartão zerado se lê como *"a casa
  não vendeu"*, que é diferente de *"ainda não importou"*. Abrindo no último dia com venda, o
  número na tela é sempre um número de verdade. É a regra "número verdadeiro ou nenhum" que o
  painel já seguia, aplicada à escolha do DIA.
  🔑 **As setas andam entre dias que TÊM venda, não entre dias do calendário.** Numa casa que
  fecha na segunda, avançar um dia cairia num zero — o mesmo engano pela outra porta. Quem diz
  para onde dá para ir é o SERVIDOR: `anterior` e `proximo` vêm nulos quando não há para onde, e
  é isso que desliga a seta. ⚠️ E a seta desligada **parece** desligada (`.link-acao:disabled`,
  que já existia): seta viva que não faz nada ao ser clicada se lê como tela quebrada.
  ⚠️ **O dia vem no MESMO pacote do painel**, não numa segunda chamada — painel que faz seis
  requisições pisca seis vezes. Só a NAVEGAÇÃO custa uma ida ao servidor, e aí é alguém pedindo.
  ⚠️ **E só o dia navega**: trocar de dia não recarrega a apuração do período, os alertas nem o
  peso por setor. Seria refazer a tela toda para mudar três números.
  ⚠️ **A receita sai de `venda_itens`, como a do CMV** — não do `vendas.valor_total` do
  cabeçalho. Hoje os dois concordam por construção (o cabeçalho é a soma dos itens), mas ler de
  fontes diferentes é como um painel passa a discordar de si mesmo: a receita do período está
  logo acima, na mesma tela.
  ⚠️ **Ticket médio é receita ÷ número de VENDAS**, não ÷ itens — é o quanto cada cliente
  gastou. E vem **nulo** num dia sem venda: um ticket de zero real é uma afirmação, não a
  ausência de uma.
  ⚠️ **Venda cancelada não conta**, aqui como em todo lugar. A suíte cobra os dois lados: a
  contagem e o valor.
  ⚠️ **Dinheiro obedece à permissão**: sem `cmv.painel` o `dia` vem nulo e a rota recusa. Um
  cartão só com a contagem seria uma quarta coisa a explicar em troca de nada.
  ⚠️ E quando o dia mostrado é o mais recente **e não é hoje**, o cartão diz isso ("é o dia mais
  recente com venda importada"): é a resposta para *"por que não estou vendo o movimento de
  hoje?"* antes de a pergunta ser feita.

- 🔑 **Busca MANUAL não consome a cota do dia** (mesmo pedido). `agenda_rodou_em` sempre foi
  movido só pelo agendador — mas o **cardápio do PDV** tinha um segundo relógio, `cardapio_em`,
  e ele era marcado dentro de `cardapio.sincronizar_cadastros`, que roda pelos DOIS caminhos.
  Um clique em "Buscar no PDV" às 10h fazia a busca agendada da madrugada **pular os cadastros**,
  e o prato criado no PDV depois disso esperava mais um dia para nascer aqui, sem nada dizendo
  por quê. O relógio saiu de lá e virou `cardapio.marcar_cardapio`, chamado **só pelo agendador**.
  ⚠️ **O "uma vez por dia" é do AGENDAMENTO, não de todo mundo**: quem clica no botão está
  pedindo agora, não dispensando a passada da madrugada. São dois pedidos diferentes, feitos por
  razões diferentes.
  ⚠️ O agendador marca o relógio **mesmo quando o cardápio dá erro** — mesma razão do
  `agenda_rodou_em`: reler 630 itens a cada minuto em cima de uma conta bloqueada só prolonga o
  bloqueio. O erro viaja em `cadastros.erro`.

- 🔑 **Dormir um tempo fixo e afirmar é SUPOR a precondição.** Três checagens do navegador
  quebraram assim em 29/08/2026, e nenhuma por defeito da tela: `pdv-legal.tsx` devolve
  `<Carregando/>` enquanto `/pdv/config` não responde, então `#agenda-pdv` não existe no DOM —
  e o teste acusava a tela de não ter a agenda. O bloco do Omie é outro componente e responde
  antes, o que fazia a falha parecer específica do PDV. A tela do produto tinha a mesma doença.
  A correção é `waitForSelector`/`waitForFunction` pelo que se vai medir.
  ⚠️ **Mas esperar pelo seletor ERRADO não espera nada.** `span.rotulo` existe igual no
  formulário de cadastro, que é a tela de onde se acabou de sair: a espera casava com a página
  velha e devolvia na hora, e a checagem seguinte media a tela ainda em branco. **Espere por
  algo que só existe na tela de DESTINO** — ali, o rótulo "NCM".

- ⚠️ **"O primeiro elemento que casa" deixa de identificar quando surge o segundo.** O teste da
  agenda do Omie pegava "o primeiro `select` que tem HORARIA"; assim que o PDV ganhou o mesmo
  bloco, passou a depender da ordem do DOM. Cada seção tem `id` (`#agenda-omie`, `#agenda-pdv`) e
  o teste aponta para o dela.

- ⚠️ **E o contrário também: base ZERADA descobre suíte que vivia de sobra.** Depois de
  `limpar_dados.py`, a fase 8g de `smoke_pdv_legal` caiu — ela conferia que a semelhança vira
  dica na observação do rascunho, mas o rascunho de nome IDÊNTICO criado numa fase anterior fazia
  a cascata parar no passo do nome e nunca chegar na semelhança. Só passava porque uma rodada
  antiga havia deixado a observação lá. Precondição garantida (o rascunho é renomeado e
  desativado antes) em vez de suposta. ⚠️ `web/scripts/base-vazia.mjs` passa pelas 26 telas com a
  base zerada — é o estado que ninguém testa e que o cliente vê no primeiro dia.

## Armadilhas já pagas

- ⚠️ **`toISOString()` é UTC, e depois das 21h em Brasília ele já diz amanhã.** A tela de
  Vendas propunha a data de amanhã para a importação do dia: um restaurante que fecha às 23h
  lançaria a venda inteira no dia seguinte, o CMV do mês fecharia errado e nada na tela
  denunciaria. Toda data que vira texto `aaaa-mm-dd` no front passa por **`lib/datas.ts`**
  (`hoje`, `diaLocal`, `somarDias`, `somarMeses`, `primeiroDiaDoMes`) — `sv-SE` é o formato
  ISO no fuso de quem está olhando. É a mesma armadilha que o banco resolve com a sessão em
  `America/Sao_Paulo`.

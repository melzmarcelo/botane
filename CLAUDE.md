# Botane — guia para Claude Code

Sistema de gestão para café/restaurante, sob encomenda, construído **por partes**.
Projeto **independente** do Gestor Civil (o `D:\dsv\CLAUDE.md` do diretório acima é
de outro sistema — não vale aqui, exceto pelos padrões de código citados abaixo).

**Antes de qualquer coisa, leia [`MAPEAMENTO.md`](MAPEAMENTO.md)** — é o documento-fonte:
escopo, modelo de dados, regras de negócio, permissões, integração Omie e ordem de
construção. Rascunho do DDL em `docs/schema_draft.sql`.
Apresentação para o cliente: `apresentacao/index.html` (arquivo local, autocontido;
só as fontes vêm da internet). Publicada também como artifact — republicar sempre com a
mesma URL para não criar link novo.

⚠️ **Tudo deste projeto mora no D:.** Não usar o scratchpad da sessão (`%TEMP%`, que fica no C:)
para arquivo nenhum — gravar direto aqui.

## Branches — `main` é local, `producao` é o que vai ao ar

```
desenvolvimento  →  main       roda local (Postgres + FastAPI 9200 + Next 3100)
                       ↓  merge quando validado
                    producao   o que fica online
```

⚠️ **Ao contrário dos outros projetos da casa, `main` NÃO é produção.** Aqui ela é a base de
trabalho local: é onde se experimenta, se limpa a base, se roda a bateria inteira e se quebra
coisa à vontade. Só o que passou por isso é promovido.

### Regras
- Todo desenvolvimento vai para `main` primeiro — nunca commit direto em `producao`
- `producao` recebe **merge de `main`**, nunca commits próprios: `git checkout producao &&
  git merge main`
- Promover só depois de a bateria passar inteira (API + navegador) na base local
- ⚠️ **Migração nova é o ponto de não retorno.** Ela roda no start da API e reescreve dado;
  antes de promover, conferir que é idempotente e que já rodou aqui sobre base COM dado, não
  só sobre base vazia
- ⚠️ **Configuração não se promove por merge.** `api/.env` está fora do versionamento de
  propósito: `DEBUG`, `CORS_ORIGINS`, `WEB_URL`, `DB_*` e a senha do admin são de cada
  ambiente. O que estiver online tem o `.env` dele

Ainda **não há remoto nem servidor**: os dois branches são locais. Quando houver, `producao`
é quem aponta para lá.

### Preparado para o dia do deploy
- **`.do/app.yaml`** — o app inteiro no DigitalOcean App Platform: web em `/`, API em `/api` e
  Postgres gerenciado. ⚠️ **Mesmo domínio de propósito**: com isso o navegador nunca faz
  requisição entre origens e o CORS deixa de existir como problema. O App Platform remove o
  prefixo antes de repassar, então nada muda no FastAPI — e o service worker já previa isso.
- **`api/verificar_deploy.py`** — doze checagens **só de leitura** contra o que está no ar.
  ⚠️ A suíte de fumaça NÃO serve para produção: ela cria produto, lança nota e grava
  credencial de teste na mesma linha da real.
- ⚠️ **A versão do Python vai em `api/.python-version`, NUNCA em `runtime.txt`** — o buildpack
  da DO recusa o segundo, que foi descontinuado, e o primeiro deploy morre no build. Só o
  número maior (`3.13`), sem prefixo e sem a versão de correção: prender a correção impede o
  app de receber atualização de segurança. O Python online é o mesmo de casa; o Node não
  (local 24, `.nvmrc` 22, que é LTS e o que o `engines` já pedia).
- ⚠️ **Filesystem efêmero no App Platform**: `api/uploads/` (logo) e `api/arquivos/emails/`
  somem a cada deploy. Nada insubstituível, mas a saída definitiva é o Spaces —
  `api/arquivos.py` já foi escrito para essa troca.
- **[`docs/deploy.md`](docs/deploy.md)** — o roteiro: o que decidir, banco, API, web,
  verificação em oito passos, backup e como promover uma versão
- **`api/.env.producao.exemplo`** e **`web/.env.producao.exemplo`** — as variáveis, com o
  porquê de cada uma. `api/.env` continua fora do versionamento
- ⚠️ **`requirements.txt` tem as versões PRESAS** no que passou nos testes. Estava com 10 de
  11 sem `==`: o servidor instalaria o que estivesse mais novo no dia, e a quebra apareceria
  no start, em produção, falando de uma biblioteca que ninguém tocou
- ⚠️ Os três erros que o roteiro antecipa, porque são os que sempre acontecem: **CORS** sem o
  domínio exato (o navegador barra o login e a tela fica muda), **`NEXT_PUBLIC_API` lido na
  compilação** (mudar depois do build não muda nada) e **`WEB_URL` apontando para localhost**
  (o link do e-mail de recuperação chega e não abre)

## Estado

- Mapeamento e **etapas 1 a 6 — a primeira parte inteira** (fundação, cadastros, fichas,
  estoque, Omie e CMV) concluídas em 18 e 19/08/2026.
- Roda local: `.\iniciar_local.ps1`. As credenciais do admin inicial estão em
  `api/.env.example` — e só valem em desenvolvimento.
- ⚠️ **Com `DEBUG=false`, a API RECUSA SUBIR se `ADMIN_EMAIL`/`ADMIN_SENHA` forem as de
  desenvolvimento** (ou a senha for menor que `SENHA_MINIMA`). O primeiro deploy real
  subiu com `admin@botane.com.br` e a senha padrão, porque as variáveis não tinham sido
  definidas no painel — e nada avisou: a linha "administrador criado" saiu igual à de
  sempre. Parar o start é o único aviso que ninguém deixa passar. A trava vale só na
  CRIAÇÃO: sistema que já tem gente dentro não é afetado.
- **O Omie já foi exercitado contra a conta REAL do cliente** (24/08/2026): 37 notas do
  período, 2.183 produtos e 793 fornecedores importados de verdade. Sem credencial, o
  importador cai no **modo simulado** sobre fixtures, e as duas rotas passam pelo mesmo código.
  ⚠️ **A credencial que estava configurada se perdeu** quando a suíte `smoke_omie` estourou no
  meio, depois de gravar a chave de teste na mesma linha (ver `preservar_credenciais`, já
  corrigido) — para voltar ao modo real é preciso redigitar `app_key`/`app_secret` em
  Integrações.

### O que já existe
- `api/` FastAPI: `database.py` (pool, sessão em America/Sao_Paulo), `db_updater.py`
  (migrações por checksum — **todo script tem de ser idempotente**), `seguranca.py`
  (bcrypt, JWT, refresh rotativo com hash no banco, `requer_permissao`),
  `auditoria.py` (grava no MESMO cursor da operação e filtra senha/credencial).
- `api/db_scripts/`: 001 acesso+empresa, 002 permissões e papéis de fábrica, 003 empresa inicial.
- `web/` Next.js 16 (App Router): `lib/api.ts` (cliente único, renova o token sozinho),
  `lib/sessao.tsx` (contexto + `pode()`), telas de início, empresa, lojas, usuários, papéis,
  auditoria e troca de senha.
- `api/db_scripts/`: 004 cadastros (setores, locais, categorias, UM, fornecedores, produtos,
  preços e produto×fornecedor), 005 semente dos cadastros.
- Routers da etapa 2: `cadastros.py` (as quatro tabelas de apoio no mesmo arquivo — são
  pequenas e sempre lidas juntas), `fornecedores.py`, `produtos.py`.
- **Loja atual em `seguranca.unidade_atual(cur, ctx)`** (19/08/2026): estava copiado em SETE
  routers, e a cópia ficou para trás quando o seletor passou a existir. A escolha vem do
  cabeçalho **`X-Unidade`** (não do corpo: vale para GET e nenhuma tela precisa repassá-la),
  validada com `ctx.ve_unidade` — mandar o cabeçalho não dá acesso a loja nenhuma.
- **Paginação é o PADRÃO de todo grid** (25/08/2026): `components/paginacao.tsx` —
  `usePaginacao(nome, { padrao, filtros })` + `<Paginacao p={pag} rotulo="…" />`. O rodapé diz
  "1–20 de 2.183", deixa escolher **20, 50 ou 100** e **lembra a escolha** (localStorage, por
  lista: conferir estoque numa tela grande pede 100, o celular pede 20).
  ⚠️ **O corte é do SERVIDOR** — trazer tudo e fatiar no navegador só troca a mentira de lugar.
  ⚠️ **Trocar o filtro volta para a primeira página** (é o que `filtros:` faz): quem está na
  página 7 e digita uma busca cairia numa tela vazia sem nada explicando.
  ⚠️ A preferência é lida num **efeito**, não no estado inicial: o servidor renderiza a tela
  antes de existir `localStorage`, e valores diferentes dos dois lados quebram a hidratação.
  Aplicado em produtos, fornecedores, notas, saldos, razão, fichas, vendas, inventários,
  produções, auditoria, usuários e movimentação do CMV. **Fora, de propósito**: tabelas de
  apoio, lojas, papéis e tudo que é detalhe de UM registro (itens da nota, insumos da ficha) —
  são poucos por natureza, e rodapé de página em lista de três linhas é ruído.
  ⚠️ **A movimentação do CMV é a única que fatia no navegador**, porque o rodapé precisa somar
  TODAS as linhas para a identidade fechar — o relatório vem inteiro de propósito.
- ⚠️ **O total sai em consulta SEPARADA e só na primeira página** (`paginacao.pagina`). Medido
  com 400.000 movimentos no razão: página de 100 sem total **4 ms**, com `count(*) OVER ()`
  **388 ms** — a janela obriga o banco a materializar todas as linhas do filtro para depois
  cortar em 100. Virar a página não muda o total, então a conta roda no `offset = 0` e mais
  nada: 148 ms na primeira, **2 ms** nas seguintes. Quando o cabeçalho não vem, `api.listar`
  devolve `total: null` e `usePaginacao.setTotal` **guarda o que já tinha** — tratar nulo como
  zero apagaria o rodapé na página 2. Quem monta a consulta passa o SQL **sem LIMIT**: o total
  usa o mesmo texto e os mesmos parâmetros, e uma cópia do filtro escrita à mão divergiria no
  primeiro `WHERE` novo. As listas limitadas por natureza (fichas, inventários, usuários)
  continuam com `com_total` e `count(*) OVER ()`.
- **Paginação**: as listas grandes devolvem o total em **`X-Total`** (via `count(*) OVER ()`,
  na mesma varredura) e o front usa `api.listar()`. ⚠️ O header precisa estar em
  `expose_headers` do CORS, senão o navegador não o entrega à tela.
- 🔑 **"Quais são as provisórias?" não tinha resposta** (01/09/2026, pedido do dono). A saída
  que não acha saldo sai por um custo **estimado** e a linha nasce marcada no razão — mas com
  centenas de movimentos a etiqueta só ajuda quem já está olhando para a linha certa. Cada uma
  delas é **uma entrada que ninguém lançou**, e deixa o CMV torto até ser lançada.
  `?apenas_provisorios=true` no razão, caixinha **"só custo provisório"** na tela.
  ⚠️ **Caixinha, não mais um valor no seletor de Movimento**: não é um TIPO de movimento — é
  uma marca que qualquer saída pode ter. Dentro daquela lista pareceria excludente das outras.
  ⚠️ **Lista vazia é a BOA notícia**, e a tela diz isso ("não há entrada faltando"): o
  "nenhum movimento com esses filtros" de sempre faria parecer que o filtro não funcionou.
  ⚠️ **E a lista precisa dizer o que FAZER** — ela é de saídas esperando uma entrada, não de
  erros a corrigir no razão, que é append-only.
  ⚠️ **O ARQUIVO aceita o mesmo filtro**, e ganhou a coluna "Custo provisório" — filtro que
  existe num lado só recria a divergência que o razão exportado existe para não ter. A coluna
  vem **vazia** quando o custo é firme, e não "não": ela é um alerta, e 600 "não" ao lado de 3
  "sim" escondem os três.
  🔑 **Nasceu daí o primeiro filtro de SIM OU NÃO da janela de exportação** (`tipo: "sim_nao"`).
  ⚠️ E `False` sai do que vai para a auditoria **por identidade** (`v is not False`): registrar
  `provisorio: false` em toda exportação é ruído, mas `v not in (None, [], "", False)` levaria
  junto o `dias=0`, que é filtro legítimo — em Python `0 == False`.
- 🔑 **E o razão NÃO filtrava por loja** (01/09/2026). `GET /estoque/movimentos` não tinha
  `id_unidade` no `WHERE` — enquanto o CSV do razão sempre teve. Com duas lojas a tela
  misturava os movimentos das duas e o arquivo baixado trazia só os desta: a divergência exata
  que aquele endpoint documenta querer evitar. Medido na base local: 22 linhas de outras lojas
  numa página de 500. É a mesma dívida que vendas, inventários e locais já pagaram — **toda
  lista de coisa que tem `id_unidade` nasce com ela**, e ela só aparece no dia em que a segunda
  loja existe.
- **O razão filtra por período, produto, tipo e local** (20/08/2026): `GET /estoque/movimentos`
  ganhou `inicio`/`fim`/`busca` (os mesmos nomes do CSV) e a tela ganhou a barra de filtro com
  paginação de 100 por `X-Total`. ⚠️ `fim` é dia **cheio** (`< fim + 1`): `<= fim` cortaria o que
  foi lançado às 14h do próprio dia, porque `data_movimento` guarda data e hora. O CSV aceita os
  mesmos filtros — filtrar na tela e baixar outra coisa faria quem conferisse achar que um dos
  dois mente. Os rótulos dos tipos saem de `GET /estoque/tipos-movimento`, não de uma lista
  copiada no front.
- 🔑 **Baixar deixou de ser um clique cego** (`services/exportacao_catalogo.py`,
  `components/exportar.tsx`, 29/08/2026). O botão de `/produtos` despejava os **3.226** do
  cadastro, sempre; o de saldos trazia os 99 locais; o razão MANDAVA `id_produto` e o servidor
  **ignorava** — filtrar um produto na tela e baixar dava a planilha inteira, calada, que é
  exatamente o defeito que aquele endpoint dizia existir para evitar. Agora o botão abre uma
  janela: os filtros pertinentes ÀQUELE processo, todos de escolha múltipla, mais a escolha
  entre **planilha e PDF**.
  🔑 **O PDF não foi nove trabalhos, foi um** — e a razão é que os relatórios já se declaravam
  na mesma forma. `exportacao.pdf_de` tem a MESMA assinatura de `csv_de`
  (`linhas, colunas, titulo, resumo`), então relatório novo nasce com os dois formatos sem que
  ninguém escreva nada a mais, e é impossível a planilha e o PDF discordarem sobre o conteúdo.
  ⚠️ **O motor é `reportlab`** (preso em `requirements.txt`), e a escolha é restrição, não
  gosto: `weasyprint` exige GTK/cairo e **quebraria o build no App Platform**. Gerar no
  navegador criaria a segunda implementação do mesmo relatório.
  ⚠️ **A extensão do caminho É o formato, e por isso a URL não mente**: `/exportar/saldos.csv`
  e `/exportar/saldos.pdf`. Quando o caminho traz extensão é ela que manda — um `?formato=pdf`
  pendurado num `.csv` faria o arquivo baixado discordar do endereço que o gerou.
  ⚠️ **O catálogo dos filtros vem do SERVIDOR** (`GET /exportar/catalogo`), com as opções já
  resolvidas. É a lição das três listas de `TIPOS`: escrita no front, a lista divergiria
  **calada** — a tela ofereceria um filtro que o servidor ignora e o arquivo sairia com mais
  linhas do que se pediu. As opções vêm resolvidas para a janela não precisar de quatro
  requisições a mais (e piscar quatro vezes) antes de deixar escolher.
  ⚠️ **O vocabulário é o de `inventario_selecao`**: filtro opcional, combinando com E, vazio
  querendo dizer "todos", e no SQL `(%(x)s IS NULL OR coluna = ANY(%(x)s))`.
  ⚠️ **Produto NÃO vira lista de caixinhas** — são milhares, e seria a mesma mentira do
  `<select>` paginado. O catálogo marca o filtro com `tipo: "produtos"` e a tela resolve com a
  `BuscaCadastro` da casa, guardando o escolhido como etiqueta.
  ⚠️ **A prévia diz quantas linhas viriam ANTES do botão** (`/exportar/{rel}/previa`), como a
  do inventário — e conta o ANEXO junto, senão ela diria "10" e o contador abriria 443 linhas.
  ⚠️ **Dois relatórios são COMPOSTOS de propósito**: o do contador leva a apuração **e** a
  margem por prato; o da reunião com o fornecedor leva a evolução de preço **e** o peso por
  setor. `csv_de`/`pdf_de` recebem `anexos=` por causa deles. Partir em dois arquivos faria
  quem recebe juntar de novo — e duas suítes cobram os dois quadros no mesmo arquivo.
  ⚠️ O BOM do anexo **sai**: ele só vale no começo do arquivo, e um solto no meio vira
  caractere invisível numa célula do Excel (o `precos.csv` tinha esse desde sempre).
  ⚠️ **`MAXIMO_PDF = 5000`**: o razão de uma base real tem centenas de milhares de movimentos,
  e o PDF disso é um arquivo de milhares de páginas que ninguém abre e que estoura o tempo da
  requisição. Acima do teto a resposta é uma FRASE mandando usar a planilha, que não tem teto —
  e a janela desabilita o botão antes do clique, em vez de deixar a surpresa para depois.
  ⚠️ **`int` é contagem e não leva casa decimal no PDF**: o resumo dizia "Linhas 2,00". O tipo
  já separa os dois na origem — contagem chega de um `len()`, dinheiro chega como `Decimal`.
  ⚠️ E o número sai formatado **diferente** do CSV de propósito: a planilha precisa de vírgula
  decimal SEM separador de milhar (com ponto de milhar o Excel lê como texto e não soma); o PDF
  é para o olho, e "1.284.532,10" se lê enquanto "1284532,1" não.
  ⚠️ **A apuração do CMV passou a sair em centavos**, e é arredondamento de APRESENTAÇÃO: ela
  encadeia custo unitário de 6 casas, e o arquivo do contador dizia "56.138,035", que não é um
  valor em reais. Quem arredonda é a linha do relatório, nunca o motor.
  ⚠️ **Nem todo relatório filtra pelo banco**: a movimentação e os vencimentos são motores cuja
  consulta prova uma identidade (`inicial + entradas − saídas = final`) ou alimenta o alerta da
  tela inicial. Neles o corte é feito sobre as linhas devolvidas — daí o de-para de id para
  nome. Remodelar o SQL deles arriscaria a propriedade que o relatório existe para provar.
  ⚠️ **Toda exportação vai para a auditoria com o FILTRO que a gerou**: sem ele o registro diria
  "fulano exportou o estoque", e a pergunta que se faz depois é sempre *o quê, exatamente*.
  ⚠️ **A folha de contagem existia desde a etapa 4 sem botão em tela nenhuma** — só se chegava a
  ela pela URL, e ela é o caminho previsto para quem conta no papel. Ganhou o botão em
  `/inventario/[id]`, no modo "avulso" da janela (um registro só: pergunta o formato e mais
  nada). Em contagem CEGA aberta o servidor continua tirando as colunas do sistema.
- 🔑 **A ficha técnica ganhou FOTO do prato pronto** (01/09/2026, pedido do dono). A coluna
  `fichas_tecnicas.foto_url` **existe desde a etapa 3 e nunca tinha sido usada** — não houve
  migração. A ficha é seguida por quem está de pé na cozinha, e *"está pronto?"* é uma pergunta
  **visual**: nenhuma descrição de montagem responde o que a imagem responde. Ela aparece no
  cartão do prato, vira miniatura na lista de fichas e **sai no PDF**, que é o papel que fica
  pendurado.
  🔑 **A foto é a EXCEÇÃO da regra "ficha homologada não se edita".** A ficha publicada é
  congelada porque mexer nela mudaria custo histórico; a foto não entra em conta nenhuma. E o
  prato só pode ser fotografado DEPOIS de pronto, que é depois de homologado — a trava
  obrigaria a abrir uma versão que não difere em nada, e cada versão carrega histórico de
  custo. Mesmo raciocínio do nome do inventário, editável com a contagem fechada: rótulo não
  mexe em item nem em razão.
  🔑 **A nova versão leva a foto, e `arquivos.copiar` duplica o ARQUIVO — não a URL.** Copiar só
  a URL deixaria as duas fichas apontando para o mesmo arquivo, cujo `dono` é a versão VELHA — e
  `salvar_imagem` apaga as versões anteriores do mesmo dono. Trocar a foto da versão 1 apagaria
  a da versão 2, que ninguém tocou, e a imagem sumiria da tela sem nada explicando. A suíte
  cobra exatamente esse caminho.
  ⚠️ **No PDF ela sai AO LADO do resumo, não abaixo.** A caixa do resumo tem 106 mm e a página
  em retrato tem 186: sobrava metade da largura vazia, e a foto embaixo empurraria os
  ingredientes para a segunda página — que é justamente a que ninguém pendura.
  ⚠️ **`larga_max` porque foto de celular vem DEITADA**: a 34 mm de altura ela passa dos 78 mm
  da coluna e estoura a tabela. O `_figura` saiu de dentro do código da logo, que já fazia
  altura fixa com largura proporcional e já tolerava imagem ilegível — os dois usam o mesmo
  helper agora.
  ⚠️ **Ver a foto NÃO depende de `fichas.custos`**: ela não é dinheiro. Quem manda a foto
  precisa de `fichas.editar`.
  ⚠️ **O `dono` do arquivo é a FICHA, não o produto** (`ficha-{id}`): duas versões do mesmo
  prato podem ter fotos diferentes, e é a montagem que muda entre elas.
  🔑 **O cartão aparece TAMBÉM na tela de CRIAR, e a primeira versão o escondia ali.** A ficha
  nova não tem id e a foto não teria para onde ir — então o cartão simplesmente não existia em
  `/fichas/nova`. Só que é EXATAMENTE ali que a pessoa está com a foto na mão, e ela concluiu
  que o sistema não tinha o campo (foi assim que o dono o encontrou faltando, no mesmo dia).
  Agora a imagem fica guardada no estado e sobe logo depois do `POST /fichas`, com prévia local
  (`URL.createObjectURL`, revogada na limpeza) enquanto não há nada no servidor.
  ⚠️ **Falhar o envio da foto NÃO é "não foi possível salvar"**: a ficha já existe daquele
  ponto em diante, e a frase genérica mandaria cadastrar tudo de novo — criando uma segunda
  ficha do mesmo prato. O `try` é só do upload, e a mensagem diz o que aconteceu e onde
  reenviar.
  ⚠️ **E a checagem do estado vazio mudou de lugar por causa disso**: "diz quando não há
  nenhuma" era afirmado na tela da ficha recém-criada — que agora nasce COM foto. O único lugar
  onde o vazio é garantido é a tela de criar, antes de escolher o arquivo. Mesma família do
  teste que descreve o estado do dia.
  🔑 **O seletor de arquivo do NAVEGADOR não conta como botão** (01/09/2026, segunda correção
  no mesmo dia). A primeira versão usava o `<input type="file">` cru: ele tem a cara do sistema
  operacional, muda em cada máquina e não se parece com nada mais do sistema — o dono olhou a
  tela e **não achou o botão**, com o campo bem ali. Agora é o corte da tela de Empresa: input
  `hidden` e um `.btn btn-secundario` que o clica ("Escolher imagem" na ficha que ainda não
  existe, "Enviar imagem" na que existe sem foto, "Trocar imagem" com foto).
  ⚠️ **E o teste passava assim**, porque perguntava só se o input EXISTIA — e input escondido
  responde "sim" do mesmo jeito. Passou a exigir o botão da casa e o campo fora da vista.
  ⚠️ Casar por `button.btn` DENTRO do cartão, não por texto solto na página: o rótulo "remover"
  ficou igual ao da empresa, e a checagem que procurava "remover foto" quebrou no instante em
  que os dois passaram a falar igual.
  ⚠️ **A suíte apaga a foto ANTES de arquivar a ficha**: arquivar não apaga o arquivo (nem
  deveria — ficha arquivada continua respondendo pelo histórico), e sem isso cada rodada
  deixaria mais duas imagens na tabela `arquivos`.
  ⚠️ **O corpo multipart precisa do CRLF antes do fecho da fronteira.** Sem ele o servidor não
  acha o campo e devolve 422 "Field required" — que se lê como rota errada, não como teste
  errado. Custou meia hora na primeira versão do helper da suíte.
- 🔑 **A ficha técnica se imprime** (`GET /exportar/ficha/{id}.pdf`, botão em `/fichas/[id]`,
  29/08/2026). A ficha existe para ser SEGUIDA, e quem segue está de pé na cozinha — não na
  frente do monitor. Sem o papel, a receita fica presa numa tela que ninguém leva para perto
  do fogão.
  🔑 **Ver a ficha e ver o CUSTO são permissões diferentes, e o PDF não podia ser a porta
  lateral disso.** Sem `fichas.custos` nenhuma coluna nem linha de dinheiro entra no arquivo —
  quem esconde é o servidor, como já era no JSON. Um PDF é justamente o que SAI da tela e
  circula; se o dinheiro vazasse por aqui, a regra do router de fichas viraria enfeite. A
  suíte cobra isso nos dois formatos.
  ⚠️ **O modo de preparo não é tabela** — é o texto que se lê enquanto se cozinha. `csv_de` e
  `pdf_de` ganharam `notas=[(rótulo, texto)]`, que fecham o documento depois dos ingredientes,
  na ordem em que se usa. No PDF a quebra de linha vira `<br/>`: o `Paragraph` do reportlab
  ignora a quebra crua e um preparo numerado sairia em bloco corrido.
  ⚠️ **Coluna sem informação SAI da ficha** — mesma regra da folha de contagem, que só mostra o
  local quando a contagem cobre mais de um. Numa receita simples "Qtd líquida" e "Observação"
  vêm vazias em todas as linhas e "Fator correção" é 1,00 repetido: três colunas mortas
  empurravam o documento para PAISAGEM. Sem elas a ficha cabe em **retrato**, que é o formato
  de quem vai pendurar o papel. Elas voltam sozinhas na receita que as usa — quem descasca
  cebola tem fator de correção, e aí a coluna é a informação mais importante da linha.
  ⚠️ **`exportacao.quantidade_br` existe porque texto MONTADO à mão escapa da formatação**: o
  resumo dizia `Rendimento;2.0000 UN` — ponto decimal e quatro zeros no meio de um CSV que usa
  vírgula em todo o resto. O valor virava string antes de passar pelo formatador, e nenhuma das
  duas formatações o alcançava. Os zeros à direita saem: "1,0000 UN" não informa mais que
  "1 UN", só sugere uma precisão que não existe ali.
  ⚠️ **`formatoPadrao` na janela**: o padrão é planilha porque a maioria dos relatórios é para
  CONFERIR, mas a ficha e a folha de contagem têm o papel como destino — abrir em "planilha"
  ali faz escolher errado por inércia.
- 🔑 **Todo PDF sai em papel TIMBRADO, e com o carimbo de quem o emitiu** (29/08/2026).
  O PDF sai da tela e circula: vira anexo de e-mail, papel na mesa do contador, foto no grupo.
  Sem o timbre ele não diz de que casa é; sem o rodapé não diz quem o emitiu nem quando — e um
  relatório sem essas duas coisas não se confere contra nada.
  Cabeçalho: logo + nome + CNPJ/IE + endereço + contato (`exportacao_catalogo.papel_timbrado`).
  Rodapé, em três partes: **título** à esquerda (uma página solta na mesa precisa dizer de que
  relatório é), **"emitido por Fulano em dd/mm/aaaa hh:mm"** ao centro, **"Página X de Y"** à
  direita.
  ⚠️ **Monta com o que EXISTE.** A base tem razão social, nome fantasia e UF, e mais nada. Uma
  linha reservada e vazia anuncia o que falta em cada página impressa; montar só o que tem sai
  limpo hoje e completo depois, sem ninguém tocar em nada.
  ⚠️ **A UF só aparece ATRÁS da cidade** — sozinha, virava uma linha de endereço escrita "SC".
  Nesse par a informação é o conjunto, não cada metade.
  ⚠️ **A logo vem do DISCO, por `arquivos.caminho_local`** — o PDF desenha a imagem, não a
  busca por HTTP. Mora naquele módulo pela mesma razão que `remover`: é o único que sabe onde
  os arquivos ficam, e é ele que muda no dia do Spaces. Altura fixa e largura pela PROPORÇÃO:
  logo esticada é pior que logo nenhuma.
  ⚠️ **Logo ausente ou ilegível NÃO derruba o relatório** — no App Platform `api/uploads/` é
  efêmera e some a cada deploy, então "sem logo" é estado normal, não erro.
  ⚠️ **O carimbo é calculado UMA vez, fora do rodapé**: `_CanvasNumerado` redesenha o rodapé de
  cada página no fim, e chamar `now()` ali daria horários diferentes entre a página 1 e a 40 do
  mesmo arquivo.
  ⚠️ **O timbre sai só na PRIMEIRA página** (é um flowable, não um `onPage`): repetido em 16
  páginas viraria ruído, e quem identifica as outras é o rodapé.
  ⚠️ Com o timbre em cima, o subtítulo padrão saiu — ele repetia o nome da casa e a data, e a
  data agora mora no rodapé. Dado repetido em dois lugares envelhece num deles.
  ⚠️ O **CSV não mudou** no timbre: ele já leva a linha "Botané Deli e Café — gerado em…".
  ⚠️ Mas o carimbo é do ARQUIVO, não de cada quadro: os anexos vinham com essa linha repetida
  embaixo de cada título, e a folha de um produto ficava com ela três vezes (`com_carimbo`).
- 🔑 **O nome do arquivo carrega o nome do REGISTRO** (`exportacao.slug`, 29/08/2026).
  `botane-ficha-431.pdf` obriga a ABRIR o arquivo para saber de que prato ele é — e quem baixa
  cinco fichas seguidas fica com cinco números na pasta de Downloads. Agora sai
  `botane-ficha-bolo-de-cenoura-v2-20260829.pdf`.
  ⚠️ **A versão entra junto na ficha**: duas versões do mesmo prato são dois documentos
  diferentes, e sem ela a segunda sobrescreveria a primeira.
  ⚠️ Acento vira letra sem acento e o resto vira hífen — nome de arquivo atravessa Windows,
  e-mail e nuvem, e cada um estraga um caractere diferente. Com teto de 45 caracteres.
  ⚠️ Vale também para a folha de contagem (`inventario-camara-fria`) e para a folha do produto.
- 🔑 **A folha de UM produto** (`GET /exportar/produto/{id}`, botão **Baixar** em
  `/produtos/[id]`): cadastro, saldo por local, embalagens de compra, quem fornece e os
  **últimos 50** movimentos. A tela junta tudo isso em blocos; quem precisava levar para fora —
  conferir uma compra, discutir preço com o fornecedor, responder ao contador — não tinha como.
  ⚠️ **O bloco de estoque exige `estoque.saldos`.** Saldo, custo médio e razão são dados de
  ESTOQUE e não passam a ser de cadastro por estarem no arquivo de um produto — mesma regra do
  custo na ficha.
  ⚠️ **Os ÚLTIMOS movimentos, não todos**: o razão de um insumo movimentado tem milhares de
  linhas, e quem abre a ficha de um produto quer o que aconteceu com ele agora. O razão inteiro
  tem relatório próprio.
  ⚠️ **Não há quadro principal**: são quatro assuntos do mesmo produto, e promover um deles a
  "a tabela" faria os outros três parecerem apêndice. O bloco principal fica só com título e
  resumo (`colunas=[]`), e cada quadro entra como anexo com o nome dele em cima.
  ⚠️ **Quadro vazio não entra** — produto recém-cadastrado não tem saldo nem fornecedor, e três
  tabelas vazias fazem o arquivo parecer defeituoso. Sem nenhum quadro, uma frase explica.
  ⚠️ O botão fica **fora do `podeEditar`**: baixar é de quem CONSULTA.
  ⚠️ **A ficha sai em RETRATO, e por isso `pdf_de` ganhou `orientacao`.** O corte automático é
  por número de colunas, e está certo para relatório de tabela — lá quem manda é a largura. A
  ficha é outra coisa: um documento com FORMA por convenção. Assim que a receita usava fator de
  correção ela caía em paisagem, e cartão de receita em paisagem não é o papel que se prende no
  armário da cozinha.
  ⚠️ **A coluna "No estoque" só entra quando houve CONVERSÃO de unidade.** Ela existe para o
  caso de a receita pedir 1 CX e o razão baixar 12 PCT; sem conversão é a cópia das duas
  colunas anteriores — e era uma das que empurravam a ficha para paisagem.
  ⚠️ **O custo da LINHA sai em centavos; o unitário, não.** A coluna vinha com "2,375" e
  "1,287" no meio de valores de dois dígitos, e é uma coluna que alguém soma com o dedo. O
  unitário é um PREÇO (R$ por KG) e fica com a precisão que tiver.
  🔑 **E o total do resumo NÃO virou a soma das linhas arredondadas.** Somar a coluna impressa
  dá um centavo a mais que "Custo da receita" — é o centavo que toda coluna arredondada carrega.
  A escolha é deliberada: o resumo mostra o número **autorizado**, o mesmo da tela e do CMV.
  Um relatório que discorda do sistema sobre o custo da receita é pior que um centavo de
  diferença numa soma feita à mão. (⚠️ É o oposto da regra do rodapé dos relatórios de tabela,
  onde o total FECHA com a coluna — lá o total é do próprio relatório; aqui ele é de fora.)
  ⚠️ `components/filtro-multiplo.tsx` saiu de dentro de `/inventario/novo` quando a exportação
  passou a precisar do mesmo controle; ganhou **busca dentro da lista** acima de 12 opções
  (99 locais e 70 categorias numa base real).
- 🔑 **A janela (`Modal`) era do tamanho do CONTEÚDO, e conteúdo longo saía da tela sem
  rolagem nenhuma** (29/08/2026). A de exportação, com cinco filtros, passava de mil pixels:
  num notebook os últimos campos e o botão de baixar ficavam fora, **e não havia barra de
  rolagem em lugar nenhum** — porque `Modal` trava o `overflow` do corpo da página enquanto
  está aberta. O defeito era do componente, não daquela tela: valia para toda janela do
  sistema, e só apareceu quando uma delas cresceu.
  Agora o cartão é limitado pela altura da JANELA (`max-h-[calc(100dvh-4rem)]`), vira
  `flex-col`, e só o miolo rola (`min-h-0 flex-1 overflow-y-auto` — sem o `min-h-0` um filho
  de flex não encolhe abaixo do próprio conteúdo, e o `overflow` não teria o que rolar).
  ⚠️ **`dvh`, não `vh`**: no celular a barra de endereço entra na conta do `vh`, e o pé do
  cartão fica atrás dela.
  ⚠️ **`Modal` ganhou `rodape`**, que fica FORA da rolagem: botão de ação que rolou para fora
  da vista é botão que não existe, e quem não o acha conclui que a janela não tem saída. A
  contagem da prévia fica ao lado dele porque é o número que se olha imediatamente antes de
  clicar.
  ⚠️ **A bateria rodava a 1440×1000 e não pegaria isso.** A checagem nova MEDE numa tela de
  notebook de verdade (1440×760) e devolve o tamanho depois — altura generosa demais no teste
  esconde exatamente a classe de defeito que o teste existe para achar.
- **Aviso de ação flutua** (`components/aviso-flutuante.tsx`, 20/08/2026): sucesso e erro de
  AÇÃO saem por `useAviso()` e aparecem presos ao canto inferior — a mensagem ficava no topo e
  o botão de salvar está no fim de um formulário longo, então quem clicava não via confirmação
  nenhuma e clicava de novo. Sucesso some em 6 s; **erro fica até fecharem**. O aviso pode levar
  UMA ação ("cadastrar outro"), que é a resposta ao "cadastrei, e agora?".
  ⚠️ **Os dois somem sozinhos** (26/08/2026): sucesso em 6 s, erro em 14 — a frase do erro é
  mais longa. Antes o erro ficava até alguém fechar, e uma pilha que não se limpa acaba tapando
  a tela em uso. O que torna isso seguro é o aviso **parar de contar enquanto o ponteiro está
  em cima** (ou o foco dentro): o medo real era a mensagem sumir no meio da leitura. A barrinha
  embaixo mostra quanto falta — sem ela, o aviso sumindo parece a tela piscando.
  ⚠️ Erro de **carregamento** continua inline no cartão (é ele que explica a tela vazia) — a
  regra de bolso: mensagem com "Falha ao carregar" fica; o resto flutua.
- ⚠️ **Voltar tem de parecer um controle**: era `class="rotulo"` (10,5px, maiúsculas, cinza) e
  lia como legenda. Virou `.link-voltar`, pílula com borda e seta.
- 🔑 **E a lição do Voltar nunca tinha sido generalizada — valia para mais trinta lugares**
  (29/08/2026, pedido do dono: *"há muitos lugares clicáveis que parecem somente palavras"*).
  Varredura dos 213 elementos clicáveis do front: **82 não tinham forma de controle**. A causa
  era `.rotulo` usada em AÇÃO — `vincular`, `criar produto`, `desbloquear`, `estornar`,
  `remover`, `desativar` —, que é a mesma tinta do `<th>` da tabela e da legenda do campo ao
  lado. Três peças novas em `globals.css`:
  **`.link-acao`** (pílula com borda: ação em linha, dentro de célula, aviso ou cartão),
  **`.link-acao-erro`** (a mesma, vermelha no hover — o que estorna, apaga ou remove se anuncia
  ANTES do clique) e **`.link-registro`** (o NOME que leva ao registro: sublinhado fino
  permanente, verde no hover).
  ⚠️ **O `<button>` do Tailwind 4 mostra a SETA, não a mão.** O Preflight não devolve
  `cursor: pointer` — só `.btn` pedia o dele —, então todo botão sem classe própria tinha
  literalmente a pista de "isto é texto". A rede de segurança está em `@layer base`.
  ⚠️ **`.link-registro` existe por causa do CELULAR.** Nos cartões (produtos, fichas, compras,
  inventário, vendas) o nome era `font-semibold` puro e a única pista aparecia no hover — onde
  não há ponteiro, não havia pista nenhuma de que o cartão inteiro era clicável.
  ⚠️ **As três vão em `@layer components`, ao contrário de `.campo` e `.btn`**: elas definem
  `display`, e CSS sem camada VENCE a utilitária do Tailwind (é a mesma nota do `.campo`). Sem
  a camada, o `lg:hidden` do "fechar" do menu lateral parava de valer e ele aparecia no desktop.
  ⚠️ Ficaram de fora, de propósito: abas com sublinhado, cartão selecionável com borda, o × de
  fechar (é símbolo, não palavra) e link dentro de frase — sublinhado já é a convenção do link.
- Manuais: `docs/manual-da-equipe.md` (o que cada função faz no dia a dia) e
  **`web/public/ajuda.html`** — o manual de referência: os treze processos e o caminho do dado,
  de onde entra até virar número.
  🔑 **A seção "De onde vem cada número" é o coração dele** (28/08/2026): segue UM quilo de
  café da nota até a variância, com a aritmética real em cada passo — custo de aquisição com
  frete rateado, custo médio ponderado (e por que a média simples erraria R$ 0,92/kg), ficha,
  custo congelado no item de venda, CMV real pela fotografia do razão, e a variância fechando
  **exatamente** com a perda apontada. Fecha com a tabela "cada número e sua origem" e com o
  que ENFRAQUECE cada um (produto sem unidade, prato sem ficha, venda sem vínculo). Quem
  confere um relatório sem saber a origem do valor acaba aceitando o que está lá. ⚠️ **Fonte única**: a tela `/ajuda` o exibe num quadro que
  cresce até a altura do conteúdo, e o mesmo arquivo é o que se publica como artifact
  (republicar sempre com a mesma URL). Reescrevê-lo em JSX criaria duas versões que divergem
  no primeiro parágrafo novo — e aí o sistema explicaria duas coisas diferentes sobre si.
- **O que falta na primeira parte está em [`docs/o-que-falta.md`](docs/o-que-falta.md)** —
  levantado em 25/08/2026 comparando o MAPEAMENTO item a item com o que existe. O maior item
  é a **carga inicial das fichas**: com zero fichas não há CMV teórico, nem variância, nem
  food cost. O documento também registra as três decisões em que a construção divergiu do
  mapeamento e por quê (a venda passou a baixar estoque, `modo_producao`, `KIT`).
- 🔑 **A descrição do produto é MAIÚSCULA, e quem garante é um GATILHO** (migração 036,
  27/08/2026 — o primeiro do projeto). A base tinha 752 de 3.226 em caixa mista: "Matcha
  Culinario 500g" ao lado de "CAFE EXPRESSO". Não é feiura — é lista que não se lê: numa
  conferência de compra o olho percorre a coluna, e caixa alternada quebra a varredura.
  ⚠️ **Gatilho e não helper porque o nome é escrito em CINCO lugares**: o formulário, o catálogo
  do Omie, o cardápio do PDV, a criação a partir do item da nota e a fusão de cadastros. Um
  helper teria de ser chamado nos cinco, e o sexto — que vai existir — nasceria sem ele. "Por
  padrão" é regra de DADO; quem garante regra de dado sem depender de memória é o banco.
  ⚠️ Só `nome` e `nome_curto`. **`observacao` fica fora**: é texto que alguém escreveu para ser
  lido, e em maiúsculas vira grito. `codigo` também, porque mexer nele mudaria o de-para.
  ⚠️ O `upper()` do Postgres foi conferido contra o do Python acento a acento.
  ⚠️ **A tela mostra `uppercase` por CSS** — só dica visual, para quem digita ver o que vai ser
  gravado em vez de descobrir depois. O valor real é normalizado no banco.
  ⚠️ **Toda suíte que compara nome de produto precisa de `.upper()`** — onze checagens de API e
  seis de tela caíram de uma vez quando o gatilho entrou, e nenhuma por bug: elas afirmavam sobre
  o que mandaram, não sobre o que foi gravado.
  ⚠️ ~~Nome de **fornecedor** NÃO segue a regra~~ — **revertido em 01/09/2026** (ver a
  migração 050 logo abaixo). O argumento era: "é razão social, vem de um lugar só, e 'Cia.
  Brasileira de Distribuição' em caixa alta perde a leitura sem ganhar nada".
- 🔑 **Fornecedor e tabelas de apoio também em MAIÚSCULAS** (migração 050, 01/09/2026, pedido
  do dono — e é uma REVERSÃO da nota acima). O argumento antigo vale para LER um nome isolado;
  é falso para o que a casa faz o dia inteiro, que é percorrer uma COLUNA procurando um item.
  Ali a caixa alternada quebra a varredura — e ter produto em caixa alta ao lado de fornecedor
  em caixa mista deixa a tela com duas convenções.
  Estado da base: 43 fornecedores, 31 setores, 111 locais, 14 categorias e 17 unidades fora do
  padrão. Cobre `fornecedores.nome` e `nome_fantasia`, `setores`, `locais_estoque`,
  `categorias` e `unidades_medida.nome`.
  ⚠️ **Gatilho, e não helper — a mesma razão da 036.** Estes nomes são escritos pelo
  formulário, pelo importador de fornecedores do Omie, pela família do Omie que vira categoria,
  pelo grupo e pela impressora do cardápio do PDV, e pela loja nova que nasce com um local.
  ⚠️ **NENHUMA colisão era possível**, e foi medido: a unicidade de `setores`, `locais_estoque`
  e `perda_motivos` já é `lower(nome)` — dois nomes que só diferem na caixa nunca puderam
  coexistir. Os 65 "ESTOQUE" da base são de 65 lojas, e a unicidade do local é
  `(id_unidade, lower(nome))`.
  ⚠️ **`unidades_medida.sigla` fica FORA, e não é esquecimento**: é chave primária referenciada
  por produto, ficha, item de nota e razão — subir a caixa ali não renomeia um rótulo, quebra o
  de-para. Mesma razão pela qual `produtos.codigo` ficou fora da 036.
  ⚠️ **`perda_motivos` fica fora de propósito**: não é uma das quatro tabelas da tela, e
  "Quebra no transporte" é uma frase, não um rótulo de coluna.
  ⚠️ **Dez checagens de API e três de tela caíram de uma vez, e nenhuma por defeito** — em
  `smoke_cadastros`, `smoke_notas`, `smoke_pdv_legal`, `smoke_produto_do_omie`, nos dois
  cenários e no `verificar.mjs`. Todas afirmavam sobre o que MANDARAM, não sobre o que foi
  gravado. É exatamente o que a 036 já tinha custado a onze; a lição não muda, mas o número de
  suítes que a esquecem, sim.
  ⚠️ **E a LIMPEZA da suíte de tela também casava pelo nome que mandou** — o setor de teste
  ficava ATIVO e a base acumulava um por rodada. Ao mexer numa regra de dado, procurar o nome
  nas asserções **e** no teardown.
- 🔑 **As tabelas de apoio deixaram de ser só-leitura depois de criadas**
  (01/09/2026, pedido do dono). Dava para criar e desativar, e **não dava para
  CORRIGIR** — os quatro PUT existem no servidor desde o começo e nenhuma tela os
  oferecia. Um setor cadastrado com o nome errado no primeiro dia ficava errado para sempre, e
  o "conserto" era desativar e criar outro, deixando o histórico apontando para um cadastro
  morto. É a mesma família do cadastro de loja e do "onde a pessoa trabalha": **o sistema sabia
  fazer e não oferecia isso a ninguém.**
  ⚠️ **A correção usa o MESMO formulário do cadastro**, e não uma janela nem campos na linha:
  criar e corrigir têm a mesma forma, para o olho reconhecer — o corte que Fornecedores e
  Usuários já usam. O botão troca "Adicionar" por "Salvar" e ganha um "cancelar" ao lado.
  ⚠️ **O formulário é trazido para a VISTA** (`#form-apoio` + `scrollIntoView`): com 184 locais,
  clicar em "editar" na linha 90 preencheria um formulário fora da tela, e a pessoa concluiria
  que o botão não fez nada. Em `requestAnimationFrame`, senão a rolagem chega antes dos valores.
  ⚠️ **Trocar de aba cancela a edição aberta**: senão o formulário das unidades de medida
  apareceria preenchido com o nome de um setor, dizendo "Salvar" para um registro que não está
  mais na tela.
  ⚠️ **A SIGLA da unidade de medida não se edita** — é a chave primária, e dela dependem
  produto, ficha, item de nota e razão. O campo fica desabilitado com a dica dizendo por quê;
  quem quer outra sigla cria outra unidade.
  ⚠️ **A categoria em edição sai da lista de "dentro de"**, ela e as filhas (casadas pelo
  `caminho`): dentro de si mesma seria um ciclo, e a consulta recursiva da árvore entraria em
  laço. Quem de fato barra é o servidor, com 400 e frase — a lista só evita oferecer o que vai
  ser recusado.
- ⚠️ **Cadastro em coluna lateral não cabe no cadastro.** Fornecedor (13 campos em 360 px) e
  usuário (uma lista de papéis que cresce, cada um com descrição de duas linhas, em 380 px) eram
  formulários na direita da lista: quem cadastrava rolava a tela para achar o botão, e no de
  usuário ele caía fora — marcava-se caixinha sem ver o que se marcava. Viraram
  `/fornecedores/novo` + `/fornecedores/[id]` e `/usuarios/novo` + `/usuarios/[id]`, com o
  formulário num componente só (criar e corrigir têm a mesma forma, para o olho reconhecer).
  Mesmo corte de Compras, Vendas e Inventário — **consultar e cadastrar são telas diferentes**.
- ⚠️ **Aba padrão escrita à mão abre na aba errada.** Tabelas de apoio abria em `"locais"`, que
  é a SEGUNDA da lista: entrar pelo menu caía nela com a primeira ali do lado, marcada como não
  escolhida. Agora o padrão é `ABAS.find(pode(chave))` — a primeira que a pessoa **pode ver**,
  que também resolve quem não tem permissão na primeira e caía numa aba vazia.
- ⚠️ **`.campo` é `width:100%` e vence a utilitária de largura do Tailwind.** `w-[110px]` num
  input com `campo` não faz nada — a largura tem de ir na COLUNA (`<th>`), e com `min-w` além
  do `w`: em `table-layout: auto` o navegador ignora a largura sugerida quando falta espaço.
- ⚠️ **Produto ATIVO sem unidade de estoque também devolvia 500.** A trava é do banco
  (`ck_produto_rascunho`) e é a certa — quantidade sem unidade não decide custo nenhum —, mas
  vazava como "Internal Server Error" para quem cadastrava um prato sem escolher unidade.
  Virou 400 com frase, e a saída ("salve como rascunho") vai junto. ⚠️ Ao adicionar validação
  que consulta uma coluna, **o `SELECT` do "antes" no PUT precisa trazê-la**: sem `um_estoque`
  ali, um PUT que só mudava o preço levava 400 sem ter tocado no assunto.
- ⚠️ **Nome repetido em tabela de apoio devolvia 500.** A unicidade é do banco (é o certo),
  mas deixar a constraint estourar dava "Internal Server Error" para quem só digitou duas
  vezes o mesmo nome — no primeiro dia, cadastrando setores e locais. `_recusar_repetido()`
  em `routers/cadastros.py` confere antes e devolve 409 com frase.
- ⚠️ **As suítes rodam contra base virgem.** `tests/comum.py` tem `garantir_local`,
  `garantir_locais`, `garantir_setores` e `garantir_fornecedor` — nenhuma suíte pode supor
  que existe local, setor ou fornecedor, nem contar linhas de semente. `garantir_fornecedor`
  procura pelo **CNPJ**, não pelo nome: o CNPJ é a chave única, e buscar por nome falhava
  quando o Omie simulado criava outro fornecedor com o mesmo documento.
- ⚠️ **Tabela nova que aponta para as tabelas limpas derruba `limpar_dados.py`** — e a
  mensagem do Postgres passa longe de "atualize a lista do script". Aconteceu com
  `produto_unidades` e com `cmv_movimentacao`: a limpeza estourava no meio e quem rodou achava
  que tinha limpado. O script agora **confere antes** (`referenciam()`) e recusa nomeando o que
  falta na lista.
- 🔑 **`--filiais-de-teste` na limpeza** (01/09/2026): as suítes criam uma loja por rodada e
  ninguém as apagava — `unidades` está em `PRESERVADAS`, e numa casa de verdade a loja fica.
  Dezenove tinham se acumulado. Não é só sujeira de lista: **filial ATIVA muda a barra
  superior**, porque o seletor de loja aparece e vira o primeiro `<select>` do documento.
  ⚠️ **O critério é estar INATIVA, não o nome.** As suítes desativam a filial delas no
  `atexit`, então "inativa" é exatamente a marca que elas deixam; casar por nome seria o
  palpite que este projeto já removeu uma vez. A matriz nunca entra.
  ⚠️ Roda **depois** do TRUNCATE: com movimento, venda ou nota apontando para a loja, a
  exclusão bate na chave estrangeira.
  ⚠️ Locais, setores e categorias com marca de suíte continuam saindo **na mão** —
  `--tabelas-de-apoio` esvazia tudo, inclusive o que a casa usa.
- ⚠️ **A limpeza NÃO toca nas tabelas de apoio** (locais, setores, categorias): elas são
  cadastro base e ficam. Mas as suítes criam locais e setores com marcador a cada rodada, e a
  lista incha — vale tirar o que não é da semente de fábrica depois de uma bateria. A flag
  `--tabelas-de-apoio` esvazia mesmo, e aí a base fica MAIS vazia que uma instalação nova (a
  semente do script 005 não volta: o `db_updater` não reexecuta migração já aplicada).
- **`web/scripts/base-vazia.mjs`** passa por todas as 26 telas com a base ZERADA e diz qual
  quebra. ⚠️ Tela com zero registro é o estado que ninguém testa e que o cliente vê no primeiro
  dia: divisão por zero, `lista[0]` e `.toFixed()` em nulo só aparecem ali — e aparecem na frente
  de quem está conhecendo o sistema. Não cria nada; roda depois de `limpar_dados.py`.
- `api/limpar_dados.py` zera a operação e deixa a base como instalação nova (`--simular`
  mostra sem apagar). Produtos e fornecedores saem inteiros de propósito: o seed não cria
  nenhum. **Recusa banco que não seja local.**
- **Tela inicial = painel do dono** (20/08/2026): `routers/inicio.py` entrega tudo numa
  chamada só — painel que faz seis requisições pisca seis vezes. ⚠️ **Número verdadeiro ou
  nenhum**: sem venda importada, `food_cost_pct` e `variancia` vão como `null` (não 0) e a
  tela mostra "—" com o motivo; zero ali pareceria um resultado excelente. Dinheiro só sai
  com `cmv.painel` — quem não tem recebe `dinheiro: null`, não um valor zerado. A cobertura
  de ficha viaja junto porque é ela que diz o quanto dá para confiar na variância.
- Telas: `/produtos`, `/fornecedores`, `/cadastros`, `/fichas`, `/estoque`, `/ajustes`,
  `/producao`, `/inventario`, `/transferencias`, `/compras`, `/cmv`, `/vendas`,
  `/integracoes`. As que têm detalhe e formulário em página própria: `/compras/[id]`,
  `/compras/nova`, `/inventario/[id]`, `/inventario/novo`, `/producao/[id]`, `/produtos/[id]`,
  `/fichas/[id]`, `/transferencias/[id]`, `/vendas/[id]`, `/vendas/lancar`,
  `/vendas/sem-vinculo`, `/fornecedores/novo`, `/fornecedores/[id]`, `/usuarios/novo`,
  `/usuarios/[id]`, `/lojas/nova` e `/lojas/[id]`.
- **Busca de cadastro é o padrão onde havia combobox** (21/08/2026):
  `components/busca-cadastro.tsx` + `lib/busca-cadastro.ts`. Digita-se código ou nome e dá
  **Tab**: um resultado preenche e segue; mais de um (ou nenhum) abre a janela de pesquisa já
  filtrada; a lupa abre direto. A busca vai ao SERVIDOR (`?busca=`), então não depende da
  página carregada — combobox só serve até umas dezenas de linhas. Aplicado em produto
  (ajustes, nota manual, conciliação, ficha, kit, venda) e fornecedor (nota manual, vínculo do
  produto). ⚠️ Categoria, setor, local e unidade **continuam `<select>`**: são poucos por
  natureza, e trocar por busca ali seria atrito sem ganho.
  ⚠️ Na ficha o item aceita insumo OU preparo com ficha; **o id do preparo entra negativo**,
  que é o que deixa produto 5 e ficha 5 conviverem na mesma lista.
  ⚠️ Ficha só de leitura mostra o nome como TEXTO, não campo desabilitado.
- **Filtrar ≠ escolher** (`FiltroCadastro`): nos saldos e no razão o texto continua filtrando
  solto ("café" traz os cinco), e a **lupa FIXA** um produto — que vira etiqueta com ×, para
  ninguém achar que a lista está curta por acaso. Fixado manda `id_produto`; texto manda
  `busca`. Na **contagem de inventário** o filtro é só texto e local: a lista já está na tela e
  é ela que se percorre — abrir janela para escolher um item seria perder a contagem de vista.
  ⚠️ O impacto previsto soma **todos** os itens, nunca os filtrados.
- **`fonteDaLista()`** serve a janela a partir de uma lista já carregada (as receitas da
  produção). Mesma janela, outra origem.
- **A contagem se monta por RECORTE** (`services/inventario_selecao.py`, migração 030,
  26/08/2026): **local, setor, categoria e tipo de produto**, cada um opcional, combinando com
  E, e vazio querendo dizer "todos". Contar a despensa inteira é raro — o que a casa faz é
  contar a câmara fria, ou só as bebidas, ou só o hortifrúti antes da feira; antes disso a
  única pergunta era o LOCAL, e quem quisesse um pedaço escolhia produto por produto.
  ⚠️ **A linha da contagem virou o par produto × LOCAL** (`inventario_itens.id_local`, unicidade
  `(inventário, produto, local)`). Sem local escolhido, o mesmo café pode ter saldo na câmara e
  no seco: são duas prateleiras, duas contagens e dois ajustes. Sem isso o fechamento lançaria
  os dois no mesmo lugar e sumiria com o estoque de um deles.
  ⚠️ **`inventarios.id_local` virou NULO quando a contagem cobre vários.** Não é redundância: é
  o atalho de que todo o resto depende, e continua sendo a resposta certa no caso comum.
  ⚠️ **Contar sem dizer o local, com o produto em dois, é RECUSADO — não adivinhado.** O erro
  só apareceria no fechamento, como falta num lugar e sobra no outro, e nada na tela denunciaria.
  ⚠️ **A guarda deixou de ser "um inventário aberto por local"** e passou a ser o par
  produto × local: contar as bebidas e o hortifrúti do mesmo local ao mesmo tempo é legítimo.
  ⚠️ **Cega por padrão** (`InventarioCreate.cega = True`): a opção certa não pode depender de
  alguém lembrar de marcá-la. Suíte que confere saldo congelado ou diferença passa `cega: False`
  de propósito.
  ⚠️ O vínculo é com o **tipo/setor/categoria do produto**, e o que gerou a lista fica gravado
  (`filtro_*`): quem abre uma contagem de três meses atrás vê 40 produtos e precisa saber por
  que aqueles 40.
  ⚠️ **`/inventario` é só a LISTA; `/inventario/novo` monta.** O formulário morava no topo da
  lista e empurrava as contagens para fora do campo de visão — com quatro filtros e a prévia não
  caberia. Mesma separação de Compras. A prévia (`GET /inventarios/previa`) diz **quantas linhas
  viriam, de quais locais**, antes do botão: numa base real o filtro em branco traz o cadastro
  inteiro, e descobrir isso depois custa cancelar e recomeçar.
  ⚠️ O **nome** é editável depois, inclusive com a contagem fechada — é rótulo, não mexe em item
  nem em razão.
- **A contagem tem tela própria, feita para o celular** (`/inventario/[id]`, 21/08/2026):
  quem conta anda pela despensa com o telefone, e uma tabela de dez colunas não serve na mão.
  Cada produto é um cartão; o progresso fica grudado no topo; há filtro "só o que falta".
  ⚠️ **Grava item a item, no blur** — contagem que só existe na tela até um "salvar tudo" no
  fim é contagem que se perde. ⚠️ A **unidade é escolhível** (migração 019), com a de estoque
  por padrão: quem conta conta caixa, e converter de cabeça é onde o erro entra. `qtd_contada`
  segue na unidade de ESTOQUE (é ela que o fechamento compara); `qtd_informada`/`um_informada`
  guardam o que foi digitado, senão ninguém sabe depois que 36 eram 3 caixas de 12.
- **Contagem cega** (`inventarios.cega`, migração 020): opção ao abrir o inventário. Ver o
  saldo esperado transforma a contagem em conferência — a pessoa lê 12, olha a prateleira e
  escreve 12. ⚠️ O esconderijo é no **servidor**: enquanto ABERTO, `qtd_sistema`, `diferenca`,
  `custo_medio` e `diferenca_valor` saem `null` para todos, e a folha CSV perde as colunas.
  Esconder só na tela deixaria o número no JSON e no papel impresso. Ao fechar, tudo aparece.
- ⚠️ **Seletor com uma opção só, desabilitado, lê como travado.** O de unidade da contagem
  ficava assim para produto sem embalagem cadastrada. Agora ele oferece as três origens que
  convertem de verdade — unidade de estoque, embalagens do produto e unidades da **mesma
  grandeza** (KG↔G sem cadastro nenhum) — e, ao lado, o caminho "contar em outra embalagem?"
  para o cadastro do produto. ⚠️ Dentro de UNIDADE, siglas com o mesmo fator base ficam de
  fora: CX e PCT não se convertem entre si (é a mesma regra de `custos.converter`).
- ⚠️ **`.campo` tem `font-size: 15px` e vence a utilitária** — abaixo de 16px o Safari do
  iPhone dá **zoom ao focar** e a tela salta a cada campo. Use `.campo-toque` (16px + alvo
  maior) em tela de uso no aparelho. `scripts/celular.mjs` fotografa e checa corte lateral.
- **As quatro tabelas de apoio ficam num item de menu só** — decisão do dono, 24/08/2026,
  depois de experimentar as quatro separadas. ⚠️ Como "Tabelas de apoio" não é o nome de nada
  que alguém procura, **a tela diz o que tem dentro** logo abaixo do título, e cada aba tem
  endereço próprio (`/cadastros?aba=locais`) para guardar e voltar direto.
  ⚠️ O item de menu aceita **lista** de chaves — Tabelas de apoio serve a quatro permissões.
- ⚠️ **`innerText` não enxerga valor de campo.** Depois que a escolha virou input, "o nome
  aparece na tela" ficou falso no teste e verdadeiro no monitor — `verificar.mjs` tem
  `textoVisivel()`, que junta `innerText` com o valor dos inputs.
- **Consultar e lançar são telas separadas** (21/08/2026): entrada, saída, perda e
  transferência eram quatro botões no cabeçalho de `/estoque`, que é onde se CONSULTA.
  Viraram **Estoque ▸ Ajustes** (`/ajustes`): escolhe-se o tipo e o formulário se molda a ele.
  Depois de lançar o formulário **fica aberto e limpo** — quem ajusta um item ajusta o
  próximo. ⚠️ O item de menu aceita **lista** de chaves (`chave: string | string[]`): Ajustes
  serve a quatro permissões e quem só tem a de perda também precisa chegar nele.
- ⚠️ **A busca da integração vive na tela do ASSUNTO, não só em Integrações.** `/vendas` ganhou
  **Buscar no PDV** (27/08/2026), gêmeo do "Buscar no Omie" de `/compras`, mais o
  **Reconciliar N pendente(s)** quando há item de venda sem produto. Quem abre Vendas para ver as
  vendas não vai lembrar que a busca mora noutra tela — e venda não buscada é receita faltando no
  CMV do período, sem nada denunciando.
  ⚠️ **O `modo` viaja na resposta de `/pdv/sincronizar`**, como já viajava na do Omie: sem ele,
  quem está em simulado importa venda de demonstração e não tem como saber — os números aparecem
  no CMV como se fossem da casa. A tela escreve "(modo simulado — dados de demonstração)".
- **Cada nota tem endereço** (25/08/2026): `/compras` é só a LISTA, `/compras/nova` digita e
  `/compras/[id]` mostra — com **cabeçalho, itens e total**, no mesmo modelo do formulário de
  digitação. Antes as três coisas dividiam a mesma tela: o formulário empurrava as notas para
  fora do campo de visão, e a conferência mostrava os itens espremidos e **nunca somava o
  total** — quem conferia via as linhas e não via o número que se bate contra o papel do
  fornecedor. `/compras/[id]/editar` corrige a digitada (a correção também é longa demais para
  caber num cartão).
- **`services/nfe_xml.py`** + `routers/notas.py`: a casa opera **sem integração nenhuma**. A
  nota entra por três portas — XML da NF-e, digitação e Omie — e da gravação em diante o
  caminho é um só (conciliação → conversão → rateio → razão). Por isso o ciclo da nota
  (conferir, vincular, lançar, estornar) mora em `notas.py`, e `omie.py` ficou só com
  credencial, sincronização e catálogo. Nota digitada não tem chave da NF-e: a repetição se
  reconhece por fornecedor + número + série (índice único `ux_nota_manual`).
  ⚠️ **Só a nota MANUAL se edita** (`PUT /notas/{id}`), e só antes de lançar: a que veio do
  XML/Omie é o documento do fornecedor, e mudar valor ali faria o sistema divergir da nota
  fiscal sem rastro. Os itens são reescritos inteiros — nada virou movimento ainda, e casar
  linha a linha só abriria caminho para item órfão.
- 🔑 **O custo inicial vindo do Omie** (migração 049, `importador.custos_iniciais`, botão
  **Trazer o custo inicial** em Integrações, 01/09/2026, pedido do dono). Medido na base:
  **2.323 produtos ativos que controlam estoque estavam sem custo NENHUM** — nunca entrou nota
  deles aqui e não há preço de fornecedor. Sem custo não há ficha, nem CMV teórico, nem margem:
  o prato entra na conta **valendo zero** e o food cost sai bom demais, sem nada denunciando. O
  Omie já sabe o número (o CMC da posição de estoque), e a tela só sabia COMPARAR os dois.
  🔑 **É REFERÊNCIA, não movimento — e essa é a decisão que importa.** Nada entra no razão e
  nenhum saldo muda: o CMV real continua saindo do que a casa comprou e contou. Como movimento,
  2.323 linhas erradas entrariam no CMV do período da carga e **não se apagariam** — o razão é
  append-only, e a única saída seria estornar 2.323 movimentos.
  ⚠️ **`produtos.custo_referencia` é o ÚLTIMO degrau de `custos.custo_do_insumo`**, depois do
  médio do razão e do último preço do fornecedor. A ordem é a da confiança: o médio é o que a
  casa pagou com o frete DELA rateado dentro; o preço do fornecedor é o que ela negociou; a
  referência é o que outro sistema acha — melhor que nada e pior que os dois.
  ⚠️ **Só quem NÃO tem custo**, e rodar de novo só alcança quem continua sem. Referência
  sobrescreve referência; custo de verdade, nunca.
  ⚠️ **CMC zero é PULADO.** Zero não é um custo: é o Omie dizendo que não sabe, e gravá-lo faria
  a ficha calcular com um número inventado — pior que calcular sem, porque o aviso de
  "sem_custo" some.
  ⚠️ **`custo_referencia_origem` existe para daqui a seis meses**: sem ela ninguém sabe se
  aquele número foi importado ou digitado, e é essa diferença que decide se ele pode ser
  sobrescrito sem perguntar.
  ⚠️ **A prévia vem antes, sempre** (`GET /omie/custos-iniciais/previa`): mesma varredura, sem
  gravar. Com 2.323 produtos, descobrir o efeito depois é tarde. E o de-para é
  `vinculo.por_codigo_omie` — a coluna e depois os apelidos, senão o principal que absorveu um
  duplicado ficaria de fora.
  ⚠️ **A suíte provava a precedência lançando uma ENTRADA no produto da conferência** — e o
  razão é append-only: o saldo ficava lá e a rodada seguinte falhava em "o saldo daqui é zero",
  acusando um defeito que não existia. Agora ela usa produto próprio e escreve o
  `custo_referencia` direto. **Teste que deixa rastro derruba a próxima; aqui o rastro seria
  permanente.**
- **Cadastro pode vir do Omie por três caminhos** (20/08/2026): catálogo de produtos (já
  existia, nasce RASCUNHO), **catálogo de fornecedores** (`importar_fornecedores`) e
  **criar produto direto do item da nota** (`POST /notas/itens/{id}/criar-produto`, que já
  cria o de-para e o `produto_fornecedor`). ⚠️ O importador de fornecedores **só preenche o
  que está em branco** — nunca sobrescreve o que alguém digitou aqui, senão reimportar
  desfaria correção. ⚠️ No Omie **cliente e fornecedor moram na mesma lista**: daí o
  `apenas_completar`. ⚠️ Criar produto do item **vincula ao existente quando o EAN já é de
  outro produto** — dois cadastros para o mesmo insumo partiriam o custo dele em dois (antes
  disso era 500). Depois de cada sincronização com nota nova, os fornecedores da leva são
  completados sozinhos.
- **Achados da PRIMEIRA conta real** (24/08/2026) — cada um derrubava ou falseava a
  importação, e nenhum aparecia no modo simulado:
  1. ⚠️ **Fornecedor se separa de cliente por ETIQUETA.** Sem filtro, uma conta de 919
     cadastros trouxe **888 clientes** (pessoas físicas) para dentro dos fornecedores. O
     filtro vai no servidor: `clientesFiltro: {"tags": [{"tag": "Fornecedor"}]}` — desce 648
     em vez de 919. A etiqueta é configurável na tela (em branco = traz todo mundo).
  2. ⚠️ **`ListarProdutos` sem `filtrar_apenas_omiepdv: "N"` devolve ZERO.** A conta tinha
     2.198 produtos e a importação dizia "0 criado(s)" — indistinguível de "não tem catálogo".
  3. ⚠️ **Unidade que a casa não tem derrubava a carga inteira** pela FK (o catálogo trazia
     "M", de metro). Agora o produto nasce **sem unidade** e a mensagem conta quantos foram —
     é rascunho, e rascunho existe para lembrar que falta conferir unidade e fator.
  4. ⚠️ **O mundo real não respeita largura de coluna.** O "código" de um produto era a
     descrição inteira (42 caracteres) e o NCM vinha `2202.99.00.05`. Todo texto sai **aparado
     no tamanho da coluna** no mapeador, e NCM só em dígitos (pontuado num lado só nunca casaria
     com o do XML).
  5. ⚠️ **O teto de páginas truncava calado**: 992 de 2.198, e a mensagem dizia só "992
     criado(s)". `paginar` agora avisa por `ao_truncar(trazidos, total)`.
  6. ⚠️ **O Omie BLOQUEIA a conta por consumo indevido** quando as chamadas vêm rápido demais
     — e o bloqueio pega a integração inteira. Há `INTERVALO_MINIMO` entre chamadas, a espera
     que ele pede ("Aguarde 56 segundos") é obedecida, e **erro de estrutura não é repetido**:
     parâmetro errado continua errado na quarta tentativa e só gasta a cota.
  7. ⚠️ **`ListarNotaEnt` não aceita `apenas_importado`** — foi esse parâmetro inválido que
     consumiu cota até o bloqueio.
- **O cadastro do produto aproveita mais do que o Omie já tem** (migração 031, 26/08/2026).
  Medido na conta real: 2.189 produtos importados, **todos** com NCM, **1.149 com EAN** e
  **zero com categoria** — e sem categoria o CMV por grupo e a curva ABC não separam nada.
  ⚠️ **O buraco não era o campo, era a reimportação: produto que já existia não recebia NADA.**
  A importação contava "atualizado" e seguia com um `continue`, então quem foi criado antes de
  um campo ser mapeado — ou criado a partir do item da nota — nunca mais era completado. Agora
  `_completar_produto` preenche **só o que está em branco** (`coalesce(coluna, %s)`), pela mesma
  regra do importador de fornecedores: reimportar não pode desfazer correção. Quem corrigiu
  corrigiu porque o dado de lá estava errado.
  ⚠️ Campos novos: `marca`, `cest`, `peso_liquido`, `peso_bruto`, `sincronizado_em`. **Peso é
  conversão, não enfeite** — o pacote entra por UN e a ficha consome em KG; o LÍQUIDO é o que
  interessa, porque o bruto inclui a embalagem.
  ⚠️ **A família do Omie vira categoria**, criada na primeira vez que aparece: é a classificação
  que a casa já fez do outro lado, e deixá-la para trás obrigava a classificar dois mil itens
  à mão.
  ⚠️ **`produtos.codigo_omie` já era o "código interno" que sobrevive à troca do código** — não
  havia campo a criar. Ele guarda o `codigo_produto` do Omie (o id de lá, que a casa não
  escolhe), tem índice único e é o nível 2 da cascata de conciliação. `produtos.codigo` é o da
  casa e pode ser renomeado à vontade; a suíte cobra que renomear NÃO faça a importação criar um
  duplicado. ⚠️ **O vínculo com o Omie NÃO aparece na tela do produto** — é interno, e quem
  cadastra não tem o que fazer com ele.
  ⚠️ **O EAN estava no formulário e não tinha campo na tela.** Era enviado ao salvar e lido pela
  conciliação da nota, mas ninguém conseguia ver nem digitar: o dado só entrava pela importação
  do Omie. Campo que o servidor aceita e a tela não oferece é campo morto na direção inversa — e
  esse some sem ninguém notar, porque nada quebra. O `verificar.mjs` passou a cobrar os cinco
  campos fiscais do formulário.
  ⚠️ **O `ListarProdutos` do Omie NÃO diz quem fornece o quê** — conferido campo a campo contra
  a conta real. Quem sabe isso é a NOTA, e até aqui o vínculo só nascia no LANÇAMENTO: numa base
  real, 227 produtos já tinham aparecido em nota com fornecedor e só 107 tinham vínculo. O resto
  eram notas importadas e não lançadas, que é o estado normal de quem acabou de sincronizar.
  `POST /notas/vincular-fornecedores` fecha essa lacuna (185 vínculos na primeira execução).
  ⚠️ **Preço só de nota LANÇADA**: `custo_aquisicao_unitario` é calculado no lançamento, e o
  valor bruto da linha não é custo.
  ⚠️ **A conta real deixa `marca`, `cest`, `peso` e `descricao_familia` VAZIOS.** O mapeador lê
  os nomes certos (conferidos num registro só, em 26/08/2026); é o cadastro do cliente que não
  os preenche. O que ele preenche é descrição, código, EAN, NCM, unidade e valor.
- 🔑 **As notas de compra estão em `produtos/recebimentonfe`, NÃO em `produtos/notaentrada`**
  (24/08/2026). O segundo é o lançamento manual de nota do Omie: na conta do cliente tinha
  **uma** nota, de 2024, enquanto o recebimento de NF-e tinha **3.670**. Quem olhasse só o
  primeiro concluiria que a casa não compra nada. A varredura usa `ListarRecebimentos` para os
  cabeçalhos e `ConsultarRecebimento` (por `nIdReceb`) para os itens — a lista **não traz item
  nenhum**, e o detalhe só é pedido para nota que ainda não existe aqui: pedir o de todas
  custaria meia hora e a conta bloqueada. Mapeador: `recebimento_de_nfe` / `item_do_recebimento`.
- 🔑 **A conferência de estoque com o Omie NUNCA funcionou até 27/08/2026 — e o modo simulado
  dizia que sim.** `GET /omie/conferencia` sempre voltou "Tag [PAGINA] não faz parte da
  estrutura"; cada recusa gastava cota. Três erros empilhados, e o segundo é o pior:
  1. **`ListarPosEstoque` tem um dialeto SÓ DELE** (`DIALETO_POSICAO`): aceita `nPagina`,
     **recusa** `nRegistrosPorPagina` e quer `nRegPorPagina`; responde `nTotPaginas`/
     `nTotRegistros`. São **três** dialetos, não dois — e a lição não é o número: é que **o
     dialeto é por CHAMADA, não por módulo**. Uma chamada com um registro só diz qual é.
  2. **O mapeador lia `cCodigo` como `codigo_omie`.** `cCodigo` é o código da CASA registrado no
     Omie ("104304"); `codigo_omie` guarda o id de lá (`nCodProd`, "7302593753"). Nunca casava —
     e o sintoma seria uma **lista vazia**, que se lê como "está tudo certo". Mesma família do
     erro que ligou REDBULL a LIMÃO TAITY: ler o identificador errado não dá erro em lugar nenhum.
  3. **A comparação olhava só o custo médio.** Saldo diferente com custo igual é o caso mais
     comum de todos — a entrada lançada de um lado só.
  ⚠️ **E a fixture tinha sido escrita a partir da suposição errada** (`pagina`, `cCodigo`), então
  o simulado confirmava a suposição de quem a escreveu. **Fixture que copia o que se imagina não
  testa nada.** Agora ela copia a forma real, lida da conta do cliente.
  ⚠️ A resposta virou **objeto**, não lista: `conferidos`, `sem_cadastro_aqui`, `divergentes` e
  `truncado`. Lista sozinha não distingue "nenhuma divergência" de "nenhum produto comparado", e
  a tela mostra o resumo ANTES da tabela por isso. Medido na conta real: **1.987 produtos em
  ~17 s** (10 páginas de 200).
- ⚠️ **Código único repetido virava 500.** `codigo_omie`, `codigo_pdv` e `codigo_barras` têm
  índice único, e a violação vazava como "Internal Server Error" para quem só digitou um código
  que já é de outro produto. Virou 409 com frase que **nomeia o dono** — porque a ação seguinte
  quase sempre é abrir aquele cadastro e usar **Vincular**. Mesma família do nome repetido em
  tabela de apoio.
- ⚠️ **O Omie tem DOIS dialetos de paginação** (`cliente.DIALETO_PADRAO` e `DIALETO_HUNGARO`).
  Os módulos antigos falam `pagina`/`registros_por_pagina`; o recebimento exige
  `nPagina`/`nRegistrosPorPagina` e recusa o outro com "Tag [PAGINA] não faz parte da
  estrutura". Cada chamada recusada gasta cota — e cota gasta bloqueia a conta.
- ⚠️ **`ListarRecebimentos` não aceita filtro de data nenhum.** Testados e recusados:
  `dDtInicial`, `dDataInicial`, `dEmissaoDe`, `dDtEmissaoDe`, `dRegistroInicial`. Aceita só
  `cEtapa` e `nIdFornecedor`. Como a lista vem da nota mais VELHA para a mais nova, a varredura
  vai **da última página para a primeira** (`paginar(do_fim=True)`) e para na primeira página
  inteira fora da janela — senão a sincronização diária atravessaria três anos de histórico.
- **`nIdProduto` do item é o `codigo_omie` do produto** — nível 2 da cascata de conciliação,
  antes do EAN. É o de-para que o Omie já fez. Numa conta real, **109 de 114 itens** acharam
  produto por aí assim que o catálogo entrou.
- **`POST /notas/reconciliar`** passa a cascata de novo nos itens pendentes. Existe porque a
  ordem real é: chegam as notas, e só depois o cadastro fica pronto. Sem isso, item que não
  achou dono no dia da importação só sairia da fila na mão. Nota **lançada** não se mexe (os
  movimentos já estão no razão) e item ignorado fica ignorado.
- ⚠️ **Produto sem `um_estoque` NÃO entra no razão** (`lancar_nota`). Quantidade sem unidade é
  número sem significado — "3" de champignon não diz se são três bandejas ou três quilos —, e o
  custo médio que sair daí contamina ficha, CMV e a próxima compra. O catálogo do Omie cria
  rascunho sem unidade de propósito (a sigla do fornecedor pode não existir na casa); é no
  lançamento que a dívida é cobrada, e a recusa **nomeia todos** os produtos de uma vez.
- ⚠️ **O rodapé de tributos do DANFE vem grudado na descrição** e ia para o nome do produto:
  59 cadastros se chamavam "MAMÃO FORMOSA Trib. Aprox. (Fed: R$ 3,63…) Fonte: IBPT/…".
  `mapeadores._nome_limpo` corta na entrada; a migração 023 limpa o que já entrou.
- 🔑 **O `vTotalItem` do Omie JÁ TRAZ frete, IPI/ST e desconto rateados pelo emitente**
  (25/08/2026). Tratar isso como mercadoria e ratear as acessórias da nota por cima cobrava
  tudo DUAS vezes: numa conta real, R$ 74,44 a mais no razão e um queijo entrando 13,5% acima
  da nota. `mapeadores._acessorias_do_emitente` reconhece a sobra (`vTotalItem` − mercadoria
  líquida) e a transforma em acessória INFORMADA — a mesma regra que o XML já seguia: quando o
  emitente rateou, o rateio é dele e ninguém soma nada por cima. A mercadoria passou a ser
  **quantidade × preço**, nunca `vTotalItem`, e o desconto da NOTA guarda só o que não está
  nos itens (`vTotalDescontos` é a soma dos `vDesconto`). Migrações 024 e 025 consertam o que
  entrou antes; nota já lançada precisa de estorno + novo lançamento.
- ⚠️ **Fator 1 num vínculo não é resposta, é a falta dela.** `codigos_externos.fator` e
  `produto_fornecedor.fator` nascem 1 por padrão — e **o lançamento da nota CRIA a linha de
  `produto_fornecedor`** só para guardar o último preço. A cascata de `_fator_do_item` aceitava
  esse 1 como informação, e o vínculo recém-criado passava na frente do `fator_compra` do
  produto: o galão de azeite de 5 L entrou certo na primeira nota e virou 1 L na segunda, sem
  ninguém mexer no cadastro. Agora só fator **diferente de 1** conta como resposta.
- ⚠️ **Cópia congelada acompanha a largura da ORIGEM.** `cmv_movimentacao.codigo` era
  `varchar(20)` contra `produtos.codigo varchar(40)`: **fechar o mês estourava com 500** assim
  que a base tinha um código real de 40 caracteres. Migração 026. É a terceira vez que largura
  de coluna quebra com dado de verdade (catálogo do Omie e NCM foram as outras).
- ⚠️ **A unidade da nota ia CRUA para `produtos.um_compra`, que é chave estrangeira.** Uma
  conta real trouxe "UND", "BJ", "GA", "GF", "1UNID" — e criar produto a partir do item da nota
  devolvia 500 sem dizer por quê. Sigla desconhecida vira nulo.
- **A busca das notas pode rodar sozinha** (`services/omie/agenda.py`, migração 033,
  26/08/2026): `MANUAL` (o padrão), `HORARIA` ou `DIARIA` numa hora escolhida, por loja, mais
  uma janela em dias opcional (nulo = a janela adaptativa de sempre). Nota que chega na sexta e
  ninguém busca até segunda é nota que não entrou no estoque — e o CMV do fim de semana sai com
  compra a menos.
  ⚠️ **O padrão é MANUAL e tem de continuar sendo.** Cada busca consome cota, e o Omie
  **bloqueia a integração inteira** de quem consome demais: ligar é decisão de quem paga a
  conta, não algo que uma migração liga sozinha. A tela avisa que "a cada hora" são 24 buscas
  por dia.
  ⚠️ **O relógio é `agenda_rodou_em`, não `ultima_sincronizacao`** — a segunda só avança quando
  alguma nota chega, e usá-la como relógio faria o agendador tentar de novo a cada minuto numa
  casa sem nota nova, que é a casa normal de domingo. Por isso ele avança **mesmo com erro**: o
  erro fica em `agenda_ultimo_erro`, à vista na tela, e a próxima tentativa é no horário
  seguinte. Repetir em cima de um bloqueio do Omie só o prolonga.
  ⚠️ A DIÁRIA dispara na hora escolhida **e só uma vez no dia**: sem a segunda condição ela
  rodaria a cada minuto durante os sessenta minutos daquela hora.
  ⚠️ **`pg_try_advisory_xact_lock` antes de olhar o relógio**: duas instâncias da API (ou o
  worker do `--reload` com um órfão) leriam a mesma linha vencida e gastariam cota em dobro.
  ⚠️ O laço vive no `lifespan` e sobe SEMPRE — quem decide é a configuração. Se ele só subisse
  havendo agenda, ligar exigiria reiniciar a API, e ninguém lembraria disso. A busca roda em
  `asyncio.to_thread`: o importador é síncrono e leva dezenas de segundos; no laço de eventos
  travaria a API inteira enquanto isso.
- ⚠️ **A janela da busca do Omie é adaptativa** (`importador.janela`): sem parâmetro, vai
  **desde a última sincronização com 7 dias de folga** — a folga existe porque nota emitida
  antes e lançada no Omie depois cairia fora se a janela começasse onde a anterior parou, e
  ninguém veria (o resultado seria "0 novas"). `desde=` faz a carga inicial do histórico;
  `dias=` fixa. O controle do que já veio continua sendo a **chave da NF-e**, nunca um
  marcador. `GET /omie/conferencia-notas` compara período a período e **nomeia** as notas que
  faltam — "0 novas" sozinho não distingue "nada mudou" de "passou batido".
- **`services/omie/`**: `cliente.py` (HTTP, paginação, back-off, modo simulado com fixtures),
  `mapeadores.py` (**o único arquivo que muda quando a credencial real chegar** — cada campo
  é lido por uma lista de nomes possíveis) e `importador.py` (de-para em cascata, rateio,
  conversão, lançamento).
- Credenciais ficam cifradas (`services/segredos.py`, Fernet com chave derivada do
  `JWT_SECRET`) e **nunca voltam pela API** — só mascaradas. Trocar o `JWT_SECRET` invalida
  as credenciais guardadas.
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
- 🔑 **O ABACATE: um cadastro por fornecedor, e o de-para que junta os cinco** (01/09/2026,
  pedido do dono). O catálogo do Omie cria um produto por CÓDIGO, e o mesmo abacate aparece uma
  vez para cada fornecedor que já o vendeu. O pedido foi "um produto principal e poder vincular
  os demais, por uma tabela auxiliar com os códigos do Omie".
  ⚠️ **A tabela já existia** — `codigos_externos`, chave `(sistema, código) → id_produto`, com
  fornecedor, fator, a descrição de lá e quem confirmou. Ela é o **nível 1 da cascata** de
  conciliação da nota, e o "aprender" do item pendente já a alimentava. O que faltava era o
  lado do PRODUTO do Omie, e uma tela.
  🔑 **A fusão DESCARTAVA o `codigo_omie` do absorvido** — enquanto o `codigo_pdv` virava
  apelido, na MESMA função, com a justificativa de que senão "ele voltaria a criar rascunho na
  importação seguinte". A mesma situação, tratada de dois jeitos. O efeito era o trabalho se
  desfazendo sozinho: juntavam-se os cinco abacates e, na primeira nota que trouxesse o código
  de um absorvido, o sistema não achava o principal (a cascata filtra `AND ativo`, e ele está
  arquivado) — o item caía na fila de pendentes e quem clicasse em "criar produto" recriava o
  duplicado. Agora ele vira apelido, e a coluna do absorvido é **zerada** junto: ela é única, e
  deixá-la lá manteria o código preso a um cadastro arquivado.
  ⚠️ **`SISTEMA_PRODUTO = "OMIE_PRODUTO"` é um espaço de nome NOVO, e tinha de ser.** O
  `sistema = "OMIE"` guarda o código que vem na LINHA da nota (o do fornecedor); o identificador
  do produto no Omie é outra coisa, que pode ter o mesmo valor. Enfiar os dois na mesma chave é
  a família do erro que ligou REDBULL a LIMÃO TAITY.
  🔑 **Tudo pelo MESMO botão Vincular, e ele passou a aceitar VÁRIOS** (decisão do dono, depois
  de ver a primeira versão). Houve um cartão separado "Outros códigos deste produto" no cadastro,
  com endpoints próprios para gravar e tirar código à mão — e ele **saiu**: duas portas para a
  mesma coisa são duas versões da mesma verdade, e a janela do Vincular já é onde se reconhece
  que dois cadastros são o mesmo produto. Juntar os cinco abacates um a um seria abrir aquela
  janela cinco vezes, e a quinta já não lembraria o que a primeira decidiu.
  🔑 **E o "Como fica" mostra as LINHAS DE CÓDIGO EXTERNO que vão sobrar**
  (`previa.codigos_externos`), com a origem de cada uma: **principal** (a coluna do que fica),
  **vira apelido** (a coluna do absorvido, a linha que antes era descartada) e **já aponta** (o
  que os dois lados já tinham). É o que faz a fusão em lote ser confiável — sem ver por quais
  códigos o cadastro vai responder, confirma-se no escuro e o defeito só aparece na nota que
  não achou dono.
  ⚠️ **Sem código do lado que fica, o do absorvido sobe a PRINCIPAL** em vez de virar apelido —
  a prévia diz exatamente o que `_absorver` faz, e a suíte cobra os dois caminhos.
  ⚠️ **Todos os escolhidos têm de cair no MESMO principal.** A direção é dos fatos: um cadastro
  com história puxa a fusão para o lado dele. Num lote isso vira trava com frase, porque o
  sobrevivente seria outro e a pessoa confirmaria uma coisa acontecendo outra.
  ⚠️ **Um pedido por cadastro, em ordem, e parar no meio deixa as anteriores feitas** — que é um
  estado bom, não pela metade: cada fusão é a mesma operação repetida. A mensagem de erro diz
  quantas já foram.
  ⚠️ **`key={escolhidos.length}` no `BuscaCadastro`**: ele guarda o texto digitado em estado
  próprio e só o sincroniza quando o `selecionado` muda — passando `null` sempre, o nome do
  produto anterior ficaria no campo e o próximo seria digitado por cima dele.
  ⚠️ **E a janela passou a ser o `Modal` da casa, não um overlay próprio** (01/09/2026, pedido
  do dono). Ela montava o seu — e com a lista de escolhidos e a tabela de códigos passou a sair
  da tela **sem barra de rolagem em lugar nenhum**, porque o corpo da página fica travado
  enquanto ela está aberta. É o mesmo defeito que a janela de exportação já tinha tido em
  29/08, e a segunda implementação divergiu na primeira correção — que é sempre o que acontece.
  Os botões vão no `rodape`, fora da rolagem.
  ⚠️ A checagem mede numa tela de **1440×760**: a altura de 1000 do resto da bateria esconde
  exatamente esta classe de defeito.
  ⚠️ **Continua sem detector.** Nada aqui adivinha quais cadastros são o mesmo abacate: a tela
  guarda o que a pessoa disse. Mesma decisão que removeu a cascata por semelhança.
  ⚠️ E para o duplicado que a fusão RECUSA (já tem movimento no razão), o caminho continua
  sendo o item da nota: vincular com "aprender" grava o de-para, e o estoque entra no principal.
  🔑 **"O estoque sempre entra no principal" é verdade CONDICIONADA, e vale escrever qual.** O
  movimento vai para `nota_itens.id_produto` — o produto que o ITEM aponta —, e quem o decide é
  a cascata. Depois de juntar, ele é o principal: o código do absorvido virou apelido, a coluna
  dele foi zerada e ele ficou inativo, então os passos que filtram `AND ativo` também deixam de
  achá-lo. **Antes** de juntar, não: enquanto o duplicado é um cadastro ativo com aquele código,
  ele é o dono dele, e o estoque entra nele — que é o certo. E nota **já lançada** não se move:
  o razão é append-only, e é justamente por isso que a fusão recusa absorver quem tem movimento.
  ⚠️ Nota importada e ainda NÃO lançada muda de dono na fusão (`nota_itens` está em
  `_REAPONTAVEIS`), então lançá-la depois entra no principal.
  ⚠️ **O apelido NÃO filtra por `ativo`**, ao contrário da coluna: ele É a decisão de alguém,
  gravada para apontar para o principal. A contrapartida é que um principal desativado depois
  continuaria recebendo — aceito, e é o mesmo comportamento do vínculo de nível 1.
  🔑 **E o CATÁLOGO do Omie tinha o mesmo defeito, pela porta do lado** (01/09/2026).
  `importar_catalogo` procurava só pela COLUNA `codigo_omie` — e ao juntar dois cadastros a do
  absorvido é zerada, então o código passa a existir **só como apelido**: a consulta não achava
  nada e um **rascunho novo** era criado. O duplicado renascia na sincronização seguinte,
  desfazendo o trabalho de juntar, e sem ninguém ter feito nada. Ele agora consulta a coluna e
  depois os apelidos.
  ⚠️ **Sem `AND ativo` ali, ao contrário da cascata**: a pergunta do catálogo é "este produto do
  Omie já existe aqui?", e cadastro inativo existe — completá-lo é certo, duplicá-lo não.
  ⚠️ **Fornecedor NOVO com código novo não tem como cair no principal sozinho**, e está certo:
  a cascata tenta o EAN (que resolve quando a nota traz `cEAN` e o principal tem o mesmo) e o
  código no fornecedor; falhando, o item fica PENDENTE com sugestão, e quem reconhece decide —
  vincular com "aprender" grava o de-para e a próxima nota daquele fornecedor entra sozinha.
  Adivinhar por semelhança é o que este projeto removeu.
- **O vínculo entre cadastros é DECLARADO, não detectado** (`services/produtos_vinculo.py`,
  botão **Vincular** na tela do produto, 27/08/2026). O sistema recebe produto por três portas —
  catálogo do Omie (o que se compra), cardápio do PDV (o que se vende) e a mão de quem cadastra —
  e nenhuma chave impede o mesmo produto de existir duas vezes.
  🔑 **Existiu um detector por semelhança de nome, e ele foi REMOVIDO porque errava nos dois
  sentidos.** Não achava `BEB CERV HEINEKEN 350ML` contra `CERVEJA HEINEKEN PILSEN` — o mesmo
  produto, **63,8%** de semelhança — e juntava `CAKE BOARD N19` com `CAKE BOARD N21`, que são
  tamanhos diferentes. **Nenhum piso separa os dois casos, porque a diferença não está no
  texto**: um é a descrição abreviada do fornecedor com o volume, o outro é o nome comercial com
  o estilo. Palpite que vincula sozinho contamina o CMV teórico de todo mês em que o prato foi
  vendido, e ninguém vai procurar ali.
  ⚠️ **`produtos.codigo_pdv`** (migração 035) é o espelho do `codigo_omie`: único, visível e
  editável. **Com os dois preenchidos, o cadastro é o mesmo produto nas duas integrações** — e
  isso se lê na tela, sem abrir o banco.
  ⚠️ **O vínculo do PDV tem DOIS níveis** (`services/pdv/vinculo.py`): a coluna é o código
  PRINCIPAL e `codigos_externos` guarda os **apelidos**. Não é sobra de projeto antigo — na conta
  real, `ENTREGA` tem **quatro** códigos de cardápio apontando para a mesma coisa. Uma coluna
  sozinha guardaria um, e os outros três voltariam a virar rascunho na importação seguinte: o
  duplicado renascendo sozinho, sem ninguém ter feito nada. A resolução é coluna → apelidos, e a
  regra mora num arquivo só.
  ⚠️ **A descrição fica com o nome do lado do OMIE e a curta com o do PDV**, e não é preferência
  estética: são nomes com funções diferentes. O do Omie é o fiscal, o que aparece na nota do
  fornecedor e o que se procura ao conferir uma compra; o do PDV é o que sai no cupom e o que a
  equipe fala. Guardar os dois é o que faz o mesmo cadastro ser reconhecível nas duas pontas.
  ⚠️ **A prévia vem antes do botão** (`GET /produtos/{id}/vincular/previa`): fusão não tem
  desfazer, e quem confirma precisa ver com que nome o produto vai ficar, que campos serão
  completados, quantos itens de venda mudam de dono e — quando não dá — o que exatamente trava.
  🔑 **A direção é decidida pelos FATOS, não pela tela** (`direcao`, 27/08/2026). Antes, abrir o
  cadastro do cardápio e escolher o do Omie levava *"não pode ser absorvido… faça a fusão a partir
  dele"* — uma recusa que já sabia a resposta e ainda exigia refazer o caminho noutra tela. Três
  critérios, nesta ordem:
  1. **história** — só um lado pode ser absorvido, então não há escolha;
  2. **controlar estoque** — o cadastro que controla é o operacional; o do cardápio nasce sem.
     ⚠️ Sem este critério, fundir o do Omie no rascunho do PDV produzia um produto com os dois
     códigos e **sem controlar estoque**: a compra deixaria de entrar no razão, calada, e o saldo
     pararia de existir para aquele item;
  3. **a tela** — empatados os dois acima, manda o contexto de quem está olhando.
  ⚠️ **Inverter calado seria pior que não inverter**: a resposta traz `invertido` e
  `motivo_da_direcao`, e a tela avisa — senão a pessoa confirma achando que o cadastro que abriu
  é o que fica.
  ⚠️ **Só absorve cadastro SEM história, e a lista de travas já foi MAIOR.** Ela barrava nota de
  entrada e vínculo de fornecedor, e isso estava errado: são PONTEIROS, não história — um item de
  nota diz "esta linha é deste produto", e se os dois cadastros são o mesmo produto, a linha muda
  de dono. O sintoma foi um caso real: `AGUA MINERAL C/GAS 600ML PLATINA`, com **zero** movimento
  no razão, recusado por causa de uma nota **não lançada**. Sobraram as travas do que de fato não
  se move: razão, lote, mês fechado, contagem de inventário, produção e ficha própria. Nota
  LANÇADA não escapa — ela gerou movimento, e o razão barra.
  ⚠️ Mudam de dono (`_REAPONTAVEIS`): item de nota, sugestão de produto na nota, fornecedor,
  embalagem, agenda de produção, linha de ficha e componente de combo. **Quatro têm unicidade
  composta com o produto**, e mudar o dono às cegas estouraria o índice — derrubando a fusão
  inteira, não só a linha: quando a gêmea já existe do lado que fica, a do absorvido é descartada.
  ⚠️ Com os DOIS carregando história, a recusa continua — e agora diz isso, em vez de mandar
  fazer ao contrário, que não resolveria nada.
  ⚠️ **Completa o que está em branco, nunca sobrescreve** — mesma regra do importador de
  fornecedores. `_carregar` faz `SELECT p.*` de propósito: enumerar as colunas ali faria a lista
  de campos completáveis viver em dois lugares, e um campo novo entraria na lista e não no
  SELECT. Foi o que aconteceu com `marca` na primeira versão.
  🔑 **A fusão BAIXA do estoque o que foi vendido e nunca saiu** (`baixar_vendas`, ligado por
  padrão). É o motivo de ela existir, e o caso é este:

      PRODUTO PDV    estoque  0   vendas 10
      PRODUTO OMIE   estoque 15   vendas  0
      ao vincular →  estoque  5   vendas 10

  O item do cardápio nasce sem controlar estoque, então as vendas dele nunca tocaram o razão.
  Sem a baixa, o resultado seria "comprou 15, vendeu 10, saldo 15" — e as 10 faltando
  apareceriam na primeira contagem como **ajuste de inventário**, que é justamente onde a
  diferença some sem nome.
  ⚠️ **Não é lançamento retroativo, e é por isso que pode.** A saída entra com a data de HOJE,
  num movimento só, dizendo de onde veio. Datá-la no passado cairia dentro de mês possivelmente
  já fechado.
  ⚠️ O tipo é **`SAIDA_VENDA`, não ajuste**: aquelas unidades foram vendidas mesmo. Como ajuste,
  engordariam a linha do CMV que quer dizer "não sabemos o que houve".
  ⚠️ **A conta é simples porque a trava garante**: só se absorve cadastro SEM movimento no
  razão, então nenhuma venda dele baixou — não há o que separar entre "já baixou" e "não baixou".
  ⚠️ A prévia mostra a quantidade, a prateleira e o **saldo que vai sobrar**, e avisa quando ele
  fica NEGATIVO (o razão aceita, com custo provisório, mas quem confirma tem de ver). Desligar é
  possível e a tela diz o que se perde.
  ⚠️ **Um movimento SÓ, com `origem_tipo = 'VINCULO'`.** Cancelar depois uma daquelas vendas
  antigas não devolve a unidade (o estorno procura `origem_tipo = 'VENDA'`) — aceito de propósito:
  a alternativa seria um movimento por venda antiga, todos com a data de hoje, enchendo o razão de
  linhas que não correspondem a nada que aconteceu naquele dia.
  ⚠️ O item de venda **sem** custo ganha o custo de hoje; o que já tinha congelado não é tocado.
  ⚠️ O absorvido vira **inativo e ARQUIVADO**, com a observação dizendo para onde foi — nunca
  apagado, porque auditoria e histórico continuam apontando para ele.
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
- 🔑 **Preço de venda POR LOJA — e sem migração** (`services/precos.py`, 31/08/2026). O índice
  único já previa os dois donos: `(id_produto, coalesce(id_unidade, 0)) WHERE vigente_ate IS
  NULL`. A regra é **o preço da loja manda; sem ele, vale o da casa** — a mesma forma da reserva
  do custo, o específico primeiro e o geral depois.
  ⚠️ **A queda para o preço da casa é o CASO COMUM, não conveniência**: quem abre a segunda loja
  cobra o mesmo na maioria dos itens, e obrigar a cadastrar duas vezes faria a filial nascer com
  centenas de pratos sem preço — e prato sem preço não vende.
  🔑 **A leitura nem filtrava por loja**: pegava a linha de `vigente_de` mais recente, de quem
  fosse — com um preço da casa e um de loja, o resultado era **arbitrário**. Estava assim em
  SEIS consultas, cada uma com a regra copiada por dentro. Agora ela é escrita uma vez.
  🔑 **E o gravador do cardápio estava errado de origem**: `tabelapreco/get/{filial}` é POR
  FILIAL, e o preço importado nascia como preço DA CASA. Com duas lojas, o valor da filial
  sobrescreveria o da matriz a cada importação — as duas terminariam com um preço só, o da
  última que sincronizou.
  ⚠️ **O formulário do produto grava o da CASA**, de propósito: fazê-lo gravar por loja faria o
  preço da casa nunca ser definido — cada filial teria o seu e nenhuma herdaria nada. O da loja
  tem bloco próprio, e os dois só aparecem separados com mais de uma loja.
  ⚠️ **Apagar não é ZERAR**: limpar devolve o preço da casa; zero diz que ali o prato é de
  graça. São coisas diferentes, e o histórico guarda as duas.
  ⚠️ **Setor continua GLOBAL e local por loja** — decisão registrada, não omissão: setor é
  organização do cardápio (o mesmo prato sai do bar nas duas lojas), local é prateleira física,
  que é de cada uma.
- 🔑 **A loja ganhou cadastro de verdade** (31/08/2026): `/lojas` virou só a LISTA, com botão
  de **Nova loja**; `/lojas/nova` e `/lojas/[id]` compartilham o mesmo formulário — nome,
  apelido, CNPJ, IE, endereço, contato e mesas.
  ⚠️ **O sistema sabia criar loja pela API e não oferecia isso a ninguém**, o que é o mesmo que
  não saber. A tela antiga juntava lista, seleção por clique na linha e o formulão de
  parâmetros embaixo, e trazia um bilhete admitindo o vão: *"cadastro completo da loja entra
  junto com a segunda unidade"*. Ela chegou.
  🔑 **Os parâmetros foram para DENTRO de cada loja**: o endereço passa a guardar a loja — dá
  para voltar, guardar o link e saber de qual se está falando. Mesmo corte de Compras, Vendas,
  Fornecedores e Usuários.
  ⚠️ **A caixa "é a matriz" não se desmarca sozinha**: só uma loja é matriz, e desmarcar a
  atual deixaria a casa sem nenhuma — a matriz é a resposta padrão de quem não escolheu loja.
  Para trocar, marca-se na outra, e o servidor tira daqui.
  ⚠️ **A integração NÃO ficou na tela da loja**, de propósito: ela é por loja, mas mora em
  Integrações, resolvida pelo seletor do topo. Duas portas para a mesma configuração seriam
  duas versões da mesma verdade. A tela de nova loja DIZ isso antes de salvar — quem abre a
  filial esperando que ela já converse com o PDV descobriria o contrário no primeiro dia.
- 🔑 **O seletor de LOJA virou o primeiro `<select>` do documento** (31/08/2026) — e derrubou
  DEZ checagens do navegador assim que existiu a segunda loja. Elas liam `["1","15"]`, os ids
  das lojas, achando que liam os tipos de produto; e `p.select("select", …)` chegaria a
  **trocar a loja no meio do teste**, com a falha aparecendo três telas adiante. Tudo passou a
  ser escopado em **`main select`** — o conteúdo da página, não a casca.
  ⚠️ É a armadilha do "primeiro elemento que casa" outra vez, e a pior versão dela: **some
  enquanto há uma loja só e volta no dia em que a casa abre a filial**.
  ⚠️ **E a filial de teste da suíte tinha ficado ATIVA na base do dono** — a limpeza do fim só
  roda quando a rodada chega lá. Virou `atexit`, que roda mesmo com traceback: mesma lição do
  `preservar_credenciais`.
- 🔑 **Transferência ENTRE LOJAS: dois movimentos ligados, cada um na sua loja** (31/08/2026,
  decisão do dono). `transferir` recebia UMA loja e dois locais: escolhendo um local da outra,
  o razão gravava saída e entrada sob a loja de quem estava na tela — o saldo das duas ficava
  errado e **nada denunciava**. Agora cada lado é lançado na loja do seu próprio local.
  🔑 **O custo ATRAVESSA a fronteira**: a entrada usa o `custo_unitario` que a saída apurou (o
  médio da origem). É isso que faz a origem perder exatamente o valor que o destino ganha.
  ⚠️ **Quem não enxerga a loja não empurra mercadoria para dentro dela** — a transferência toca
  DUAS, e mandar para uma loja que a pessoa não vê seria mexer num estoque que ela não pode nem
  consultar. Validado com o mesmo `ve_unidade`.
  ⚠️ **`/locais?todas_lojas=true` nasceu por causa disso**: o destino pode ser a prateleira da
  outra loja, e `/locais` tinha acabado de passar a filtrar pela atual. O nome da loja vem
  junto, senão a lista mostraria dois "Estoque".
  🔑 **E a remessa ENTRA na apuração como compra do destino e compra negativa da origem.**
  Dentro de uma loja a transferência se anula e por isso nunca contou como compra; entre lojas
  ela NÃO se anula — o destino recebe mercadoria que não comprou (CMV **negativo**) e a origem
  perde mercadoria que não vendeu (CMV inchado). Quem mostrou foi a TELA da rede: a filial que
  só recebeu uma remessa aparecia com **CMV de −R$ 160,00**. Somando de um lado e subtraindo do
  outro, as duas fecham e o total da rede não muda.
  ⚠️ **E isso quebrou a identidade "a soma dos grupos é o CMV do período"** em R$ 1.120,00: o
  relatório por grupo não conhecia a remessa. Ela entrou em TRÊS lugares da consulta — a coluna
  de compras, a expressão do **CMV** (esquecê-la ali manteve a diferença na primeira tentativa)
  e o `HAVING`, senão um grupo cujo único movimento fosse uma remessa sumiria da lista.
  ⚠️ A checagem do CMV da filial tem folga de **um centavo**: o custo unitário tem 6 casas e a
  conta encadeia entrada, saída e estoque — o resíduo é de milionésimos de real.
- 🔑 **A remessa: entre lojas a mercadoria leva TEMPO no caminho, e agora alguém confere na
  chegada** (migração 047, `services/transferencias.py`, tela **Estoque ▸ Remessas entre
  lojas**, 31/08/2026, pedido do dono). Saída e entrada eram gravadas na mesma transação: o
  carro saía hoje e chegava amanhã, e a filial já aparecia com o produto na prateleira. Pior,
  **quem recebia não conferia nada** — chegando menos, a diferença só apareceria na contagem
  seguinte como *ajuste de inventário*, que é exatamente onde a diferença some sem nome.
  🔑 **A decisão difícil não é a tela, é de QUEM É O VALOR no caminho.** Dar baixa no envio e
  entrada só no recebimento faria o valor **desaparecer das duas lojas** nesse intervalo,
  inflando o CMV da origem — um buraco que nenhum relatório explicaria. Por isso **o envio não
  escreve no razão**: a quantidade continua contando no estoque da ORIGEM, marcada como em
  trânsito, e os dois movimentos nascem juntos no recebimento, como sempre nasceram. A
  identidade `inicial + entradas − saídas = final` continua fechando nas duas em qualquer data
  de corte, e o dinheiro nunca fica sem dono.
  ⚠️ **Dentro da MESMA loja nada muda** — prateleira para prateleira alguém carrega a caixa.
  Continua imediata, e `POST /estoque/transferencias` é quem **ramifica**: mesma loja lança na
  hora, lojas diferentes criam a remessa. A frase de sucesso vem do servidor porque as duas
  coisas são diferentes, e escrevê-la no navegador seria repetir a regra lá.
  🔑 **O que não chegou vira PERDA na ORIGEM, não sobra de saldo.** A mercadoria saiu da
  prateleira do mesmo jeito; transferir só o que chegou deixaria a origem com um saldo que ela
  não tem, e a contagem seguinte cobriria o buraco como ajuste anônimo. Como perda ela tem
  nome, dono e uma linha própria no CMV de quem mandou. O recebimento parcial pede o motivo.
  ⚠️ **Nulo e zero são afirmações diferentes** em `qtd_recebida`: nulo é "ainda não conferido"
  (e, no corpo do recebimento, "chegou o que foi mandado" — o caso comum não se digita); zero é
  "conferi e não veio nada".
  ⚠️ **O custo é o do RECEBIMENTO, não o do envio.** A mercadoria foi da origem até chegar,
  então quem responde por ela é o médio da origem no dia em que ela sai de lá. Congelar no
  envio criaria um terceiro número, que não seria nem de quem mandou nem de quem recebeu.
  🔑 **Os dois movimentos apontam UM PARA O OUTRO, não para a remessa** — e isso quase virou um
  defeito calado. `_transferencia_entre_lojas` acha o outro lado com
  `JOIN estoque_movimentos o ON o.id = m.origem_id` para saber se a mercadoria atravessou a
  fronteira; pôr ali o id da remessa faria o JOIN cair num movimento QUALQUER de mesmo número, e
  o CMV das duas lojas passaria a depender de uma coincidência de numeração. Quem liga o
  movimento à remessa é `transferencia_itens`. Pela mesma razão a perda usa
  **`origem_tipo = 'REMESSA'`**: naquele vocabulário `origem_id` é um movimento, e aqui não há
  outro lado.
  ⚠️ **Cancelar não estorna nada, porque nada foi lançado** — é a vantagem silenciosa deste
  desenho, e a frase diz isso: quem cancela espera ter de consertar o razão. Depois de recebida
  não há cancelamento, só estorno dos movimentos.
  🔑 **Quem recebe é o DESTINO, e a pergunta é a LOJA ATUAL — não `ve_unidade`.** A primeira
  versão usou a visibilidade, e o administrador vê todas: com ele a trava **não travava nada**, e
  quem despachou daria entrada na outra loja sem ninguém ter conferido — que é o processo inteiro
  que o recebimento existe para impedir. A loja atual é a do seletor do topo. A frase nomeia a
  loja e manda trocar, senão um 403 seco deixa a pessoa procurando permissão que ela já tem.
  ⚠️ **`estoque.transferencia_receber` é a chave NOVA, não a de enviar** — quem transferia ontem
  continua transferindo e ganha o recebimento de graça. Invertida, o deploy tiraria de todo mundo
  uma coisa que já fazia. Mesma escolha do inventário (045).
  ⚠️ **A lista mostra os DOIS lados da loja atual** — o que ela mandou e o que ela espera.
  Filtrar só pela origem esconderia da filial justamente a remessa que ela precisa receber; a
  etiqueta "a receber" é que separa as duas.
  ⚠️ **O saldo da origem DIZ quanto já está na estrada** (`em_transito` em `/estoque/saldos`).
  Sem isso o "continua contando" vira armadilha: quem olha o saldo da matriz vê mercadoria que
  já está no carro e despacha de novo. Vem de **uma consulta só**, casada em memória — 200 linhas
  por página contra um punhado de remessas abertas, e correlacionar cobraria o preço em toda
  listagem de saldo por causa de um caso que quase sempre vem vazio.
  ⚠️ O item de menu só aparece **com mais de uma loja**: numa casa só, remessa não existe.
- 🔑 **Em que loja cada pessoa trabalha** (31/08/2026, pedido do dono). O escopo por loja
  existe desde o **primeiro script**: `usuario_papeis.id_unidade`, nulo querendo dizer "todas".
  A tela de usuário mandava **sempre nulo**, com o comentário `// com uma loja só é o que faz
  sentido` — e fazia. Assim que a casa abriu a filial, todo mundo passou a enxergar as duas, e
  o `ve_unidade` que protege saldo, venda, inventário, remessa e apuração virou enfeite. É a
  mesma família do cadastro de loja: **o sistema sabia fazer e não oferecia isso a ninguém.**
  ⚠️ **O bloco "Onde trabalha" só aparece com mais de uma loja** — numa casa só a resposta é
  sempre "todas", e o campo seria um a mais para responder sempre igual.
  ⚠️ **As lojas oferecidas são as de QUEM ESTÁ CADASTRANDO** (`eu.unidades`, da sessão), não
  uma chamada a `/unidades` — que exigiria `admin.unidades` de quem só administra usuários. É
  também a lista certa: o servidor recusa dar acesso a loja que quem edita não enxerga, e
  oferecer o que vai levar 403 seria ensinar o erro.
  🔑 **Quem não enxerga a loja não põe ninguém dentro dela** (`_conferir_lojas`). Sem essa
  trava, um administrador escopado à filial criaria um usuário com acesso à matriz — dando a
  outra pessoa um alcance que ele mesmo não tem, que é o caminho clássico para escalar
  privilégio sem tocar em permissão nenhuma.
  🔑 **E ninguém encolhe o próprio alcance** (`_nao_encolher_o_proprio_alcance`): quem se
  lotasse só na filial perderia a matriz de vista — e a trava de cima o impediria de devolvê-la
  a si mesmo, porque ele já não a enxerga. Não é hipótese: é o primeiro erro de quem está
  configurando as lojas e testa em si. Mesma regra do `PUT /auth/me`, onde papel e loja ficam
  de fora.
  ⚠️ Loja **inexistente** estourava na chave estrangeira como 500 e loja **inativa** lotaria
  alguém numa casa fechada — 404 e 400 com frase.
  ⚠️ **A tela grava o produto cartesiano papéis × lojas**, que é como a tabela guarda. O modelo
  permite mais do que o formulário oferece — "Cozinha na matriz e Gerente na filial" —, e por
  isso ele **avisa quando o arranjo guardado é mais fino** (`arranjoMisto`): salvar por cima
  alargaria o acesso da pessoa sem ninguém pedir.
  ⚠️ **Ler o alcance é `any(id_unidade is None)`**, não "o primeiro vínculo": basta UM sem loja
  para valer em todas, e é assim que o servidor lê. `lojasDosVinculos` existe para a tela ler
  igual — duas leituras discordariam sobre o alcance da mesma pessoa.
  ⚠️ E a lista de usuários **de-duplica o papel**: com duas lojas, o mesmo papel vem uma vez por
  loja e a coluna mostrava "Cozinha, Cozinha".
- 🔑 **`localStorage` está VAZIO até alguém mexer no seletor de loja** (31/08/2026), e a tela da
  remessa foi a primeira a DECIDIR com base nele: `Number(unidadeAtual() || 0)` dava **zero**
  para quem nunca trocou de loja — que é a maioria —, e aí nem o botão de receber nem o de
  cancelar apareciam. Quem abrisse a própria remessa não tinha o que fazer com ela. O layout
  disfarçava o buraco porque só usava o valor para MARCAR a opção do `<select>`, com
  `?? eu.unidades[0].id` na frente.
  ⚠️ A resposta mora em `useSessao().unidade` e **espelha `seguranca.unidade_atual` passo a
  passo**: a escolhida no seletor, senão a matriz para quem enxerga todas, senão a de menor id.
  "O primeiro da lista" como reserva NÃO é o padrão do servidor quando a matriz não é a de
  menor id — o seletor mostraria uma loja e o pedido iria para outra.
  ⚠️ Ler `localStorage` no render é seguro **ali** porque `eu` nasce nulo: a primeira pintura do
  cliente é igual à do servidor, e o valor só aparece depois do `/auth/me`.
- 🔑 **O açúcar em vários setores: o local ganhou um SETOR** (migração 051, 01/09/2026, processo
  descrito pelo dono). O fluxo real: o açúcar entra no **Estoque Central**, e de manhã cada
  setor leva um pacote para o seu canto — Bar, Confeitaria, Cozinha, Cafeteria. Durante a
  semana cada um gasta do que pegou; no fim, **cada setor conta o seu estoque**.
  🔑 **O que ele chama de "setor" nesse fluxo é, no vocabulário do sistema, um LOCAL** — o teste
  é o comportamento: guarda mercadoria, recebe transferência e é contado num inventário próprio.
  Modelando assim, a transferência da manhã, o inventário por setor e o saldo por setor
  funcionam com o que **já existe** — e o "um produto pode ter vários setores" deixa de ser
  problema: ele não precisa de vários setores, ele tem **saldo em vários locais**
  (`estoque_saldos` é por local).
  ⚠️ **NULO é resposta legítima e é o padrão**: o Estoque Central não pertence a setor nenhum,
  ele serve a todos. Exigir setor em todo local obrigaria a inventar um para a despensa, e setor
  inventado suja o relatório que a coluna existe para melhorar.
  ⚠️ `ON DELETE SET NULL`: apagar um setor não pode levar junto a prateleira, que guarda saldo e
  razão. Perder a classificação é o custo certo; perder o local, não.
  🔑 **A produção passou a sair de ONDE SE PRODUZ** (`estoque._de_onde_sai`). Sem isso, o pacote
  que a Confeitaria pegou de manhã nunca baixava, e a contagem do fim da semana acusava uma
  sobra que não existe.
  ⚠️ **Mas só quando há saldo lá** — e a reserva não é conveniência. A regra anterior (cada
  insumo sai do local DELE) existe por um caso igualmente real: uma receita usa leite da câmara
  e café do seco ao mesmo tempo. Forçar tudo no local de quem produz faria a saída bater num
  lugar por onde o insumo nunca passou, com saldo negativo e **custo provisório contaminando o
  custo do prato** — que é justamente o número que a produção existe para apurar. A ordem é: o
  local de quem produz primeiro, o local do produto como reserva.
  ⚠️ **Pergunta pelo SALDO do dia, não pelo cadastro**: se a Confeitaria tem açúcar, sai de lá;
  se acabou no meio da tarde, sai do central. Decidir pelo cadastro faria a produção falhar
  justamente no dia em que o pacote da manhã acabou.
  ⚠️ **A folha da previsão resolve o local do MESMO jeito.** Prever com outra regra seria prever
  outra coisa: ela diria que falta açúcar no central enquanto a produção o tiraria da
  Confeitaria, e quem lesse iria comprar o que já tem.
  🔑 **`GET /estoque/saldos-agrupados`, e a tela escolhe a granularidade**: prateleira ("onde
  está" — o que quem conta precisa), produto ("quanto a loja tem" — o que quem compra precisa)
  e empresa. Um seletor, não duas caixinhas: duas fariam quatro combinações, duas delas sem
  sentido. ⚠️ O corte por setor ali é pelo setor do **LOCAL**, não pelo do produto — a pergunta
  é "o que a Confeitaria tem na mão", e quem responde é onde a mercadoria está.
  ⚠️ **O CMV por setor continua saindo de `produtos.id_setor`, e isso é uma DÍVIDA conhecida.**
  Com açúcar em quatro setores, todo o consumo de açúcar é atribuído a um só. A ponte para
  consertar já existe (`locais_estoque.id_setor` + `estoque_movimentos.id_local`), mas trocar
  isso reescreve `relatorios.cmv_por_grupo`, cuja identidade — *a soma dos grupos fecha com o
  CMV do período* — a bateria cobra. É entrega própria; ver `docs/o-que-falta.md`.
- ⚠️ **`produtos.id_local_padrao` é UM local, e local pertence a UMA loja** (31/08/2026). A
  produção usava esse local direto, com o `id_unidade` de quem estava produzindo: a filial que
  fizesse um molho cujo local padrão é a câmara da MATRIZ gravaria o movimento com a loja da
  filial e a prateleira da matriz. O saldo tem chave `(loja, local, produto)` — nascia uma
  **linha fantasma**, e o produto ficava num lugar onde ninguém o acha. `_local_desta_loja`
  aceita o local padrão só na loja dona dele; fora dela, cai no principal de quem produz.
  ⚠️ Não é o cadastro que está errado: o local padrão é a resposta certa na loja dele.
- 🔑 **O estoque da EMPRESA: `GET /estoque/saldos-rede`** (01/09/2026, pedido do dono). A tela
  da rede dizia quanto **VALE** o estoque da empresa e não dizia **de quê** — para conferir um
  item era preciso trocar de loja no seletor e somar de cabeça, que é exatamente a conta que a
  visão consolidada existe para evitar. Interruptor **"somar todas as lojas"** na aba de saldos
  de `/estoque`, só com mais de uma loja.
  ⚠️ **A linha vira o PRODUTO e a prateleira sai.** Agrupar por local devolveria a mesma lista
  de sempre, só que mais longa; onde ele está vem em `por_loja`, uma coluna por loja. O filtro
  de local **some** da barra nesse modo — seletor que não corta nada é promessa falsa.
  🔑 **O custo médio da rede é PONDERADO, nunca a média dos médios.** Matriz com 10 kg a R$ 40 e
  filial com 1 kg a R$ 52 dão **R$ 41,09**, não R$ 46 — a média simples daria o mesmo peso ao
  estoque grande e ao pequeno. É a mesma lição do food cost da rede.
  🔑 **Só as lojas que a pessoa ENXERGA entram na soma**, e essa é a trava que mais importa
  aqui: somar uma loja que ela não pode consultar entregaria pelo **total** justamente o que o
  `ve_unidade` esconde — e o total é o pior lugar para vazar, porque nada na tela denuncia um
  número maior do que devia. `smoke_lojas_do_usuario` cobra que quem só vê a filial some só a
  filial, na quantidade **e** no valor.
  ⚠️ **Transferência em trânsito não aparece**: entre lojas ela é movimento INTERNO da rede, a
  mercadoria continua contando na origem e o total não muda. Mostrá-la sugeriria que parte do
  estoque da empresa está fora dela.
  ⚠️ **Traço, não zero**, na coluna de uma loja sem aquele produto: "não tem linha aqui" e "tem
  zero" se leem igual e só o segundo é um saldo.
  ⚠️ **O relatório `saldos-rede` some do catálogo com uma loja só** — ali ele é o de sempre com
  uma coluna a mais, e oferecer os dois lado a lado faria escolher entre duas versões da mesma
  coisa. As lojas visíveis chegam ao montador por `_com_as_lojas`, num parâmetro `_lojas` com
  underscore: é INTERNO, não um filtro que a janela oferece — `exportacao_catalogo` não conhece
  `ve_unidade`, e resolver a lista lá dentro somaria o que a pessoa não pode ver.
  ⚠️ **O total do cartão de saldos somava a PÁGINA e se chamava "valor em estoque"** — a mentira
  que a casa já pagou noutra tela. Agora o rótulo diz qual das duas coisas é: "valor nesta
  página" quando há mais de uma.
  ⚠️ **A rede com ZERO daquele item derrubava a lista INTEIRA com 500.** O custo médio da rede
  é uma divisão pela quantidade — com o saldo zerado ele não existe —, e o modelo de resposta
  exigia `float`. O caminho é o comum (desmarcar "só com saldo"), e o que morria era a resposta
  da PÁGINA, não daquela linha: a tela ficava vazia sem dizer por quê. Agora ele é **nulo**, e
  a tela mostra traço — zero não serve, porque "não custa nada" e "não há nada para custar" se
  leem igual e só o primeiro é um custo.
  🔑 **O painel da rede e a lista consolidada NÃO fechavam, e nada dizia por quê**
  (`GET /estoque/saldos-rede/inativos`, 01/09/2026). Medido na base local: o painel dizia
  R$ 34.893,38 e a lista somava R$ 9.984,88 — **R$ 24.908,50 em 162 produtos INATIVOS que ainda
  têm saldo**. As duas regras estão certas e são antigas: o painel soma `estoque_saldos` inteiro
  (tirar o inativo do estoque final inflaria o CMV) e a lista de saldos filtra por ativo desde
  sempre, aqui e na visão de uma loja só. O que mudou é que passou a existir uma tela que
  **promete explicar** aquele total — e explicava menos de um terço dele. Agora a lista diz
  quanto ficou de fora, com a caixinha para incluí-los; com ela marcada os dois fecham ao
  centavo, e a suíte cobra essa identidade.
  ⚠️ **O aviso segue os MESMOS filtros da lista** — busca, produto e "só com saldo". Número que
  responde por outro recorte é pior que número nenhum: diria "e mais R$ 24 mil" com um produto
  só na tela. Por isso ele é do servidor, não uma conta escrita na tela.
  ⚠️ **E só as lojas que a pessoa enxerga**, como a lista: o aviso é um TOTAL, e total é o pior
  lugar para vazar — nada nele denuncia um número maior do que devia.
  ⚠️ **Endpoint próprio em vez de mais um cabeçalho.** `X-Total` é o padrão da casa para isso,
  mas ele passa por `api.listar`, que serve a TODA lista do sistema: alargar o contrato dele
  por causa de uma tela sairia caro em todas as outras. ⚠️ A mesma divergência existe entre
  `/inicio` e `/estoque` numa loja só — lá continua sem aviso, de propósito, porque ali a lista
  nunca prometeu explicar o painel.
- 🔑 **A visão da REDE** (`GET /inicio/rede` + tela `/rede`, 31/08/2026). Toda outra tela
  responde por UMA loja, e está certo: quem opera opera numa de cada vez. Mas o dono de duas
  não tinha onde ver as duas — e somar de cabeça dois food costs de bases diferentes é a conta
  que ninguém faz certo.
  ⚠️ **Roda a MESMA `apurar` de cada loja, uma por vez** — nunca uma consulta nova que soma
  tudo. Uma segunda implementação divergiria no primeiro caso de borda (ciclo diferente, grupo
  fora do CMV configurado só numa delas), e o consolidado passaria a discordar do painel de
  cada uma. Assim, **se a soma não bate, o erro está numa das partes**.
  🔑 **O food cost da rede se RECALCULA, não se soma**: média de percentuais dá o mesmo peso à
  loja que vendeu R$ 100 mil e à que vendeu R$ 5 mil — e erra justamente para quem tem uma
  grande e uma pequena, que é o caso de quem abre a segunda. A tela diz isso, porque quem
  confere com a calculadora acharia outro número.
  ⚠️ **Cada loja declara o SEU período** (uma pode fechar por semana e a outra por mês), e a
  tela avisa quando eles diferem. ⚠️ Só as lojas que a pessoa ENXERGA entram, e sem
  `cmv.painel` a tela não abre.
  ⚠️ **O item de menu só aparece com MAIS DE UMA loja** (`soComVariasLojas`): com uma só, a
  visão da rede é o Início repetido, e item de menu que leva a tela redundante ensina a
  ignorar o menu.
- 🔑 **O custo do insumo passou a ser da LOJA** (31/08/2026, primeiro passo da segunda loja).
  `custos.custo_do_insumo` somava `estoque_saldos` inteiro, sem filtrar `id_unidade`: o café que
  a matriz comprou a R$ 40/kg e a filial a R$ 52/kg valia **R$ 45,30 nas duas — e nenhuma pagou
  isso**. Não ficava contido: alimenta a ficha, o custo **CONGELADO** do item de venda e a baixa
  por vínculo, ou seja contaminava ficha, CMV teórico, margem e food cost das duas ao mesmo
  tempo. E era silencioso — nenhum valor ficava absurdo, só errado, e gravado.
  A loja atravessa agora `custo_do_insumo` → `custo_da_ficha` (e as sub-fichas) → 
  `custo_teorico_do_produto` → `kits.custo`. Quem GRAVA passa a loja: importação de venda,
  reconciliação do cardápio, baixa do Vincular e previsão de produção.
  ⚠️ **Sem `id_unidade` a conta continua sendo a da REDE, e é proposital**: há caminhos que
  perguntam o custo fora de uma operação de loja — prévia de ficha, relatório consolidado — e
  para eles a média geral é a melhor resposta disponível.
  ⚠️ **A reserva é o último preço do FORNECEDOR, e ela é da rede** (decisão do dono): preço
  negociado vale para as duas lojas, e é o que deixa a filial nova calcular ficha e CMV antes de
  ter recebido o insumo. Cair no médio da OUTRA loja seria voltar a misturar o que o filtro
  separa, e sem dizer que misturou.
  🔑 **A loja nova nasce com um LOCAL, principal.** Sem local nada se movimenta, e a mensagem
  era "Local não encontrado", que não diz o que fazer. O nome é genérico ("Estoque") de
  propósito: é para ser renomeado, não para fingir que se sabe como a casa chama a prateleira.
  🔑 **E `/locais` não filtrava por loja** — filtrava por "o que a pessoa pode VER"
  (`ve_unidade`), que para quem enxerga todas devolve tudo. Assim que a filial existiu, o
  administrador passou a ver os locais das duas na mesma lista, **com dois "Estoque" marcados
  como principal**, e SETE checagens caíram em quatro suítes. Elas estavam certas: a segunda
  loja provou. ⚠️ Mesma correção que vendas e inventários já precisaram — **toda lista de coisa
  que tem `id_unidade` nasce com essa dívida**.
- 🔑 **A logo sumia a cada deploy, e agora mora no BANCO** (migração 046, 31/08/2026). O
  filesystem do App Platform é EFÊMERO: `api/uploads/` some a cada publicação. O risco estava
  anotado desde o preparo da subida, com o Spaces como saída — mas para UMA imagem de até 2 MB
  o banco é a resposta mais honesta: ele já sobrevive ao deploy, já entra no backup do roteiro,
  e não pede bucket, chave nem segredo. **Este projeto já perdeu duas credenciais guardadas; a
  melhor credencial é a que não existe.**
  ⚠️ **Quem chama continua recebendo uma URL** e não sabe de onde ela vem — foi para isso que
  `api/arquivos.py` existe desde o começo, e é por isso que a troca coube em cinco pontos.
  ⚠️ **O `StaticFiles` virou rota, e ela é PÚBLICA como o estático era**: a logo aparece no topo
  de toda tela e no cabeçalho dos PDFs, e a `<img>` do navegador não manda cabeçalho de
  autenticação. O nome tem sufixo aleatório, então a URL não é adivinhável.
  ⚠️ **Cache de um ano, e é seguro PORQUE o nome muda a cada envio** — sem isso seria uma
  consulta ao banco por tela aberta. E `_nome_da_url` recusa `..`, subpasta e prefixo de fora.
  ⚠️ **O PDF recebe os BYTES**, não um caminho: ele DESENHA a logo, não a busca por HTTP.
  ⚠️ **A limpeza da versão anterior é na MESMA transação** da gravação: falhando, a antiga
  continua valendo. ⚠️ E no dia do deploy a logo **não migra sozinha** — ela já não existe no
  disco do servidor; é reenviar uma vez.
  ⚠️ No dia em que houver foto de produto ou anexo de nota — arquivo grande, muitos, servidos
  direto —, o Spaces volta a ser a resposta, e é só `arquivos.py` que muda.
- ⚠️ **Três checagens caíram no dia 31, e duas pela MESMA causa: corte no topo** (31/08/2026).
  1. O rótulo da apuração exigia as duas pontas ("01/08 a 31/08") porque o mês estaria em
     curso — mas **no último dia do mês o recorte É o mês inteiro**, e o nome curto está certo.
     O teste envelhecia todo fim de mês, longe de qualquer commit.
  2. e 3. `/vendas/sem-vinculo` devolve **os 100 de maior receita**, e o item fantasma de R$ 10
     das suítes saiu do topo assim que a base ganhou venda de verdade. É a lição do ranking de
     margem outra vez: **relatório cortado no topo esconde o registro que se procura**, e "não
     achei" lê como "já foi resolvido". A fila ganhou **busca** por código ou descrição — não
     para o teste: com 100 pendências, achar a que se quer resolver é o que uma pessoa faz.
- 🔑 **Contar e MONTAR a contagem viraram permissões diferentes** (migração 045, 30/08/2026).
  `estoque.inventario` dava as duas coisas: quem ia à prateleira contar podia abrir contagem
  nova, escolher o recorte e cancelar a dos outros. A chave nova é **`estoque.inventario_criar`**
  (abrir, configurar, renomear, cancelar); a antiga ficou sendo **contar**.
  ⚠️ **A chave NOVA é a de criar, não a de contar** — e a escolha não é estética. Invertê-la
  faria todo mundo que hoje conta parar de contar no instante do deploy, até alguém
  reconfigurar os papéis. A migração dá a chave nova a quem já tinha a antiga: **ninguém perde
  o que já fazia**.
  🔑 **E cada contagem diz quem conta** (`inventario_contadores`). ⚠️ **Lista vazia quer dizer
  "qualquer um com a permissão"** — é o comportamento de sempre, e é o que faz as contagens
  antigas continuarem valendo sem ninguém reconfigurar nada.
  ⚠️ **Não é permissão, é ESCALA.** A permissão diz o que a pessoa sabe fazer; a lista diz quem
  está no turno de hoje. Misturar as duas obrigaria a mexer em papel toda vez que a equipe do
  dia mudasse — e a desfazer amanhã. Quem pode CRIAR passa por cima da escala: ficar de fora da
  própria contagem seria trava sem propósito.
  ⚠️ **Quem só conta VÊ só o que pode contar.** Mostrar a lista inteira seria oferecer contagens
  que a pessoa abre e não consegue preencher — o 403 chegaria no primeiro número digitado,
  depois da caminhada até a prateleira. E a escala aparece no cabeçalho da contagem, para quem
  não consegue digitar saber por quê sem perguntar a ninguém.
  ⚠️ **A listagem de inventários não filtrava por LOJA** — com duas, a contagem de uma
  apareceria na tela da outra. Mesma correção que a de vendas já precisou.
  ⚠️ **E a checagem da "contagem cega" pegava a ÚLTIMA caixinha da página** — o cartão novo
  "Quem vai contar" passou a ter caixinhas depois dela, e o teste media a escala de uma pessoa.
  Achar por RÓTULO, nunca por posição: é a armadilha do "primeiro elemento que casa", pela
  outra ponta.
- 📄 **O estudo da SEGUNDA LOJA está em [`docs/segunda-loja.md`](docs/segunda-loja.md)**
  (30/08/2026), com a ordem aprovada. 🔑 O achado que manda: **`custos.custo_do_insumo` faz a
  média de `estoque_saldos` sem filtrar `id_unidade`** — com duas lojas, o insumo que uma
  comprou a R$ 40 e a outra a R$ 52 passa a valer R$ 45,30 nas duas, contaminando ficha, CMV
  teórico, margem e food cost. É silencioso, e o custo do item de venda é CONGELADO: o erro
  fica gravado. Também não há transferência entre lojas, e a loja nova nasce sem local.
- 🔑 **A busca de vendas passou a trazer os CADASTROS junto** (migração 048,
  `cardapio.sincronizar_cadastros`, 01/09/2026, pedido do dono). Prato que nasce no PDV é
  cadastrado aqui; prato desligado lá é desativado aqui. E o cadastro vem **antes** da venda,
  de propósito: prato criado hoje e vendido hoje entraria como item sem vínculo e sem custo,
  esperando alguém percorrer a fila.
  🔑 **Mas só CRIAR e DESATIVAR — nunca alinhar** (`importar(alinhar=False)`). O alinhamento
  (nome curto, categoria, setor, unidade, NCM, CEST, EAN, preço) continua sendo o botão
  "Importar cardápio", e a razão é a que já estava escrita no código: *o que evita o ping-pong
  é ser MANUAL*. Rodá-lo sozinho, de hora em hora, desfaria **calada** a correção de quem
  arrumou a categoria de um prato à mão. Separar em duas o que era uma função só é o que deixa
  a sincronização automática existir sem reverter a decisão de 30/08.
  ⚠️ **`ativo` é o único campo que a sincronização automática escreve**, e é o que se pediu:
  ninguém corrige `ativo` à mão esperando que ele fique — produto desligado no cardápio tem de
  sumir das listas daqui.
  ⚠️ **Nada é desativado por AUSÊNCIA.** Só o item que vier com a situação desligada. Sumir da
  lista é ambíguo: `getlistaresumida` já devolveu 570 de 630 sem avisar que faltavam sessenta,
  e uma leitura truncada desativaria dezenas de pratos de uma vez — derrubando o vínculo das
  vendas que chegassem depois.
  🔑 **Na agenda, UMA VEZ POR DIA** (`integracoes.cardapio_em`). A busca de vendas pode ser
  HORÁRIA, e ler os 630 itens 24 vezes por dia para achar um prato novo é caro sem ser mais
  útil: prato novo não nasce de hora em hora. O botão "Buscar no PDV" sincroniza **sempre** —
  ali é alguém pedindo.
  ⚠️ **Relógio PRÓPRIO, não `ultima_sincronizacao`** — aquela é o relógio das VENDAS e avança a
  cada busca. Mesma lição do `agenda_rodou_em`.
  ⚠️ **Falhar o cadastro NÃO impede a busca de vendas**, e a ordem é essa de propósito: venda
  não importada é receita faltando no CMV; cadastro não sincronizado é um item que fica na fila
  mais um dia. Derrubar a segunda por causa da primeira trocaria um problema pequeno por um
  grande. O erro viaja na resposta, em `cadastros.erro`.
  ⚠️ **O preço nem é PEDIDO no modo desligado**: `tabelapreco/get` é uma chamada a mais, e ele
  não seria gravado — pedir seria gastar requisição para jogar fora.
  ⚠️ E o número dos cadastros entra na frase só quando **aconteceu** alguma coisa: "0 produto
  novo" em toda busca é ruído, e ruído esconde o dia em que o número não é zero.
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
- 🔑 **Nem toda rota do PDV responde um OBJETO — e isso derrubava o envio DEPOIS de gravar**
  (30/08/2026). `impressoras/update` devolve a STRING `"Registry updated successfully!"`, como
  o `delete` já fazia. O router fazia `resposta.get("id")` e levantava `AttributeError`:
  **500 com corpo vazio**, a alteração já feita do outro lado, a pendência continuando aberta
  e a tela só sabendo dizer que falhou. Clicar de novo repetia o ciclo.
  ⚠️ A nota da string já existia para o `delete` e o cliente HTTP já a tolerava — quem supunha
  o dicionário era o router, um lugar só, que a nota não alcançou.
- 🔑 **O código do PDV não voltava para o produto** (30/08/2026). O router gravava `codigo_pdv`
  só para SETOR. O primeiro cadastro real foi criado lá (10735980) e ficou com o campo nulo
  aqui; o que segurou a fila foi o `codRefExterna` gravado do outro lado — mas ele é a REDE,
  não o vínculo: `codigo_pdv` é o que a tela mostra, o que o `enviar_preco` usa e o que
  sobrevive a alguém limpar o campo externo lá.
- 🔑 **`produtos/save` NÃO cria a linha de `tabelapreco` — medido** (30/08/2026): 631 produtos
  no cardápio para **630** linhas de preço. O produto criado pelo Botané nasce **sem preço e
  sem tributação** (CFOP, CSOSN, CST e `codICMS_ISS` vazios), e com `validarImpostos = true`
  em todos os 630 é provável que ele trave no caixa. `tabelapreco/save` existe no catálogo —
  criar essa linha é a decisão fiscal que ficou para depois.
  ⚠️ **São CINCO campos fiscais obrigatórios na prática, não três**, e eles moram na linha de
  PREÇO: `codCFOP` (5102), `codCSOSN` (102/103), `codCST` (00), `codICMS_ISS` (5) e
  `codPisCofins` — este preenchido em **630 de 630**, o único que existe até no produto sem
  CFOP. No cadastro do produto há só `codigoNCM`, `codigoCest` e `origem`.
- ⚠️ **Desativar no PDV NÃO volta para o Botané, em nenhum dos três.** A importação do cardápio
  completa apenas `id_categoria`, `id_setor`, `ncm`, `codigo_barras` e `um_estoque` — **`ativo`
  não está na lista**, e o `status` de lá só é usado quando o produto NASCE aqui. Categoria e
  setor a importação apenas cria. **Nome alterado no PDV também não volta**, pela mesma regra.
  ⚠️ E a assimetria é deliberada: desativar AQUI tira do PDV (produto), porque o que autoriza
  mexer no `status` de lá é a PENDÊNCIA — uma mudança feita neste sistema.
  ⚠️ **Setor não tem como ser desativado**: o modelo da impressora é `{codigo, nome, kds}` e
  mais nada. Por isso a tela diz "fora da integração", não "desativada".
- 🔑 **A lista das tabelas de apoio abre com o que está EM USO** (30/08/2026), com a caixinha
  "mostrar inativos" de Produtos. O inativo aparecia junto, só com opacidade baixa — e numa
  base com histórico ele é a maioria. ⚠️ O corte é do SERVIDOR: os quatro endpoints já tinham
  o parâmetro, e o padrão deles sempre foi "só os ativos" — era a TELA que pedia todos.
- ⚠️ **Editar `api/` com o `--reload` ligado derruba a requisição de quem está usando o
  sistema** — e o navegador só sabe dizer "Failed to fetch". Aconteceu duas vezes com o dono
  no meio de um envio ao PDV. Vale igual para rodar suíte de API enquanto alguém cadastra: ela
  escreve na MESMA base local, e deixou 13 produtos, 2 setores, 4 categorias e 14 pendências
  órfãs no cadastro real dele.
- 🔑 **A casca do sistema: barra superior, menu do usuário e rodapé com a VERSÃO**
  (30/08/2026). A marca à esquerda e, embaixo dela, em que LOJA se está — pequeno. À
  direita, o nome de quem entrou vira o controle, abrindo **Alertas · Ajuda · Perfil ·
  Alterar senha · Sair**.
  🔑 **O bloco do usuário saiu do pé do menu lateral.** Lá era texto com dois botões
  pequenos, e no celular — onde a gaveta nasce fechada — sair do sistema exigia abrir o
  menu e rolar até o fim. Canto superior direito é a convenção que a pessoa já traz.
  ⚠️ **A loja é legenda da EMPRESA, não item de menu**: no menu ela tinha o tamanho de um
  rótulo de seção e, no celular, só aparecia com a gaveta aberta — quem tem duas lojas não
  via em qual estava. Com mais de uma, o seletor fica no mesmo lugar onde a legenda estaria.
  ⚠️ **Alertas e Ajuda saíram do menu lateral**: são de QUEM está usando, não assunto do
  sistema como estoque ou compras. E o grupo "Operação" acabou — sobrando só o Início, o
  cabeçalho de grupo custava um clique para chegar à primeira tela. O Início virou item de
  PRIMEIRO nível e usa a tinta dos títulos de grupo; sem chevron, porque não abre nada.
  🔑 **A versão sai do `GET /saude`, nunca de constante compilada no front.** Uma constante
  diz o que foi COMPILADO; esta diz o que está NO AR — e é justamente quando os dois
  discordam que alguém precisa do número. Mesma razão da `impressao`. **`1.1.xx`: o `xx`
  conta PROMOÇÕES**, não commits — é o número que a pessoa lê no rodapé e repete ao pedir
  ajuda. Subir a `VERSAO` em `api/main.py` virou passo do roteiro em `docs/deploy.md`.
  ⚠️ **Falha ao ler a versão não mostra nada** — nem "erro", nem "—": o rodapé é decoração
  informativa, e um aviso ali assustaria por algo que não impede nada.
  🔑 **`PUT /auth/me`** (nome e telefone) **não exige permissão de administrador, e não
  pode**: todo mundo que entra tem um cadastro, e quem digitou o próprio nome errado não vai
  abrir chamado. O que protege é o ESCOPO — o `id` vem do TOKEN, nunca do corpo.
  ⚠️ **E-mail fica FORA**: é a identidade de quem entra, e trocá-lo derrubaria o login da
  própria pessoa no instante seguinte. Papel e loja idem — quem se dá permissão não tem
  permissão nenhuma.
  🔑 **Entrar RECOLHE o menu**, e o padrão passou a ser recolhido para todos os grupos —
  inclusive o da tela aberta, que se expandia sozinho. O efeito era um menu que ia abrindo
  grupos conforme se navegava até não caber na altura da tela. Quem diz "você está aqui" é a
  cor do título. O `login` limpa `botane.menu`: a preferência é da SESSÃO de trabalho, não
  da máquina.
  🔑 **O menu era SERIF.** `font-corpo` (Newsreader) é a fonte do texto que se LÊ; navegação
  se percorre com o olho, item a item. E metade dele já estava certa sem ninguém notar: o
  `<button>` do grupo pegava a `font-display` pela regra de base, o `<a>` do item não — duas
  fontes na mesma lista. ⚠️ `.menu-grupo`, `.menu-item` e `.menu-raiz` vão em
  `@layer components` porque definem `display` (a mesma nota do `.campo`).
  ⚠️ **Item ativo é pílula COM BARRA à esquerda** (`::before`, para não empurrar o texto):
  só o fundo se perdia entre seis títulos de grupo recolhidos.
- 🔑 **4px de raio é canto vivo disfarçado** (30/08/2026). A tela é feita de caixas, e num
  raio tão curto nenhuma tem forma perceptível — só borda. `.cartao` foi para **14px** com
  **sombra dupla**: uma linha de 1px logo abaixo, que separa do papel, e um halo largo e
  claríssimo, que dá a altura. Sombra única e escura é o que faz uma tela parecer de 2012.
  Botão e campo foram para 9px — canto vivo dentro de cartão redondo são duas linguagens na
  mesma tela, e a mais dura é a que se nota.
  🔑 **E o aviso não era um balão, era uma LINHA**: barra de 2px à esquerda com o texto solto
  no fundo da página, lendo como mais um parágrafo com a cor trocada. Virou `.aviso` +
  `.aviso-{info,ok,erro}` — fundo tingido, borda da mesma família, 12px de canto. Entraram os
  tokens que faltavam (`--color-erro-claro`, `--color-alerta-claro`); o `erva-claro` já
  existia e servia só ao verde. ⚠️ A forma mora no CSS, não em oito utilitárias repetidas no
  componente: o aviso aparece em quase toda tela, e um balão diferente por página seria a
  primeira coisa a divergir.
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
- 🔑 **Apagar uma categoria aqui poderia DUPLICAR o cardápio do cliente** (30/08/2026). O
  `codRefExterna` do grupo aponta para o id da nossa categoria; sem ela, o grupo sumia do
  `por_ref` (ninguém o reivindica) **e** do `por_nome` (que só recebe grupo sem dono) — e a
  categoria recadastrada com o MESMO nome não achava nada dos dois lados: a fila proporia
  **CRIAR**, e o botão Enviar criaria 30 grupos repetidos. Bastava apagar UMA categoria.
  Agora grupo de dono inexistente volta a ser adotável pelo nome, e a fixture tem um grupo
  órfão para a suíte cobrar isso sempre.
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
- ⚠️ **Comparar a tela FILTRADA com a API inteira acusa de defeito o comportamento certo.**
  A checagem do aviso "quanto ficou de fora por estar inativo" lia o texto com a busca de um
  produto preenchida e o comparava com `/estoque/saldos-rede/inativos` **sem filtro**: a API
  dizia 181 produtos, a tela dizia nada — e ela estava certa, porque o aviso obedece à busca,
  que é exatamente o que ele tem de fazer. Ou se limpa o filtro antes de medir, ou se pergunta
  à API pelo MESMO recorte. É a família do "teste que descreve o estado do dia", pela ponta do
  recorte em vez da do tempo.
- ⚠️ **`elementHandle.click()` também estoura o `protocolTimeout`** — e não só o `p.click`.
  Limpar o campo de busca com `(await p.$(campo)).click()` derrubou a rodada inteira num ponto
  sem defeito nenhum: ele rola o elemento e espera ele ficar estável. Focar de DENTRO do
  documento (`p.evaluate(() => input.focus())`) e seguir com `p.keyboard` faz a mesma coisa sem
  depender de layout.
- ⚠️ **Handle de elemento ENVELHECE, e `p.evaluate(fn, handle)` estoura o `protocolTimeout`.**
  O laço `for (const b of await p.$$("button")) { await p.evaluate(el => el.innerText, b) }`
  derrubou a rodada inteira num ponto sem defeito nenhum — a troca de loja recarrega a página
  (`window.location.reload()`), então os handles colhidos antes já não existem. O texto continua
  sendo o que identifica o botão; a procura é que tem de ser feita **de dentro do documento**,
  num `p.evaluate` só. Mesma família da nota abaixo.
- ⚠️ **Procurar no DOCUMENTO INTEIRO uma string que também mora na casca.** A checagem "a lista
  de lojas só aparece depois de escolher restringir" usava
  `body.innerText.includes(apelido_da_filial)` — e o apelido aparece no **seletor de loja da
  barra superior**, então ela era verdadeira antes de a lista existir e o teste acusava a tela
  de mostrar o que ela não mostrava. Medir pelo **id do elemento** (`#loja-<id>`), que só existe
  onde interessa. É a armadilha do "primeiro elemento que casa" pela outra ponta.
- ⚠️ **Navegar com um parâmetro de URL que a tela não lê mede a tela errada.** A checagem do
  saldo em trânsito abria `/estoque?id_produto=…` — o filtro daquela tela é ESTADO dela, não
  query string, e o teste media a primeira página do cadastro inteiro. Digitar no campo é o
  único caminho que existe de verdade.
- ⚠️ **`p.click` do puppeteer estourou o `protocolTimeout` na barra superior** — ele rola o
  elemento e espera ele ficar estável, e a dança derrubou a rodada inteira num ponto sem
  defeito. Clique de DENTRO do documento (`p.evaluate(... .click())`) faz a mesma coisa sem
  depender de layout. ⚠️ E a tela do Perfil se alcança pelo ENDEREÇO: encenar o clique num
  link que fecha o próprio menu ao ser clicado só acrescenta interação frágil.
- 🔑 **O PRODUTO no envio, e o Botané virando DONO DO PREÇO** (migração 044, 29/08/2026).
  O que sai é **valor, nome, setor e categoria** — decisão do dono, nestas palavras.
  ⚠️ **NENHUM imposto é enviado, e isso é a trava mais importante do arquivo.** Os campos
  fiscais estão preenchidos em **629 de 630** no PDV (CFOP 5102, CSOSN 102, CST 00, PIS/Cofins
  e o objeto da reforma tributária) e o Botané **não tem nenhum deles**. Mandá-los zerados —
  o que um `{**nosso}` faria sozinho — derrubaria a emissão fiscal do cliente. `corpo_do_produto`
  leva descrição, grupo, impressora, unidade, NCM, CEST, EAN e `status`, e nada mais; a suíte
  cobra a AUSÊNCIA dos oito campos fiscais.
  ⚠️ **`produtos/delete` nunca é chamado.** Sair do cardápio é `status: false`.
  🔑 **O preço mora noutra tabela, e por isso são DOIS gatilhos.** Mudar o preço não toca em
  `produtos` — sem o gatilho de `produto_precos`, um envio diria "tudo integrado" com o
  cardápio cobrando o valor velho. Ele é só de **INSERT**: linha nova É a mudança de preço; o
  `UPDATE` de lá só fecha a vigência da anterior. ⚠️ E `NEW.id` ali é o id da LINHA DE PREÇO —
  usá-lo criaria pendência para um produto que não existe, e ela nunca sairia da fila.
  ⚠️ **`enviar_preco` é ler → mudar só `valor` → gravar.** A linha de `tabelapreco` volta como
  veio; qualquer campo não repetido seria apagado, e são os fiscais que moram ali.
  🔑 **Ser dono do preço obriga a PARAR de importá-lo.** `cardapio.importar` deixa de ler
  `tabelapreco` quando `enviar_ao_pdv` está ligado naquela loja — senão os dois sistemas
  brigam: o preço alterado lá volta por cima na sincronização seguinte, o envio o desfaz, e
  `produto_precos`, que existe para responder *"quando o preço subiu?"*, vira ruído de ida e
  volta. ⚠️ Só o PREÇO para de vir: nome, grupo, impressora e NCM continuam sendo importados —
  dono do preço não é dono de tudo.
  ⚠️ **`ativo` ENTRA na regra do produto, ao contrário da categoria.** Lá o campo é sazonal e
  tem donos diferentes; aqui, desativar um produto deve tirá-lo do cardápio. O que impede o
  ping-pong é a **pendência**: é a mudança feita AQUI que autoriza mexer no `status` de LÁ.
  Desativaram no PDV e nada mudou aqui? Não há pendência, e nada é reativado.
  ⚠️ **O casamento é pelo `codigo_pdv`, NUNCA por nome** — é a lição do REDBULL → LIMÃO TAITY,
  e escrevendo ela criaria produto em cima do cadastro errado.
  ⚠️ **Produto INATIVO aqui não NASCE no cardápio** (eram 67, resíduo de suíte): povoar o PDV
  com o que a casa já não vende. E **vínculo perdido não vira cadastro novo** — `codigo_pdv`
  guardado que sumiu do cardápio (137, com nomes de teste) vira `SEM_PAR`, à VISTA na aba
  Integrados e sem ação: criar um segundo cadastro deixaria o código velho apontando para o
  nada e um duplicado no lugar.
  🔑 **18 "PAO DE QUEIJO" quase foram criados no PDV do cliente**, e a causa era do TESTE:
  `_soltar_codigo()` limpava o `codigo_pdv` e deixava `integrado_pdv = true`, então o resíduo
  entrava na fila como CRIAR. Fila derivada tem esta propriedade — lixo de suíte vira proposta
  de escrita no sistema de quem está vendendo. Conferir a fila ANTES de mandar, sempre.
- **`services/kits.py`** (19/08/2026): combo/kit — a linha única do PDV que vale por vários
  produtos. `KIT` já era um tipo previsto em `produtos.tipo` e nunca tinha sido implementado:
  o combo não é produzido (sem ficha) nem estocado (sem custo médio), então entrava no CMV
  teórico **sem custo**. ⚠️ A composição aponta para **produto**, não para ficha (ao
  contrário de `ficha_itens`): ficha é uma VERSÃO, e o combo preso a uma versão continuaria
  calculando pela receita velha depois de a cozinha homologar a nova. Cada componente resolve
  o custo pela regra dele. Componente sem custo **não zera** o combo — o que se sabe entra e a
  origem vira `kit_parcial`, para o buraco aparecer em vez de sumir. Ciclo recusado na
  gravação, com trava de profundidade por segurança (igual às fichas).
- **Movimentação do estoque por produto** (`cmv.movimentacao_por_produto`, migração 018,
  21/08/2026): estoque inicial, entradas, saídas e estoque final de cada produto — a conta que
  EXPLICA o CMV, que é uma linha só. Aba em `/cmv` e planilha em `/exportar/movimentacao.csv`.
  ⚠️ O saldo inicial e o final saem da **fotografia do razão** (`saldo_apos` ×
  `custo_medio_apos`), não de somar entradas menos saídas: a quantidade daria igual e o
  **valor** não, porque o médio muda a cada entrada. ⚠️ Entradas e saídas aqui são **todas**
  (produção, transferência e ajuste inclusive) — a soma que vira CMV continua sendo só a de
  compras; são perguntas diferentes.
- **O fechamento congela a movimentação junto** (`cmv_movimentacao`): fechar o mês trava o
  relatório que explica o número, não só o número. Nome, código, categoria e setor vão
  **gravados** — renomear o produto depois não reescreve mês fechado. ⚠️ O congelado é do MÊS
  INTEIRO: um recorte dentro dele não vem congelado, e a resposta traz `mes_fechado` para a
  tela oferecer o mês completo em vez de deixar mandarem o parcial ao contador.
- **`services/relatorios.py`** (19/08/2026): os dois relatórios do dono. `cmv_por_grupo`
  quebra a MESMA conta do CMV por setor ou categoria — **não é rateio**, e a soma dos grupos
  fecha com o CMV do período (o teste confere isso). Produto sem grupo aparece como "Sem
  setor" em vez de sumir na junção. `evolucao_de_preco` ordena pelo **impacto em reais**, não
  pelo percentual: 8% num item semanal dói mais que 60% num trimestral. Base é o **custo de
  aquisição** (frete dentro), não o valor de tabela.
- **O fechamento tem três ritmos** (`services/periodos.py`, migração 028, 25/08/2026):
  `MENSAL` (o padrão e o de sempre), `SEMANAL` (escolhendo o dia em que a semana fecha) e
  `DIARIO`. A casa que viu a apresentação fecha o CMV toda **semana** — mês é o ritmo do
  contador, e uma variância que só aparece no dia 30 chega tarde para virar decisão. Escolhe-se
  em `parametros.ciclo_fechamento` + `fechamento_dia_semana` (ISO: 1 = segunda, 7 = domingo).
  ⚠️ **A pergunta "que período é este dia?" é feita num lugar só.** O mês estava escrito por
  dentro de quatro: o fechamento, o painel de CMV, a tela inicial e a frase com que o razão
  recusa lançamento. Trocar o ritmo em um deles faria o sistema discordar de si mesmo.
  ⚠️ **`dia_fechamento_cmv` era campo MORTO** — estava na tela de Lojas e ninguém lia. Virou o
  dia em que o mês do CMV COMEÇA: 1 dá o mês do calendário (idêntico ao de antes), 26 dá o
  ciclo 26/07–25/08 de quem fecha junto com o fornecedor. Limitado a 28: dia 30 não existe em
  fevereiro, e período de tamanho variável não compara com o anterior.
  ⚠️ **Período que ainda não terminou não fecha.** A conferência antiga (`competencia > mês
  corrente`) deixava fechar o mês CORRENTE: no dia 25, congelar agosto travava os seis dias que
  ainda iam acontecer. O corte é `fim > hoje`, e não `>=`, porque o dia do fechamento pertence
  ao período que ele encerra — recusar o último dia deixaria a casa sempre um período atrasada.
  ⚠️ **Períodos fechados não se sobrepõem** (409 nomeando o outro): quem fechava por mês e passa
  a fechar por semana teria dois congelados dizendo coisas diferentes sobre os mesmos dias.
  ⚠️ `cmv_fechamentos.ciclo` entra na unicidade (`ux_fechamento_ciclo`) — sem ele a semana que
  começa no dia 1 colidiria com o mês que começa no dia 1, e o `ON CONFLICT` sobrescreveria um
  com o outro em silêncio.
  ⚠️ **O nome do período vem do SERVIDOR** (`periodos.rotulo`), nunca remontado no front: só a
  coluna `ciclo` sabe se "01/08" é o mês de agosto ou a semana que começou nele. E o nome curto
  ("agosto de 2026") só vale para o período INTEIRO — um recorte que para no dia 25 mostra as
  duas pontas, senão manda-se ao contador um pedaço achando que é o mês.
  ⚠️ A tela de Lojas mostra a prévia do calendário **pedindo ao servidor**
  (`GET /unidades/{id}/parametros/previa-fechamento`), com os valores do formulário e sem
  salvar: semana que fecha na quarta, mês que começa no 26 e dia corrido são três aritméticas,
  e uma segunda implementação em TypeScript divergiria no primeiro caso de borda — aparecendo
  como fechamento no período errado, que só se desfaz reabrindo.
- **`UTENSILIO` — "Utensílios"** (migração 037, 27/08/2026), pedido da cliente.
  Prato, talher, taça, panela e avental entravam como INSUMO ou REVENDA e sumiam dentro do
  custo da comida.
  🔑 **O que o separa de EMBALAGEM e MATERIAL_LIMPEZA não é ser "não comida" — os três são. É
  que utensílio NÃO É CONSUMIDO**: marmita sai com o pedido, detergente acaba; uma taça vive
  meses e some num sábado. Ele quebra, some e é REPOSTO. Por isso ganhou grupo próprio no CMV
  em vez de virar apêndice do de limpeza: "quanto se quebrou e se repôs no mês?" não é a mesma
  pergunta que "quanto disto não é comida?".
  ⚠️ **Nasce FORA do CMV real** (`considerar_no_cmv = false`), pelo mesmo motivo do grupo de
  limpeza: taça quebrada não é custo do prato, e o food cost é o percentual que vira decisão de
  cardápio. Como nenhum produto tinha o tipo ainda, **nada no passado muda** — todo mês já
  fechado continua idêntico, e a suíte cobra que comprar utensílio não mova o CMV real.
  ⚠️ **A lista viva é `TIPOS`, em `api/models/produtos.py`** — `cmv_grupos`,
  `inventario_selecao` e o router do CMV a importam, então o tipo se propaga sozinho para
  grupos, filtro de inventário e painel. **Não há CHECK no banco de propósito**: tipo novo é
  migração de dado, não alteração de tabela. Mas são DUAS listas, e a outra é
  `TIPOS_PRODUTO` em `web/lib/cadastros.ts` — mexer só numa faz o servidor aceitar um tipo que
  ninguém consegue escolher (a lição do EAN, na direção inversa: essa não quebra nada, só
  nunca aparece). O `verificar.mjs` passou a contar os tipos do `<select>`.
  ⚠️ **`TIPOS_CATEGORIA` é uma TERCEIRA lista** (`api/models/cadastros.py`), e estava sem
  `MATERIAL_LIMPEZA` desde a 029: a tela oferecia o tipo e o servidor recusava com 422 —
  ninguém tinha tentado criar a categoria ainda. Corrigido junto. Ela espelha `TIPOS` menos
  `KIT`, que não se classifica em categoria de compra.
  ⚠️ Tipo inválido devolve **400 com a lista inteira na frase**, não 422 — "UTENSILIOS" no
  plural é o erro provável, e a resposta mostra a grafia certa.
- **A casa monta os próprios grupos do CMV, por TIPO de produto**
  (`services/cmv_grupos.py`, migração 029, 26/08/2026). O painel já mostrava Perdas, Consumo
  interno e Ajustes de inventário como linhas que EXPLICAM o número; faltava a pergunta que o
  dono faz olhando a nota do mês: **quanto disto não é comida?** Detergente, sacola e marmita
  entram no custo pela mesma porta dos insumos e somem no total. Tipo novo:
  **`MATERIAL_LIMPEZA`**. O grupo de exemplo ("Material de limpeza e embalagem" = EMBALAGEM +
  MATERIAL_LIMPEZA) nasce na migração — funcionalidade que não aparece é funcionalidade que
  ninguém procura —, e é editável e apagável como qualquer outro.
  ⚠️ **Um tipo só entra em UM grupo, e quem garante é o BANCO**: `tipo` é a chave primária de
  `cmv_grupo_tipos`. Conferir só na aplicação deixaria duas telas gravarem ao mesmo tempo — e o
  mesmo custo apareceria em dois grupos, com a soma dos grupos deixando de fechar com o CMV, que
  é justamente a propriedade que dá sentido ao corte (a suíte cobra a identidade).
  ⚠️ **O vínculo é com o TIPO, nunca com o produto.** Mudar a configuração reclassifica o
  passado inteiro sem tocar em cadastro nenhum; gravar o grupo no produto exigiria varrer o
  cadastro a cada mudança e deixaria para trás justamente os produtos antigos, que são os que
  têm histórico.
  ⚠️ **O grupo escolhe se entra no CMV real** (`considerar_no_cmv`, migração 032). Marcado, a
  linha EXPLICA o CMV — como Perdas: o custo já está no total e a linha diz quanto do total é
  aquilo. Desmarcado, o custo **sai da conta**, e é isso que separa comida de detergente no food
  cost, que é o percentual que vira decisão de cardápio.
  ⚠️ **Sair é sair das TRÊS pontas** — estoque inicial, compras e estoque final. Tirar só as
  compras deixaria o estoque de limpeza do começo e do fim na conta, e a diferença entre os dois
  viraria custo de comida do mesmo jeito, com sinal imprevisível. Saindo das três, a
  contribuição do grupo se anula por completo: a suíte cobra que o CMV caia **exatamente** o que
  o grupo valia, e que remarcar devolva o número.
  ⚠️ **O dinheiro NÃO some da tela**: o grupo continua no painel, dito "FORA do CMV real", e um
  aviso acima da conta nomeia o que ficou de fora. Gasto que desaparece da vista é gasto que
  ninguém controla — e quem compara com o mês passado precisa saber que a régua mudou.
  ⚠️ `tipos_fora_do_cmv` viaja na apuração e é uma **lista**: o router converte os valores para
  `float`, e `float(list)` derrubava a apuração inteira com 500. Campo novo que não seja número
  precisa entrar na exceção de `_float`.
  ⚠️ **Grupo configurado aparece no painel mesmo valendo zero**, ao contrário do relatório por
  grupo (que lista o que pesou): ali "não apareceu" é indistinguível de "não salvou". E na ordem
  que a casa definiu, não na do valor — linha que troca de lugar entre um período e outro é
  linha que ninguém acha.
  ⚠️ A conta é a MESMA de `relatorios.cmv_por_grupo` (`agrupar="grupo"`), não uma soma escrita à
  parte: painel e relatório mostram o número lado a lado. Configura-se em **Tabelas de apoio ▸
  Grupos do CMV**, sob a chave `cmv.grupos` — ver o painel e remontar a apuração da casa são
  coisas diferentes, e o Contador tem a primeira.
- **`services/cmv.py`**: `CMV real = estoque inicial + compras − estoque final`. O valor do
  estoque numa data sai do próprio razão (último movimento antes do corte já traz
  `saldo_apos` × `custo_medio_apos`) — não se recalcula série nenhuma.
  ⚠️ **Data de HOJE responde pelo `estoque_saldos`, não pelo razão.** Os dois dão o mesmo
  número (o saldo é a fotografia corrente, e o razão não aceita movimento no futuro), mas o
  caminho é outro: uma linha por produto e local contra um `DISTINCT ON` sobre tudo o que já
  aconteceu. Com 400.000 movimentos, **837 ms viraram zero** — e é o caso mais comum, porque
  todo mês aberto termina hoje. O atalho está em DOIS lugares (`valor_do_estoque` e a CTE
  `final` de `movimentacao_por_produto`) e `smoke_cmv` cobra que continuem concordando.
  Para data passada vale o índice `ix_mov_fotografia` (migração 027): apuração do mês de
  ~1.700 ms para **625 ms**, movimentação do mês aberto de 1.262 ms para **642 ms**.
- **Duas naturezas de produzido** (`produtos.modo_producao`, migração 021, 24/08/2026):
  `PARA_ESTOQUE` (a massa de pizza: produz, guarda, sai depois) e `NA_HORA` (o café passado:
  a venda produz e baixa no mesmo lançamento, e o saldo volta a zero). ⚠️ Sem o `NA_HORA` a
  casa venderia mil cafés e o pó continuaria inteiro no razão — ninguém registra produção de
  café a café. O par entrada/saída fica visível no razão de propósito.
- ⚠️ **Nada de `window.prompt`/`confirm`**: é a caixa do NAVEGADOR — fonte de sistema, botão
  em inglês, sem espaço para explicar o que a ação faz. O que não se desfaz pergunta pelo
  `Confirmacao` de `components/ui.tsx`, e o número que a ação usa fica num campo **na linha**,
  à vista antes do clique. Aplicado em: estornar movimento (razão e ajustes), estornar nota,
  fechar contagem, fechar e reabrir mês, cancelar venda e produzir da agenda.
  ⚠️ **Confirmação só onde mexe no razão ou fecha período.** Lançar a nota NÃO pergunta — a
  tela inteira é a conferência (itens, custos e destinos à vista) e um diálogo no caminho
  comum treina a clicar sem ler. Cancelar linha da agenda também não: é plano, não é razão.
  Cada diálogo diz **o que a ação faz**, não só "tem certeza".
- **A folha da produção** (`/producao/[id]`, `estoque.previsao_producao`): clicar no nome da
  linha abre o que a produção VAI precisar — por unidade, no total, o que existe no local de
  onde vai sair e o que falta. Roda a MESMA conta da produção (rendimento, conversão de
  embalagem, local de cada insumo); prever com outra regra seria prever outra coisa.
  ⚠️ A previsão é sempre de AGORA, nunca a de quando se agendou. ⚠️ Sub-ficha aparece como o
  PRODUTO dela, não explodida — é isso que a produção consome de fato.
  ⚠️ Resolver `id_local` como a produção resolve (cai no principal): sem isso o saldo era
  procurado num local nulo e a folha dizia que faltava tudo.
- ⚠️ **A agenda é lista de TAREFA, não histórico**: linha produzida some dela. O que já foi
  feito aparece em "Produções recentes" — misturar faria a agenda crescer para sempre e
  esconder o que falta no meio do que já foi. `?status=PRODUZIDA` traz o histórico, para
  conferir plano contra realizado.
- **Agenda de produção** (`producao_agenda` + `services/producao_agenda.py`): o PLANO, que
  não mexe no estoque — quem mexe é a produção, quando a linha é cumprida. ⚠️ A quantidade
  produzida pode sair diferente da planejada (a cozinha rendeu outra coisa) e as duas ficam
  registradas. Agendar o mesmo produto no mesmo dia **soma** em vez de duplicar: quem agenda
  de novo aumenta o lote, não abre outra ida ao fogão. Produto `NA_HORA` não se agenda.
  ⚠️ A sugestão repõe até o **máximo**, não até o mínimo — produzir só até o mínimo deixa a
  casa raspando o limite no dia seguinte.
- ⚠️ **O alerta de mínimo se divide em dois**: `estoque.minimo` (compra-se) e
  `producao.agendar` (a casa produz — aponta para a agenda, não para o estoque). Alerta que
  aponta para o lugar errado é alerta que ninguém segue. Há também `producao.atrasada`.
- ⚠️ **A produção baixa cada insumo do local DELE** (`id_local_padrao`), não do local
  informado no lançamento — uma receita usa leite da câmara e café do seco ao mesmo tempo.
  Achado pelo `cenario_cafeteria.py` em 24/08/2026: a saída batia num local sem saldo, o razão
  registrava a baixa por onde o insumo nunca passou (com **custo provisório**) e o saldo do
  lugar certo continuava cheio. O produzido também entra no local dele.
- ⚠️ **`lancar()` devolve `custo_exato` além de `custo_total`.** O razão guarda dinheiro em
  centavos, mas quem ENCADEIA custo (a produção soma consumos para achar o custo do prato)
  precisa do valor sem arredondar: a produção somava 4,48 + 4,98 = 9,46 onde a conta era
  9,455, e o prato nascia a 0,946 em vez de 0,9455 — meio centavo por unidade que reaparece
  multiplicado no CMV teórico.
- **`tests/cenario_cafeteria.py`**: a casa inteira funcionando uma vez, com números conferidos
  no papel (frete rateado, embalagem convertida, médio ponderado, ficha, sub-ficha, produção,
  perda, transferência, inventário, venda e o fechamento das identidades). 57 checagens.
  ⚠️ Mede **delta** da apuração e soma só os produtos do próprio cenário — a base pode ter
  outra coisa.
- ⚠️ **VENDER É SAIR DO ESTOQUE** (24/08/2026): a importação de venda lança `SAIDA_VENDA`
  para todo produto que `controla_estoque` — não só para o `NA_HORA`. Antes, o que era
  PARA_ESTOQUE (ou revenda) continuava na prateleira do sistema depois de vendido: o **CMV
  real saía subestimado** e a primeira contagem cobria o buraco inteiro como "ajuste de
  inventário", que é onde a diferença some sem nome. Cancelar a venda **estorna** os
  movimentos — cancelar sem devolver deixaria o produto fora da prateleira e fora do caixa.
- **`tests/cenario_semana.py`**: a operação de uma semana com um usuário por papel (gerente,
  conferente, cozinha, salão, contador) — quem pode o quê, e a conta fechando no fim. Com a
  baixa da venda no lugar, a **variância = perdas + ajustes** exatamente, e o food cost sai em
  30,6%. Foi ele que achou a falha acima. ⚠️ Mede **delta** da apuração e afirma só sobre os
  produtos que ele mesmo mexeu: a base é compartilhada com as outras suítes.
- **O custo da ficha é congelado no item de venda** (`venda_itens.custo_ficha_unitario`):
  corrigir receita hoje não reescreve o CMV teórico do mês passado.
- Compras contam só `ENTRADA_NF` e `ENTRADA_MANUAL`; produção e transferência são
  transformação interna e se anulam na conta.
- **`services/custos.py` é o único lugar que sabe quanto custa um insumo**: custo médio do
  estoque, com o último preço do fornecedor como reserva. Dinheiro em `Decimal`.
- **FEFO (19/08/2026):** a saída de produto com `controla_lote` **escolhe o lote sozinha** —
  o que vence antes sai antes, quebrando em vários lotes se preciso (`_consumir_fefo`).
  Sem validade fica no fim da fila. ⚠️ **Lote nunca barra a operação**: a soma dos lotes pode
  ser menor que o saldo (o campo é opcional na entrada) e o que falta sai como "sem lote" —
  quem manda no saldo é o razão, lote é camada de controle. ⚠️ O **estorno espelha os lotes do
  movimento original** (`_lotes_espelho`), nunca o FEFO — senão devolveria ao lote errado.
  Antes disso a saída não baixava `estoque_lotes`: o saldo por lote só crescia e **o alerta de
  vencimento mentia**.
- **`services/estoque.py` é a única porta de escrita no razão.** `lancar()` trava a linha de
  saldo (`FOR UPDATE`), calcula o médio e grava a fotografia (`saldo_apos`,
  `custo_medio_apos`). Router nenhum monta INSERT em `estoque_movimentos`.
- **O médio segue a ordem de LANÇAMENTO, não a data do movimento** — data serve ao relatório;
  recalcular por data faria o CMV de ontem mudar sozinho.
- **Recuperação de senha** (19/08/2026): `services/senhas.py` (token de 32 bytes, só o sha256
  no banco, 30 min, **uso único**, pedido novo mata o anterior; redefinir **revoga todas as
  sessões**), `services/email.py` + `routers/email_config.py` (SMTP em `integracoes`, senha
  cifrada e mascarada). ⚠️ A tela pública responde **a mesma frase** para e-mail cadastrado e
  inventado — senão vira verificador de quem trabalha na casa; o motivo real vai só para a
  auditoria. Sem SMTP o sistema **não para**: grava o `.eml` em `api/arquivos/emails/` e o
  admin entrega o link pela tela de Usuários (`POST /usuarios/{id}/recuperar-senha` devolve o
  link — é o único lugar onde ele aparece).
- **PWA instalável** (19/08/2026): `app/manifest.ts`, `public/sw.js`, `app/offline/page.tsx`,
  `components/pwa.tsx` (registro + convite) e `scripts/gerar-icones-pwa.mjs` (roda na mão,
  usa sharp). Regras do service worker que **não se afrouxam**: a API (outra origem) e
  `/api` são ignoradas por completo — cachear serviria o saldo de um usuário para o próximo
  que entrasse no mesmo aparelho; HTML é network-first com a página `/offline` de reserva;
  só `_next/static/*` é cache-first (o nome tem hash). ⚠️ **Em dev o cache de estático é
  desligado** (`/sw.js?dev=1`), senão o HMR do Next serve pedaço velho e vira caça a bug que
  não existe. ⚠️ `apple-mobile-web-app-capable` está declarado à mão em `metadata.other`: o
  Next 16 só emite o nome padronizado, que o Safari entende do iOS 17.4 em diante.
- Testes (1.672 verificações de API): `smoke_fundacao.py` (47, 48 em base virgem), `smoke_cadastros.py` (55),
  `smoke_fichas.py` (50), `smoke_estoque.py` (155), `smoke_cmv.py` (63), `smoke_omie.py` (116),
  `smoke_notas.py` (70), `smoke_senha.py` (40), `smoke_email_prazo.py` (15), `smoke_sessao.py` (17), `smoke_lotes.py` (28),
  `smoke_relatorios.py` (37), `smoke_kits.py` (29), `smoke_conversao.py` (29),
  `smoke_producao.py` (46), `smoke_alertas.py` (28), `smoke_paginacao.py` (25), `smoke_ajustes.py` (48), `smoke_ciclos.py` (32),
  `smoke_grupos_cmv.py` (45), `smoke_utensilios.py` (23), `smoke_inventario_filtros.py` (50),
  `smoke_exportacoes.py` (104), `smoke_produto_do_omie.py` (31), `smoke_agenda_omie.py` (27), `smoke_pdv_legal.py` (155), `smoke_vendas.py` (39), `smoke_vinculo.py` (84),
  `smoke_transferencias.py` (47), `smoke_lojas_do_usuario.py` (26),
  `cenario_cafeteria.py` (57) e `cenario_semana.py` (54); mais
  `web/scripts/testar-sw.mjs` (17, sem navegador) e
  `web/scripts/verificar.mjs` (425, no Chrome, com fotos em `web/scripts/_fotos`).
  Todos idempotentes; os de CMV medem **delta** sobre a apuração anterior, porque o banco
  local já tem dado de outras rodadas.
- ⚠️ **`<select>` alimentado por endpoint paginado é uma lista mentirosa — e MUDA.** O produto
  da ficha vinha de `/produtos?tipo=PRODUZIDO`: eram os 200 primeiros em ordem alfabética.
  Enquanto a casa tinha dezenas de pratos, ninguém notou; ao importar o cardápio do PDV (627
  itens), o prato recém-criado deixou de estar na lista — e o `<select>` não tem como dizer isso.
  A tela ficava certa, o produto simplesmente não estava lá, e o formulário recusava salvar sem
  explicar. Virou `BuscaCadastro`, que é o padrão da casa exatamente para isto. A regra de bolso
  do `<select>` continua valendo — **poucos por natureza** (categoria, setor, local, unidade) —,
  e produto nunca foi disso.
- 🔑 **A suíte pegava "a primeira ficha HOMOLOGADA" e caía numa de produto INATIVO.** Produto
  com movimento vira inativo em vez de sumir, e a ficha dele fica: a base tinha **57** fichas
  homologadas apontando para produto desativado. Agendar produção numa delas devolve 400 "está
  inativo" — e o POST não era conferido, então a agenda ficava vazia e a falha aparecia **três
  checagens adiante**, dizendo que a agenda não abre a folha. Duas correções, e as duas valem
  como regra: **filtrar pelo produto ATIVO** e **conferir o POST que monta a precondição**.
- 🔑 **A lista das TABELAS DE APOIO pagina, e o registro da rodada cai fora da primeira
  página.** "Poucos por natureza" era suposição — a base tem dezenas de setores, e um nome que
  começa com T fica na página 2. A checagem acusava a tela de não oferecer "editar" numa linha
  que ela nem mostrava. A suíte passou a aumentar a página para 100 antes de procurar, que é o
  que uma pessoa faria. ⚠️ E a afirmação "salvar troca o nome sem criar outro registro" passou
  a ser feita pelo SERVIDOR: ela é sobre o ESTADO, não sobre o que cabe na tela.
- ⚠️ **Sono fixo depois de abrir a CONTAGEM derrubou a rodada três vezes num dia** (01/09/2026).
  Os 2,2 s bastavam com dez linhas e pararam de bastar com uma contagem de centenas: a checagem
  media a tela ainda em branco e acusava a contagem de não ter campo nenhum. Virou espera pelo
  campo de digitar. ⚠️ E o passo seguinte fazia `c.focus()` sem guarda: com a tela vazia era
  `Cannot read properties of null`, e a rodada INTEIRA morria ali — **um `checar` que falha
  custa uma linha; uma exceção custa as trezentas checagens seguintes.**
- ⚠️ **Foto de página inteira não pode derrubar a bateria.** `fullPage` estoura o
  `protocolTimeout` do Chrome numa tela longa; aconteceu com o painel de CMV e voltou a acontecer
  quando Integrações ganhou o segundo bloco de agenda — e levou junto as 280 checagens da rodada.
  `foto()` agora cai para a foto da JANELA e avisa; o `protocolTimeout` subiu para 60 s.
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
- ⚠️ **Rodar a suíte de API junto com a de navegador inventa falha.** As duas disputam a mesma
  API local; a de navegador espera tempos fixos, e sob a carga da outra a tela não pinta a
  tempo. Duas checagens do formulário de produto "falharam" assim e passaram sozinhas na
  rodada seguinte — meia hora atrás de um defeito que não existia.
- ⚠️ **"O primeiro elemento que casa" deixa de identificar quando surge o segundo.** O teste da
  agenda do Omie pegava "o primeiro `select` que tem HORARIA"; assim que o PDV ganhou o mesmo
  bloco, passou a depender da ordem do DOM. Cada seção tem `id` (`#agenda-omie`, `#agenda-pdv`) e
  o teste aponta para o dela.
- ⚠️ **Relatório cortado no topo esconde o registro que se procura.** `/cmv/margem` sai ordenado
  por receita e cortado no `limite` (50). Assim que a base ganhou 464 pratos e R$ 187 mil de
  venda real, o prato de R$ 500 de uma suíte saiu do topo — e "não está na lista" leu como
  "margem zero", um bug que não existia. O endpoint ganhou `id_produto`, que responde por UM
  prato sem depender do corte; a suíte pergunta pelo id dela. Vale para todo relatório com
  `LIMIT`: quem quer olhar um item específico precisa de um caminho que não passe pelo ranking.
- ⚠️ **E o contrário também: base ZERADA descobre suíte que vivia de sobra.** Depois de
  `limpar_dados.py`, a fase 8g de `smoke_pdv_legal` caiu — ela conferia que a semelhança vira
  dica na observação do rascunho, mas o rascunho de nome IDÊNTICO criado numa fase anterior fazia
  a cascata parar no passo do nome e nunca chegar na semelhança. Só passava porque uma rodada
  antiga havia deixado a observação lá. Precondição garantida (o rascunho é renomeado e
  desativado antes) em vez de suposta. ⚠️ `web/scripts/base-vazia.mjs` passa pelas 26 telas com a
  base zerada — é o estado que ninguém testa e que o cliente vê no primeiro dia.
- ⚠️ **As suítes têm de sobreviver a uma base com dado REAL, não só a uma base virgem.** Depois
  de importar 37 notas e 2.183 produtos de uma conta de verdade, SEIS checagens quebraram — e
  nenhuma por bug do sistema: pegavam "o primeiro produto que controla estoque" (caiu num
  rascunho sem unidade), "o primeiro item pendente" (caiu numa nota do cliente), buscavam nota
  numa LISTA paginada onde a da fixture não estava mais, ou afirmavam sobre as primeiras linhas
  de um CSV. Regra: **cada suíte procura os registros DELA**, pelo código ou pelo número que
  ela mesma criou, e garante a precondição em vez de supô-la.
  ⚠️ **Vale igual para o teste de TELA, e lá o disfarce é outro**: "o primeiro `select` da
  página". A contagem de inventário tem 257 linhas numa base real, e a primeira é a que a
  ordem alfabética entregar — caiu num rascunho do catálogo do Omie, sem unidade de estoque,
  cujo seletor legitimamente não tem o que oferecer. A checagem acusava a tela de um defeito
  que era do dado. Agora ela acha o cartão pelo NOME do produto daquela rodada (em maiúsculas,
  que é como o gatilho grava) — e o "digitar grava sozinho" escreve nele, em vez de deixar
  contagem em produto de terceiro.
- ⚠️ **Fixture com data fixa envelhece.** As notas simuladas nasceram em 16–20/08/2026 e uma
  semana depois já caíam fora da janela automática da busca — o teste dizia que a importação
  tinha parado. `cliente._aproximar_datas` traz as datas da fixture para a semana de hoje
  mantendo o intervalo entre elas. Vale também para a demonstração: sistema que só mostra nota
  do mês passado parece parado.
- ⚠️ **O teste de navegador põe a integração em `simulado` e devolve o modo no fim.** Depois de
  o dono configurar a conta real, "Buscar no Omie" na suíte sincronizaria 3.670 notas de
  verdade — e a conta bloqueia quem consome demais. Trocar só o MODO não toca na credencial.
  O restauro é registrado em `aoTerminar` e roda no `finally` do roteiro: repor no fim do bloco
  não bastou, porque a suíte estourou no meio uma vez e deixou a integração em `simulado` — a
  busca do dono parou de trazer nota e nada explicava por quê. Mesma lição do
  `preservar_credenciais`.
- ⚠️ **Trabalhar na integração com a conta REAL configurada custa cota.** `POST
  /omie/importar-catalogo` varre os 2.189 produtos do cliente a cada chamada, e o Omie bloqueia
  quem consome demais. Antes de exercitar qualquer coisa do Omie: **conferir o modo** e pôr em
  `simulado` (só o MODO — a credencial fica onde está). Para descobrir que campos uma conta
  devolve de verdade, **uma** chamada com `registros_por_pagina: 1` responde tudo e não custa
  quase nada; adivinhar nome de campo e varrer o catálogo para conferir é o caminho caro.
  `preservar_credenciais()` repõe a linha inteira — credencial, modo e `ativa` —, então suíte
  que o chama devolve o modo sozinha.
- ⚠️ **`preservar_credenciais()` em `tests/comum.py`, registrado no `atexit`.** A suíte do Omie
  grava uma credencial de mentira na MESMA linha onde mora a real, e a API não devolve a chave
  em claro (é a regra que protege o segredo) — então perder a credencial do cliente é
  definitivo. Repor no fim do roteiro não bastava: a suíte estourou no meio uma vez, e foi
  assim que a chave real se perdeu. `atexit` repõe mesmo com traceback.

### Armadilhas já pagas
- ⚠️ **Apagar pasta de rota do Next deixa o cache de dev desalinhado, e a rota-PAI some.**
  Removidas `app/(app)/ajustes/{lote,custo}/`, `/ajustes` passou a devolver **404** enquanto as
  outras telas respondiam 200 — o `.next/dev/server/app/(app)/ajustes/custo/` continuava lá com
  manifesto próprio. Some as sobras em `.next/dev` e dê um `touch` na `page.tsx` (ou reinicie o
  `npm run dev`). ⚠️ A suíte de navegador tinha passado VERDE logo depois da remoção: o
  conflito só apareceu numa recompilação posterior.
- ⚠️ **Suíte de navegador que quebra no MEIO deixa rastro que derruba a próxima.** A limpeza de
  notas roda no fim; uma quebra antes dela deixou uma nota manual órfã, e as rodadas seguintes
  falharam num ponto sem relação nenhuma com a causa. Antes de caçar bug numa suíte que
  começou a falhar sozinha, **procure a sobra da rodada anterior**.
  ⚠️ O perfil do Chrome do `verificar.mjs` agora fica em `web/scripts/_chrome-perfil` — no
  TEMP do C: (que vive no limite nesta máquina) o Chrome falha com erro de PROTOCOLO em pontos
  diferentes a cada rodada, não com "disco cheio", e isso se lê como teste instável.
- 🔑 **O seletor de local oferecia TODOS os locais da casa — 93 numa base real.** O produto
  costuma estar em UM. Escolher o errado não dava erro na hora: numa saída, o razão registrava
  a baixa por um local onde o insumo nunca passou, criando saldo **negativo com custo
  provisório** — o mesmo defeito que a produção já teve. Agora a tela pergunta onde o produto
  tem saldo e oferece só esses, **com a quantidade no rótulo** ("Câmara fria — 12 KG"), o que
  faz a escolha ser consciente em vez de um chute entre nomes de prateleira. Um local só:
  escolhe sozinho.
  ⚠️ **Na ENTRADA a lista continua inteira**, de propósito: a primeira entrada de um produto
  novo não tem saldo em lugar nenhum, e restringir ali impediria de cadastrar o estoque inicial.
  O destino da transferência idem — as duas põem mercadoria onde ela ainda não está.
  ⚠️ **Tirar o seletor não era opção**: produto PODE ter saldo em mais de um local (há casos na
  base), e escolher sozinho ajustaria a prateleira errada em silêncio.
  ⚠️ **Sem saldo em lugar nenhum, a lista volta INTEIRA e o lançamento é PERMITIDO.** Houve
  uma versão que bloqueava com "este produto não tem saldo em nenhum local" — estava errado:
  perda e saída de algo que o sistema acha que é zero são legítimas, o razão aceita e marca o
  custo como provisório. Bloquear obrigaria a inventar uma entrada antes, que é pior: cria uma
  compra que não houve e o custo dela contamina o médio. O acerto de quantidade idem — "a
  prateleira tem 5 e o sistema não tem nada" é justamente o caso em que ele serve, e
  `_saldo_de(exigir=False)` trata a ausência de linha como zero.
  ⚠️ O ajuste de CUSTO continua recusando saldo zero, e não por política: `(novo − atual) × 0`
  é zero. Não há valor a corrigir.
- 🔑 **A tela de Ajustes tem SEIS tipos, e eles se dividem em dois grupos.** Entrada, Saída,
  Perda e Transferência dizem **o que se MOVEU**. Ajuste de estoque e Ajuste de custo declaram
  **a VERDADE** — quanto realmente tem, quanto realmente custa — e o sistema calcula a
  diferença. Pedir a diferença obrigaria a fazer a subtração de cabeça, que é onde o erro entra:
  quem conta lê "12" na etiqueta, não "menos 3".
  🔑 **`estoque.ajuste` ("ajustar saldo fora do inventário") existia desde o script 002 sem
  nenhuma funcionalidade atrás dela** — só era usada pelo estorno. O ajuste de estoque é ela.
  ⚠️ **Ele reusa `AJUSTE_INVENTARIO_ENTRADA/SAIDA`**, e não um tipo novo: é a mesma natureza de
  correção, então cai na linha "Ajustes de inventário" que o painel já mostra. Tipo novo criaria
  uma segunda linha para a mesma coisa.
  ⚠️ **A sobra entra pelo MÉDIO que já existe** (`custo_unitario=None`): item encontrado vale o
  que os outros valem, e assim o acerto de QUANTIDADE não mexe no custo médio — quem faz isso é
  o outro tipo.
  🔑 **Os dois têm efeito OPOSTO no CMV, e é o erro mais fácil de cometer.** Falta de estoque
  baixa o estoque final e o CMV é `inicial + compras − final`: menos estoque, **CMV maior**.
  Já subir o custo aumenta o estoque final: estoque mais caro, **CMV menor**. As duas prévias
  dizem qual dos dois em palavras, e a suíte cobra os dois sinais.
- ⚠️ **O ajuste de custo é MAIS UM TIPO na tela de Ajustes, um produto por vez** — não um
  processo em lote com tela própria. A primeira versão fez lote (`/ajustes/lote`,
  `/ajustes/custo`, item no menu) e o dono pediu igual aos outros quatro: mesma tela, mesma
  forma. O lote saiu; o que ficou do backend é `POST /ajustes/custo` (recebe lista, a tela
  manda uma) e `POST /ajustes/custo/previa`. `ajuste_lotes` continua no banco e recebe um lote
  de UM por ajuste — é o que guarda autor e observação e amarra o movimento por
  `origem_tipo = 'AJUSTE_LOTE'`. **Quantidade tem porta própria e mais antiga**
  (`/estoque/entradas`, `/saidas`, `/transferencias`); o lote de estoque virou código morto e
  foi removido.
  ⚠️ **A prévia é pedida ao SERVIDOR no blur do campo**, não recalculada em TypeScript: seria a
  segunda versão da mesma regra, e as duas divergiriam no primeiro caso de borda.
  ⚠️ O campo de quantidade **some** no tipo custo — mostrá-lo desabilitado sugeriria que alguma
  quantidade se move.
- 🔑 **Movimento de quantidade ZERO some das somas que ramificam por sinal.** O ajuste de custo
  (migração 039) reavalia o estoque sem mover mercadoria: `quantidade = 0`, `custo_total <> 0`.
  A CTE da movimentação ramificava só em `quantidade > 0` e `< 0`, então ele caía em nenhum dos
  dois lados e o valor sumia — enquanto o estoque FINAL, que sai da fotografia do razão, já o
  incluía. A identidade `inicial + entradas − saídas = final` parou de fechar, e a diferença era
  exatamente o reavaliado. **Três suítes caíram de uma vez.** Agora o valor entra pelo SINAL do
  `custo_total` quando a quantidade é zero. ⚠️ A quantidade continua fora (é zero mesmo): a linha
  mostra valor sem unidade, que é literalmente o que aconteceu.
  ⚠️ **O sinal do efeito é contraintuitivo e precisa estar escrito na tela**: subir o custo do
  estoque AUMENTA o estoque final, e o CMV é `inicial + compras − final` — estoque mais caro,
  CMV **menor**. A prévia diz isso em reais antes do botão.
  ⚠️ **Teste de tela que desvia tem de VOLTAR.** As checagens novas navegavam para
  `/ajustes/lote` e `/ajustes/custo` e o bloco seguinte supunha estar em `/ajustes` — a suíte
  morria procurando campos numa página que não os tem, longe da causa.
- ⚠️ **`/estoque/saldos` é paginado, e os dois CENÁRIOS montavam dicionário da primeira página.**
  `cenario_semana` estourou com `StopIteration` e `cenario_cafeteria` passava por sorte — o
  KeyError chegaria na rodada seguinte. Os dois agora pedem `?id_produto=` de cada produto
  DELES (`saldos_de()` no cafeteria).
  ⚠️ **`smoke_conversao` tinha a MESMA doença e ficou de fora daquela correção** — quebrou
  em 29/08/2026, com quatro checagens, na primeira base grande o bastante para empurrar os
  produtos dele para fora da primeira página. E o sintoma engana: a checagem acusa o razão de
  não ter gravado o que gravou. Ao corrigir uma armadilha deste tipo, **procurar todos os
  chamadores**, não só os que estão falhando naquele dia. ⚠️ Pior que o estouro é o caso mudo: a checagem final do
  `cenario_semana` filtrava a página e, vindo vazia, passava sem ter olhado nada.
- 🔑 **A sessão caía no meio do uso, e a causa era o refresh ROTATIVO sem trava no cliente.**
  O antigo morre no instante em que o novo nasce; as telas disparam várias chamadas juntas
  (Integrações pede quatro), então, ao vencer o access, TODAS levavam 401 e todas chamavam
  `renovar()` com o **mesmo** refresh. A primeira rotacionava e revogava, as outras chegavam com
  token morto e caíam no `limparSessao()` — sessão encerrada sem ninguém ter feito nada errado.
  Duas defesas, em camadas diferentes: `renovacaoEmCurso` em `web/lib/api.ts` (uma renovação por
  vez, as demais esperam a MESMA promessa) e `REFRESH_GRACA_SEGUNDOS` no servidor, para o caso
  de duas ABAS — que a trava do front não cobre.
  ⚠️ **A graça vale só para token SUBSTITUÍDO por rotação** (`sessoes.substituida_em`), nunca
  para revogação explícita. A primeira versão olhava só `revogada_em`, que o **logout** também
  preenche: sair da conta deixava o refresh valendo mais 30 s. A suíte pegou. Sair vale na hora,
  sempre — assim como sessão derrubada pelo admin.
- 🔑 **Fechar o navegador não encerrava nada**: o token ia sempre para `localStorage` e o refresh
  valia 30 dias para todo mundo. Agora quem entra escolhe (`manter_conectado` no login):
  desmarcado → `sessionStorage` + refresh de `REFRESH_SESSAO_HORAS`; marcado → `localStorage` +
  os 30 dias de sempre.
  ⚠️ **O padrão é desmarcado**, e o servidor também trata a ausência do campo como sessão curta:
  a opção segura tem de ser a que vale para quem não escolheu — inclusive para cliente antigo.
  ⚠️ **`sessionStorage` é POR ABA**: abrir o sistema numa aba nova pede login de novo. É o preço
  de "fecha quando eu fechar o navegador", e é o que "manter conectado" resolve para quem
  prefere o contrário.
  ⚠️ **A rotação PRESERVA o modo** (`sessoes.persistente`, migração 038). Sem isso, renovar
  promoveria a sessão curta a 30 dias: a escolha da pessoa duraria até a primeira renovação e
  depois sumiria, sem nada avisando.
  ⚠️ **O front esquecer não é segurança.** Quem garante a promessa é a validade curta no
  servidor — token copiado não está preso ao navegador de ninguém.
- 🔑 **Credencial ILEGÍVEL e credencial AUSENTE davam a mesma resposta — e a diferença é tudo.**
  `JWT_SECRET` deriva a chave do Fernet; trocá-lo (ou subir a mesma base noutro ambiente) faz
  `segredos.decifrar` devolver `{}` em silêncio. O envio de e-mail saía com **senha vazia** e o
  servidor respondia *authentication failed* — que manda redigitar a senha, quando o que mudou
  foi a chave do ambiente. Aconteceu na produção em 28/08/2026, com `smtp.titan.email:465`.
  Agora existe `segredos.ilegivel(bruto)`: verdadeiro só quando **há** credencial guardada e a
  chave atual não a abre. `email.enviar` **para antes de conectar** (senão gasta uma tentativa
  de login num serviço que conta tentativa falha) e a tela de Integrações mostra o aviso sem
  precisar tentar enviar. ⚠️ Falso para credencial ausente: não configurar nada é estado normal,
  e avisar sobre ele seria alarme onde não há problema.
  ⚠️ **Vale para Omie e PDV também** — os três usam o mesmo `segredos`. Só o e-mail foi ligado.
- 🔑 **Não dava para saber QUAL commit estava no ar, e isso custou uma ida e volta.** `VERSAO` é
  texto fixo, a lista de rotas só muda quando alguém cria endpoint, e correção de comportamento
  (um prazo de socket) não deixa rastro de fora — era impossível separar *"a correção não
  funcionou"* de *"a correção não foi publicada"*. `GET /saude` agora devolve **`impressao`**
  (hash do próprio código-fonte) e a **última migração aplicada**. O mesmo cálculo roda aqui:
  `cd api && python -c "import impressao; print(impressao.CODIGO)"`.
  ⚠️ **As pontas de linha são normalizadas antes do hash** (`

` → `
`): o repositório é
  clonado com CRLF no Windows e LF no contêiner, e sem isso o mesmo commit daria impressões
  diferentes — a ferramenta feita para responder "é o mesmo código?" responderia sempre "não".
  🔑 **Lista BRANCA, não lista negra.** A primeira versão excluía o que eu sabia nomear e contou
  **136 arquivos aqui contra 2.014 na produção**: o buildpack instala as dependências DENTRO da
  pasta da API, com um nome que ninguém previu, e o hash passou a incluir biblioteca de terceiros
  — comparando outra coisa que não o nosso código, e nunca batendo com o cálculo local. Lista
  negra depende de adivinhar tudo o que pode aparecer; branca só depende de saber o que é meu.
  A suíte cobra um **teto** de arquivos, não só um piso: com piso só, os dois casos passariam.
  ⚠️ **`arquivos/` e `uploads/` ficam de fora**: são dados de operação (o `.eml`, a logo) e mudam
  sozinhos com o uso — dentro do hash, a impressão mudaria sem ninguém ter publicado nada.
- ⚠️ **Falha de e-mail agora vai para o LOG, não só para a tela.** O log da nuvem mostrava
  `POST /email/testar 502` e mais nada — o motivo ia para quem clicou, que quase nunca é quem lê
  o log. O `print` está em `email.entregar`, e não no router, porque são três chamadores e um
  deles é a recuperação de senha, **rota pública**: justamente a que ninguém está olhando quando
  falha. ⚠️ Servidor e porta entram na linha; usuário e senha **nunca**.
- 🔑 **`timeout=` do smtplib é POR OPERAÇÃO, e são quatro — o pior caso era 80 s.** Conectar,
  STARTTLS, autenticar e enviar, 20 s cada. O roteamento do App Platform desiste em ~60 s e
  devolve **504 com página HTML**, então o que chegava na tela não era o erro do SMTP: era o do
  gateway, dizendo nada sobre a causa. Agora `email.entregar` tem **orçamento do envio inteiro**
  (`ORCAMENTO_ENVIO`, 20 s), reposto a cada passo com `s.sock.settimeout(_resta(ate))`.
  ⚠️ **O STARTTLS TROCA o socket** por um embrulhado em TLS — o prazo do anterior não acompanha,
  e sem repor depois dele os passos seguintes voltam a ficar sem prazo nenhum.
  ⚠️ **`settimeout(0)` não é "sem espera", é NÃO BLOQUEANTE** — a operação falha na hora com um
  erro que não parece tempo esgotado. Por isso `_resta` tem piso de 1 s.
  ⚠️ **A frase do erro leva o texto do socket de propósito**, porque é ele que separa as causas:
  *timed out* é pacote descartado (porta bloqueada na saída — o caso comum em nuvem),
  *Connection refused* é servidor ou porta errados, *Name or service not known* é o endereço.
  Sem isso os três viram "não foi possível enviar" e mandam procurar no lugar errado.
  ⚠️ `entregar` foi separado de `enviar` para **não tocar no banco**: dá para exercitar o prazo
  contra um endereço morto sem pôr o SMTP da casa em modo real — rastro que já custou uma
  credencial neste projeto. `smoke_email_prazo.py` usa 192.0.2.1 (TEST-NET-1, RFC 5737), que
  não é roteável: ninguém responde e ninguém recusa, que é exatamente o que a porta bloqueada faz.
  ⚠️ **Ainda pendente**: `enviar(cur, ...)` segura a transação do banco durante toda a conversa
  SMTP, nos três chamadores — inclusive na recuperação de senha, que é **rota pública**. Cada
  pedido prende uma conexão do pool por até 20 s. Ver `docs/o-que-falta.md`.
- 🔑 **`JSON.parse` antes de olhar `r.ok` transforma todo 5xx em erro de sintaxe.** Quem responde
  ao navegador não é só o FastAPI: o roteamento do App Platform responde HTML quando o app está
  reiniciando ou o tempo esgotou, e a tela dizia
  `Unexpected token '<', "<!DOCTYPE "... is not valid JSON` — engolindo o status real. Agora
  `corpoDaResposta` (em `web/lib/api.ts`) lê o corpo sem estourar e devolve frase útil. O
  `baixar()` já fazia certo; `pedir` e `login` não. ⚠️ No `login` era pior: HTML ali lê como
  **senha errada**.
- 🔑 **Apuração e movimentação NÃO respondem a mesma pergunta, e a diferença dormiu até o
  primeiro grupo fora do CMV existir na base.** `cmv.apuracao` desconta do estoque final os
  tipos com `considerar_no_cmv = false`; `cmv.movimentacao_por_produto` **não recebe esse
  filtro** — é relatório de ESTOQUE e mostra tudo, porque taça guardada é estoque mesmo não
  sendo custo de comida. A checagem do `smoke_cmv` comparava os dois crus e passou anos verde:
  a base local não tinha nenhum grupo fora do CMV (a semente da 029 sumiu numa limpeza com
  `--tabelas-de-apoio`, e migração não reexecuta). Assim que a 037 semeou o de utensílios, a
  identidade abriu **exatamente o valor das taças** — e parecia erro de razão.
  ⚠️ **A segunda checagem, a de ONTEM, passava por sorte**: o estoque do dia anterior ainda não
  tinha utensílio. Quebraria sozinha no dia seguinte, longe de qualquer commit — que é o pior
  tipo de teste frágil. As duas agora tiram a parcela fora do CMV dos dois lados.
  ⚠️ **A movimentação não devolve `tipo`** (só `categoria` e `setor`), então o teste casa por
  `id_produto` contra `/produtos?tipo=`. Pôr `tipo` no relatório seria melhor, mas a cópia
  congelada (`cmv_movimentacao`, migração 018) também não tem a coluna: mês fechado ficaria
  sem ela. É migração própria, não efeito colateral de outra coisa.
- ⚠️ **O tamanho mínimo de senha mora em UM lugar**: `SENHA_MINIMA`, em `api/config.py` (hoje
  **6**), espelhado em `web/lib/senha.ts` para o `minLength` do input e a frase da dica. Estava
  escrito oito vezes, e com dois valores: 12 no start e 8 nos formulários — senha aceita na
  criação do administrador era recusada na troca obrigatória do primeiro acesso. A regra de
  verdade é a do servidor; o `minLength` só evita a viagem.
- ⚠️ **Domínio próprio: o certificado sobrevive ao desligamento, o roteamento não.** O sistema
  atende em `sistema.botanedeliecafe.com.br` (CNAME no HostGator → `botane-app-zqokg.
  ondigitalocean.app`; roteamento e certificado na DO). Aplicar um spec **sem o bloco
  `domains:`** desliga o domínio, e o sintoma engana: cadeado verde e **404 em tudo**. Quem
  responde a pergunta é o cabeçalho — `x-do-app-origin` presente quer dizer ligado, ausente
  quer dizer que a borda não sabe para qual app mandar. Por isso o bloco está no
  `.do/app.yaml`. ⚠️ Trocar o **primário** muda o `${APP_URL}` e obriga a **recompilar o
  `web`** no mesmo deploy (`NEXT_PUBLIC_API` é BUILD_TIME). O `.ondigitalocean.app` fica no
  `CORS_ORIGINS` de propósito: é a porta dos fundos no dia em que o DNS quebrar.
  `verificar_deploy.py` agora lê o endereço de dentro do JavaScript compilado e o compara com
  o host conferido — é a única forma de ver essa variável depois do build.
- ⚠️ **Teste de tela que procura "o produto que contém X" cai no produto de outra rodada.**
  Produto com movimento não é apagado, vira INATIVO — então a base acumula um por rodada. O
  `verificar.mjs` clicava no primeiro item cujo nome continha `"Est tela"`, sem o marcador: a
  partir da segunda rodada a entrada de 10 kg ia para o produto de OUTRO teste, o desta ficava
  com saldo zero, e a checagem acusava a tela de não gravar. Duas checagens falhavam de forma
  intermitente e pareciam instabilidade do navegador. Vale a mesma regra das suítes de API:
  **cada teste procura o registro DELE**, pelo nome completo com marca de tempo.
  ⚠️ E `foto(fullPage)` no painel de CMV estoura o tempo do protocolo do Chrome — a página tem
  composição, ABC e margem, todas longas. Fotografar a tela do assunto, não a maior.
- ⚠️ **A fotografia do razão não sobrevive a lançamento retroativo — e não é dos ciclos.**
  `saldo_apos` é calculado na ordem de LANÇAMENTO (decisão certa: por data, o CMV de ontem
  mudaria sozinho). Como o saldo de uma data passada é lido do último movimento antes dela, um
  retroativo gravado hoje entra como "o último" e devolve um saldo que já inclui o que veio
  antes dele na fila. Resultado: `inicial + entradas − saídas = final` abre em recorte que
  termina antes de hoje. No mês inteiro fecha, porque o retroativo e o que ele contamina caem os
  dois dentro da janela — foi por isso que passou anos despercebido, com o mês sendo o único
  período possível. A tela nomeia a causa; o conserto está em `docs/o-que-falta.md`.
  ⚠️ Toda suíte que confere essa identidade tem de **garantir o ritmo MENSAL** antes, não supô-lo.
- ⚠️ **Marcador de configuração vira dado, e dado ruim não avisa.** O `ADMIN_EMAIL` do
  primeiro deploy subiu com o `DEFINA_NO_PAINEL` do `app.yaml` copiado tal e qual: passou pela
  guarda (não era o valor padrão, e a senha tinha 16 caracteres) e criou um administrador
  chamado `defina_no_painel`. A conta nasceu **morta** — `LoginRequest.email` é `EmailStr`, e o
  pedido morre com 422 antes de tocar o banco —, mas o log dizia "administrador criado" como em
  qualquer subida boa, e a única saída foi apagar a linha direto no Postgres. `garantir_admin`
  agora confere o e-mail com a **mesma regra do login** (`pydantic.validate_email`) e recusa o
  marcador como senha. Regra de bolso: **valor de configuração que vira registro no banco
  precisa passar pela validação de quem vai LER esse registro.**
- ⚠️ **`toISOString()` é UTC, e depois das 21h em Brasília ele já diz amanhã.** A tela de
  Vendas propunha a data de amanhã para a importação do dia: um restaurante que fecha às 23h
  lançaria a venda inteira no dia seguinte, o CMV do mês fecharia errado e nada na tela
  denunciaria. Toda data que vira texto `aaaa-mm-dd` no front passa por **`lib/datas.ts`**
  (`hoje`, `diaLocal`, `somarDias`, `somarMeses`, `primeiroDiaDoMes`) — `sv-SE` é o formato
  ISO no fuso de quem está olhando. É a mesma armadilha que o banco resolve com a sessão em
  `America/Sao_Paulo`.
- ⚠️ **Movimento de estoque no FUTURO não existe** (`estoque.lancar`). A trava do período
  fechado olha para trás; para a frente não olhava ninguém, e a data errada acima entrava
  calada — o movimento caía fora do mês e o relatório de movimentação deixava de fechar com o
  saldo. Foi um dia de caça a um erro de cálculo que não existia. O razão é append-only: data
  errada ali não se conserta, só se estorna.
- ⚠️ **Saída com saldo negativo deixa a identidade da movimentação aberta**, e não é erro. A
  saída sai por custo PROVISÓRIO (o último conhecido, ou zero); quando a entrada chega, o médio
  passa a valer para o saldo negativo inteiro e revaloriza o que já tinha saído — uma correção
  legítima que movimento nenhum carrega. Foi por isso que uma entrada de R$ 10 sobre saldo −3
  abriu 30 reais no relatório. A tela nomeia essa causa; a saída é lançar a entrada que faltava.
  ⚠️ Suíte que cria saldo negativo **não pode** lançar entrada nele depois: a base é
  compartilhada, e os cenários que medem a casa inteira acusam a diferença.
- ⚠️ **O rodapé do relatório soma as linhas ARREDONDADAS**, de propósito — o total tem de
  fechar com a coluna que a pessoa confere a mão. Em centenas de produtos isso dá centavos de
  diferença na identidade "inicial + entradas − saídas = final", que **não são erro de razão**.
  A folga acompanha o tamanho do relatório (meio centavo por linha), na tela e nos testes: com
  folga fixa, uma base real acusava "a conta não fecha" toda vez, e alarme que sempre toca
  ninguém escuta.
- ⚠️ **E contagem somada da PÁGINA é a mesma mentira.** A tela de Compras somava `pendentes`
  das notas que tinham vindo na página carregada e chamava aquilo de "a fila da casa inteira" —
  verdade com 37 notas, mentira com 3.670: a pendente cai na página 4 e o botão "Reconciliar"
  simplesmente some, com a pendência continuando lá. A fila vem de `GET /notas/pendencias`, que
  é da casa inteira. Vale para todo número que resume uma lista paginada.
- ⚠️ **Lista sem total é lista mentirosa.** A tela de compras mostrava as 50 notas mais
  recentes de 3.670 e nada dizia que havia mais — a nota do mês passado simplesmente não
  existia. Toda listagem que pode crescer devolve o total em `X-Total` (helper único em
  `api/paginacao.py`) e ganha busca no SERVIDOR.
- ⚠️ **`ON CONFLICT (id_unidade, servico)` não pega linha com `id_unidade` NULL**: no Postgres
  nulos são distintos, então o UPSERT nunca conflita e cada gravação cria outra linha (o SMTP,
  que é da casa toda, sofreu disso). Quem garante a unicidade dessas linhas é o índice parcial
  `ux_integracao_global` (migração 012), e o `ON CONFLICT` precisa **nomeá-lo**:
  `ON CONFLICT (servico) WHERE id_unidade IS NULL`. Toda leitura da configuração global também
  filtra `AND id_unidade IS NULL`.
- ⚠️ **Matar o uvicorn no Windows pode deixar o worker órfão** segurando a 9200 — e o
  processo novo **sobe do mesmo jeito**, sem "address already in use". Os dois respondem
  alternadamente e metade dos pedidos volta do código velho (endpoint novo dando 404 no meio
  de um teste que já tinha passado). Ao reiniciar a API na mão, conferir se sobrou
  `multiprocessing-fork` órfão: `Get-CimInstance Win32_Process -Filter "Name='python.exe'"`.
- **`allowedDevOrigins` no `next.config.mjs`**: sem isso o dev server do Next devolve **403
  nos chunks** quando a página é aberta por `127.0.0.1` (ou pelo IP, no teste em celular).
  A tela renderiza, nunca hidrata, e o formulário vira submit nativo — parece bug de login.
- **`EmailStr` recusa domínio `.local`** (reservado). Por isso o admin é `@botane.com.br`.
- Componente `Aviso` renderiza `<p>`: não colocar dentro de outro `<p>` (erro de hidratação).
- **`localStorage` é do domínio, não da aba**: no teste de navegador, logar como outro
  usuário em qualquer página troca a sessão de todas — voltar como admin antes de seguir.
- Produto, fornecedor e categoria **não são apagados** quando já têm uso: viram inativos.
  Os testes contam com isso (reaproveitam em vez de recriar).
- **Ficha homologada não se edita** (mudaria custo histórico) — só nova versão. Ciclo de
  sub-ficha é recusado na gravação, e o cálculo ainda tem trava de profundidade por segurança.
- **`fichas.custos` filtra o JSON, não só a tela**: sem a chave, nenhum campo de dinheiro
  sai do servidor. Ao mexer no router de fichas, manter isso.
- **Um produto tem UMA unidade de estoque e N de compra** (20/08/2026, migração 015):
  `produto_unidades` (CX=12, FD=6, palete=480). `produtos.um_compra/fator_compra` continuam
  como reserva e são mantidos em dia pela unidade padrão. ⚠️ A ordem em `_fator_do_item`:
  de-para confirmado → **unidade da nota no cadastro** → fator do fornecedor → fator de
  compra. A unidade da nota vem antes do fornecedor porque casa pela UNIDADE; o número do
  fornecedor não diz em que embalagem.
- ⚠️ **A prévia de custo da nota digitada divide pela quantidade EM ESTOQUE**, não pela da
  nota: mostrava R$ 20,60 por caixa onde o custo real era R$ 1,72 por unidade. A tela busca
  o fator em `/produtos/{id}/unidades` e diz "por UN" no número.
- ⚠️ **CX, FD, PCT, BDJ e UN são todas grandeza UNIDADE com fator 1**: a conversão de
  grandeza diria que 1 CX = 1 PCT e engoliria a caixa de 12. `custos.converter()` agora
  **recusa** o par (devolve `None`) quando os dois lados são UNIDADE com o mesmo fator base —
  quem sabe o tamanho da caixa é o cadastro do PRODUTO. Dúzia continua convertendo: o fator
  12 é que separa "unidade de medida" de "nome de embalagem".
- **`custos.converter_para_estoque()` é a única regra de conversão** (20/08/2026):
  mesma unidade → **embalagem do produto** (`produto_unidades`, depois `um_compra/fator_compra`)
  → grandeza → `(None, "desconhecida")`. Ficha, produção e nota de entrada passam **todas** por
  ela. Antes só a nota consultava a embalagem: a mesma caixa valia 12 na entrada e 1 na ficha,
  e a produção baixava 1 pacote onde a receita pedia uma caixa de 12 — some com 11 do razão sem
  ninguém ver. Sem conversão conhecida a ficha **avisa** e a produção **recusa**; 1:1 calado é
  o que não pode acontecer. A ficha devolve `qtd_estoque`/`conversao` por item, e a tela mostra
  "no estoque 12 PCT".
- **O local de estoque é do PRODUTO** (`produtos.id_local_padrao`, migração 017): uma nota traz
  congelado e seco na mesma folha, e um local por NOTA obrigaria a lançar duas vezes ou a
  aceitar o sorvete no estoque seco. O local da nota virou **reserva** — vale para o produto
  que ainda não tem um definido, e a tela da nota mostra o destino item a item antes de lançar
  (`local_destino`). Ordem no lançamento: local do produto → local passado no lançar → local da
  nota.
- ⚠️ **O primeiro local da loja nasce principal** (migração 016), marque-se a caixinha ou não:
  estoque, produção e inventário usam o principal como padrão, e sem nenhum marcado o seletor
  mostrava o nome do local (era o único da lista) enquanto o pedido saía **sem** local — 404
  "Local não encontrado" com o local à vista na tela. As telas também caem para o primeiro
  local quando não há principal. ⚠️ Nenhuma suíte pegou isso porque `garantir_locais` mandava
  `principal: true` — mais cuidado do que quem cadastra "Balcão" tem. O helper parou de mandar.
- ⚠️ **`produto_fornecedor.ultimo_preco` é POR UNIDADE DE ESTOQUE**, não pela embalagem: quem
  grava é o lançamento da nota (o `custo_aquisicao_unitario`, com frete dentro), e
  `custo_do_insumo` lê **sem dividir por fator** — dividir de novo aplicaria a caixa duas vezes
  (12,00 a caixa de 12 virava 0,08 o pacote). O lançamento faz UPSERT: com `UPDATE` só, a
  primeira compra de um insumo não gravava preço nenhum.
- ⚠️ **Salvar o produto pela tela não pode apagar o que a tela não manda**: `_gravar_fornecedores`
  apagava tudo e reinseria, levando junto `ultima_compra` e `ultimo_preco` — e com eles o custo
  de reserva de toda ficha de insumo sem entrada no estoque. Agora só sai da tabela quem saiu
  da lista.
- Item de nota sem produto **não entra no estoque** e barra o lançamento da nota inteira.
- ⚠️ No XML da NF-e, `vFrete` **ausente** e `vFrete` igual a **zero** são coisas diferentes:
  zero é o emitente dizendo "neste item não há frete". Tratar zero como ausente joga o item no
  rateio por valor e cobra dele um frete que a nota não pôs. Se **algum** item traz o campo, o
  rateio é do emitente e os outros recebem zero — senão o frete entraria duas vezes.
- **Fechamento de mês bloqueia lançamento retroativo** — mas quem tem `estoque.retroativo`
  (inclusive o admin) passa. Teste da trava precisa de usuário sem a chave (o Conferente).
- **Movimento de estoque não se apaga**: estorno cria a contrapartida apontando para o
  original. Produto desativado mantém saldo e razão (a lista de saldos filtra por padrão).
- ⚠️ **Parâmetro NULL sem tipo dentro de `COALESCE` estoura no Postgres**: em
  `COALESCE(validade, '9999-12-31') = COALESCE(%s, '9999-12-31')`, um `None` vira `text` e dá
  "operador não existe: date = text". Entrada com lote **sem validade** dava 500 desde a etapa
  4 porque nenhum teste passava por esse caminho. Corrigido com `%s::date`.
- Teste que usa acento ou espaço na query precisa de `urllib.parse.quote` — o urllib recusa.
- `input[type=number]` no Chrome não seleciona conteúdo com `clickCount: 3` — no teste de
  navegador, limpar com ctrl+A, senão o valor entra colado (1 + 8 = 18).

## Stack e portas

| Camada | Escolha | Porta |
|---|---|---|
| Banco | PostgreSQL local (`botane_db`) | 5432 |
| API | FastAPI + psycopg, migrações `.sql` numeradas rodando no start | 9200 |
| Web | Next.js App Router + Tailwind, PWA | 3100 |
| App | Capacitor sobre o mesmo web (fase 8) | — |

Não há deploy: o projeto roda só local nesta primeira parte.

## Regras que valem para todo código deste repositório

1. `estoque_movimentos` é **append-only**. Correção é estorno, nunca `UPDATE`/`DELETE`.
2. Dinheiro e quantidade em `numeric` (custo unitário com 6 casas), **jamais float**.
3. Só o service de estoque escreve no razão, sempre com `SELECT … FOR UPDATE` no saldo.
4. Toda rota declara a permissão que exige; nada de checagem só na tela.
5. Toda tabela de movimento carrega `id_unidade` (multi-loja desde o início).
6. Banco em UTC, sessão em `America/Sao_Paulo`.
7. Ficha técnica é versionada; o custo é congelado no momento do uso.
8. Idempotência de importação é do **banco** (índice único), nunca do gatilho.

## Padrões herdados dos outros projetos da casa

- Migração `.sql` numerada e idempotente, executada no start da API
- Router FastAPI protegido por dependência de permissão; nada de `body: dict` (Pydantic)
- Front com camada de service — nenhuma chamada de API crua dentro da página
- Service worker do PWA **nunca** cacheia `/api`

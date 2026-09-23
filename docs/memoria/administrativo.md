# Administrativo

> Empresa, lojas, parâmetros, integrações e usuários.
> Leia antes de mexer neste módulo.

## O que já existe

- `api/` FastAPI: `database.py` (pool, sessão em America/Sao_Paulo), `db_updater.py`
  (migrações por checksum — **todo script tem de ser idempotente**), `seguranca.py`
  (bcrypt, JWT, refresh rotativo com hash no banco, `requer_permissao`),
  `auditoria.py` (grava no MESMO cursor da operação e filtra senha/credencial).

- `web/` Next.js 16 (App Router): `lib/api.ts` (cliente único, renova o token sozinho),
  `lib/sessao.tsx` (contexto + `pode()`), telas de início, empresa, lojas, usuários, papéis,
  auditoria e troca de senha.

- ⚠️ **Aba padrão escrita à mão abre na aba errada.** Tabelas de apoio abria em `"locais"`, que
  é a SEGUNDA da lista: entrar pelo menu caía nela com a primeira ali do lado, marcada como não
  escolhida. Agora o padrão é `ABAS.find(pode(chave))` — a primeira que a pessoa **pode ver**,
  que também resolve quem não tem permissão na primeira e caía numa aba vazia.

- Credenciais ficam cifradas (`services/segredos.py`, Fernet com chave derivada do
  `JWT_SECRET`) e **nunca voltam pela API** — só mascaradas. Trocar o `JWT_SECRET` invalida
  as credenciais guardadas.

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

- 🔑 **De que SETOR cada pessoa cuida** (`usuario_setores`, migração 052, cadastro de usuário
  ▸ "De que setor cuida", 03/09/2026, pedido do dono).
  🔑 **A tabela existia desde o script 004 e NUNCA foi lida por nada.** O comentário dela dizia
  "Restrição por setor (o ajudante conta só a área dele). Sem linha = sem limite." — e ficou
  vazia: nenhuma tela oferecia o campo, nenhum endpoint a consultava. É literalmente a mesma
  história de `usuario_papeis.id_unidade`, que também esperou a tela aparecer: **o sistema sabia
  fazer e não oferecia isso a ninguém.** Por isso a migração 052 não cria nada — só acrescenta o
  índice que faltava e registra o dia em que a tabela passou a valer.
  ⚠️ **Lista VAZIA quer dizer TODOS**, como o 004 já dizia — a mesma convenção da loja
  (`id_unidade` nulo) e da escala do inventário. É o que faz o deploy não tirar nada de ninguém:
  quem está cadastrado hoje continua vendo o que via.
  ⚠️ **`todos_setores` é a resposta, não o tamanho da lista.** Com ele ligado, `/auth/me` devolve
  a lista **cheia** (todos os ativos) — é ela que o formulário oferece para marcar, e um
  administrador com lista vazia não teria o que oferecer a ninguém. Deduzir "todos" de uma lista
  vazia faria tela e servidor discordarem exatamente no caso comum.
  ⚠️ **Nulo NÃO é lista vazia no `UsuarioUpdate`**: nulo é "não mexi nos setores" — é o que uma
  tela antiga manda — e vazio é a escolha explícita de "todos". Tratá-los igual faria qualquer
  PUT antigo apagar em silêncio a restrição que alguém acabou de configurar. A suíte cobra os
  dois caminhos.
  ⚠️ **Isto NÃO é permissão, e a tela DIZ isso.** A permissão diz o que a pessoa sabe fazer
  (`producao.agenda`); o setor diz de que parte da casa ela cuida. Quem lesse "só estes setores"
  como bloqueio deixaria de configurar o papel — e a pessoa continuaria abrindo as telas pelo
  menu. Misturar os dois obrigaria a criar um papel por setor ("Cozinha da Confeitaria",
  "Cozinha do Bar") e a repetir cada mudança de permissão em todos eles.
  ⚠️ **O alcance é o do PAINEL e o da agenda, não o do sistema inteiro** (decisão do dono).
  Transformar setor em escopo global, como a loja é, tiraria do ar no instante do deploy telas
  que a pessoa usa hoje.
  🔑 **As mesmas duas travas da loja**: quem não cuida do setor não põe ninguém nele, e ninguém
  encolhe o próprio alcance — quem se restringisse perderia os outros de vista, e a primeira
  trava o impediria de devolvê-los a si mesmo.
  ⚠️ **Só setores ATIVOS contam** ao montar o contexto: um setor desativado que continuasse na
  lista deixaria a pessoa restrita a um lugar que não existe mais, e o sintoma seria um painel
  vazio sem explicação. Desativar o último setor de alguém a devolve a "todos".
  ⚠️ **`DELETE /setores` APAGA o setor que nunca foi usado** e só desativa o que tem produto —
  a suíte precisa prender um produto ao setor antes de desativá-lo, senão a recusa volta como
  404 "não encontrado", que é outra afirmação.
  Coberto por `tests/smoke_setor_do_usuario.py` (29 checagens) e pelo bloco `10g` do
  `verificar.mjs`.

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

- **Recuperação de senha** (19/08/2026): `services/senhas.py` (token de 32 bytes, só o sha256
  no banco, 30 min, **uso único**, pedido novo mata o anterior; redefinir **revoga todas as
  sessões**), `services/email.py` + `routers/email_config.py` (SMTP em `integracoes`, senha
  cifrada e mascarada). ⚠️ A tela pública responde **a mesma frase** para e-mail cadastrado e
  inventado — senão vira verificador de quem trabalha na casa; o motivo real vai só para a
  auditoria. Sem SMTP o sistema **não para**: grava o `.eml` em `api/arquivos/emails/` e o
  admin entrega o link pela tela de Usuários (`POST /usuarios/{id}/recuperar-senha` devolve o
  link — é o único lugar onde ele aparece).

- 🔑 **A lista de USUÁRIOS também pagina** — a base acumula um por rodada, porque usuário com
  histórico vira inativo em vez de sumir, e a checagem do link de recuperação acusava a tela de
  não oferecer o botão numa linha que ela nem mostrava. Mesma correção da lista de apoio:
  aumentar a página para 100 antes de procurar, que é o que uma pessoa faria.

- 🔑 **`JWT_SECRET` tinha padrão embutido e NADA o conferia** (11/09/2026, achado na varredura
  do módulo). `config.py` fazia `os.getenv("JWT_SECRET", "troque-este-valor-no-env")`, e nenhuma
  linha do sistema validava o valor.
  🔑 **Ele carrega duas coisas, e nenhuma é pequena.** Assina a sessão (`seguranca.token`),
  então quem conhece o valor **forja um token para qualquer usuário** — inclusive administrador,
  sem senha, sem login e sem deixar tentativa registrada. E deriva a chave que cifra as
  credenciais de integração (`services.segredos`), então com ele conhecido a cifra do Omie, do
  PDV e do SMTP deixa de proteger.
  🔑 **O precedente é da casa**: o primeiro deploy real subiu com o e-mail e a senha padrão do
  administrador porque as variáveis não foram definidas no painel — e nada avisou. A trava do
  admin nasceu daí; esta é a mesma lição aplicada ao segredo que protege todo o resto.
  ⚠️ **Roda em TODO start, e essa é a diferença para `garantir_admin`.** Aquela sai cedo quando
  já existe usuário (`if cur.fetchone()["n"]: return`), porque a senha do admin só é decidida na
  criação. O segredo pode ser esquecido numa migração de ambiente, num app novo, num restore —
  o risco não é só do primeiro dia.
  ⚠️ **Antes do `init_pool` e da migração**: sem segredo válido nada mais importa, e falhar
  cedo é mais barato que falhar depois de reescrever dado.
  ⚠️ **A frase diz o que está em jogo**, não "defina a variável": quem lê precisa entender por
  que largaria tudo para fazer isso agora. E traz o comando que gera um.
  ⚠️ **Com `DEBUG` ligado não há trava** — o desenvolvimento precisa subir sem `.env`, e é para
  isso que o padrão existe. Há também um mínimo de 24 caracteres, defensivo: o roteiro de deploy
  manda gerar 48 bytes.
  ⚠️ **Trocar o segredo depois torna ILEGÍVEIS as credenciais guardadas** (a chave Fernet deriva
  dele). O sistema já sabe distinguir isso de "não configurado" — `segredos.ilegivel()` —, então
  a tela diz o que houve em vez de mandar redigitar achando que foi erro de digitação.

- ⚠️ **A bateria de TELA bate na conta real do Omie quando o modo é `real`** (16/09/2026). A
  credencial voltou a estar configurada, e com ela `GET /omie/conferencia` e
  `/omie/custos-iniciais/previa` levam **~17 s cada** contra a conta do cliente — medido com a
  máquina livre. A fase de Integrações dava 30 s à conferência e caía por contenção; e a falha se
  espalhava, porque enquanto ela roda a tela fica `ocupado` e os botões ficam **desabilitados**,
  então o clique seguinte não acontece e o sintoma vira "o botão do custo inicial não está na
  tela". O orçamento subiu para 90 s, que é o que a prévia do custo já usava.
  🔑 **Para rodar a bateria, o modo `simulado` é o certo**: os mesmos endpoints respondem em
  0,0 s sobre as fixtures, e as duas rotas passam pelo mesmo código. Trocar o modo **preserva a
  credencial** (`app_key`/`app_secret` em branco mantêm o que está guardado), então voltar ao real
  é um clique — não é a perda documentada acima.
  ⚠️ E não é só tempo: cada rodada consumia cota da conta do cliente.

- 🔑 **Chave de acesso de MÁQUINA e o conector MCP do Claude** (migrações 074 e 075,
  19/09/2026, pedido do dono: "usar o Botané pelo Claude via MCP"). O conector mora NA API:
  `POST /mcp` (no ar, `https://sistema.botanedeliecafe.com.br/api/mcp`), cadastrado no
  claude.ai como conector personalizado, com login por OAuth. Só leitura.
  - `tokens_api` guarda **só o hash** (sha256, como o refresh). Duas origens: `manual`
    (gerada na tela de Usuários, valor `btn_…` mostrado UMA vez, validade 1 a 365 dias) e
    `oauth` (a pessoa conectou o Claude). Revogar não apaga: a linha diz quem usou e até quando.
  - 🔑 **A chave age COMO o usuário, nunca por cima dele.** `contexto_da_credencial` resolve a
    chave para um `id_usuario` e daí é o `Contexto` de sempre: papel, loja e setor valem
    igual. Usuário desativado leva as chaves junto (`carregar_contexto` recusa inativo).
  - 🔑 **O prefixo `btn_` escolhe a porta** antes de qualquer conta: JWT começa com `eyJ`.
  - 🔑 **Só leitura se decide num lugar só** (`contexto_da_credencial`, parâmetro `escreve`).
    `contexto_atual` passa o método HTTP; o `/mcp` passa `False`, porque é POST por protocolo
    mas só lê — e cada ferramenta vira um GET por dentro, que passa pela mesma conferência.
    Vale para toda rota que existe e para as que vão nascer.
    ⚠️ Nem as escritas "inofensivas" passam: chave vazada que troca a senha do dono toma a conta.
    ⚠️ **"Só leitura" é pelo método, então GET com efeito passa.** Varrido em 19/09: são
    benignos (auditoria das exportações, a linha de `parametros` criada na primeira leitura),
    EXCETO `GET /omie/conferencia`, `/conferencia-notas` e `/custos-iniciais/previa`, que chamam
    a conta real do Omie e **gastam cota**. As ferramentas do Claude não os chamam, mas a chave
    vale para qualquer GET — chave vazada de quem tem `integracao.omie` gastaria cota. GET novo
    que escreva ou chame fora tem de entrar nesta lista.
  - 🔑 **Chave não gere chave, nem para LISTAR** (`_so_por_login` / `_eu_por_login`, olham
    `ctx.id_token`). Uma chave que criasse outra ficaria imortal.
  - 🔑 **As travas de loja do cadastro, pela outra ponta** (`_conferir_alcance`): ninguém gera
    chave para quem enxerga loja que ele mesmo não enxerga. ⚠️ O alcance do alvo é lido direto
    de `usuario_papeis`: `carregar_contexto` dá 403 para inativo, e a lista das chaves de quem
    foi desativado deixava de abrir.
  - ⚠️ `ultimo_uso_em` grava com **resolução de 1 minuto**; revogada, vencida e inexistente dão
    **a mesma frase** (401).
  - **O `/mcp` (`routers/mcp.py`) é escrito À MÃO, sem o SDK `mcp`.** O SDK puxa `uvicorn`,
    `starlette` e `pydantic` mais novos que os presos no `requirements.txt`. Um servidor só de
    ferramentas precisa de pouco: JSON-RPC em POST, resposta JSON, `initialize`/`ping`/
    `tools/list`/`tools/call`. **Sem sessão** (`Mcp-Session-Id`): nada a perder quando o
    contêiner reinicia. Erro de ferramenta volta como resultado com `isError` (o modelo lê e se
    corrige); ferramenta inexistente é erro de protocolo.
  - 🔑 **As ferramentas são rotas que JÁ EXISTEM, chamadas por dentro**
    (`services/mcp_ferramentas.py`, `httpx.ASGITransport` sobre o próprio app, com a chave de
    quem pediu). Permissão, loja (`id_loja` → `X-Unidade`) e setor são os da tela. Ferramenta
    nova = uma entrada em `FERRAMENTAS`. São **69** (21/09/2026) — 62 de leitura e 7 de gravação —, cobrindo produtos, fichas,
    estoque, produção, inventário, remessas, compras, vendas, consumo, pessoas, tabelas de
    apoio, CMV, reservas, empresa e auditoria. ⚠️ **O caminho da rota é escrito à mão na
    tabela, e caminho errado só aparece quando alguém chama** — foi o que aconteceu com a
    auditoria (`/historico`, que não existe: o router é `/auditoria`). Por isso a suíte chama
    TODAS: 403 e 409 são resposta de negócio, 404 é defeito. ⚠️ Só inteiro entra no caminho (`{id_produto}`):
    string ali abriria `../` para outra rota.
  - 🔑 **OAuth 2.1 à mão** (`services/oauth.py`, `routers/oauth.py`): registro dinâmico aberto
    (RFC 7591; só https, ou http em localhost), PKCE **S256 obrigatório**, código de uso único
    queimado ANTES de conferir o verificador (errar não dá segunda chance), `iss` na volta
    (RFC 9207), revogação (RFC 7009). Cliente ou `redirect_uri` inválidos **nunca
    redirecionam** — erro na página, senão vira redirecionador aberto. A página de login não
    abre em moldura (clickjacking).
  - 🔑 **Uma linha por CONEXÃO, rotacionada no lugar**: a chave vive 1 h e a renovação
    (`btr_…`, 30 dias deslizantes) troca `token_hash` e `refresh_hash` na MESMA linha. Uma linha
    por renovação encheria a tela de 24 revogadas por dia. Por isso a tela lê **`vence_em`**
    (`coalesce(refresh_expira_em, expira_em)`) e não `expira_em`, que pintaria de "vencida" toda
    conexão parada há uma hora.
  - 🔑 **Descoberta pela RAIZ do domínio.** O claude.ai lê
    `/.well-known/oauth-protected-resource/api/mcp` e `/.well-known/oauth-authorization-server`
    — sem `/api`. O `app.yaml` manda esses dois caminhos para a API com
    `preserve_path_prefix: true`; sem isso cairiam no Next (404 em HTML). O emissor é a ORIGEM
    (sem `/api`), e tudo sai de `API_URL_PUBLICA` — a API não tem como deduzir o `/api`, que o
    App Platform tira antes de repassar.
  - 🔑 **Permissão nova `integracao.claude`**: conectar o Claude é levar dados da casa para a
    conta da pessoa num serviço de IA — decisão do dono, papel a papel. Nasce só com quem tem
    `admin.usuarios`. Exigida na autorização E em todo `POST /mcp` (tirar a permissão corta as
    conexões já feitas). ⚠️ Na página, a permissão é conferida ANTES da troca obrigatória de
    senha: é o "não" definitivo.
  - Tela: `components/chaves-de-acesso.tsx` com uma `FonteDeChaves` (`lib/tokens-api.ts`) — no
    cadastro do usuário (admin, gera chave) e em **Perfil ▸ Claude** (a pessoa vê o endereço do
    conector e desconecta pelo `/auth/me/tokens`). ⚠️ O cartão da chave recém-criada é
    `div.aviso`, não `<Aviso>`: o `Aviso` é `<p>`, e botão dentro de parágrafo é erro de
    hidratação.
  - ⚠️ **A fase 1 foi um conector stdio (`conector_mcp/`) e saiu no mesmo dia**: dois catálogos
    de ferramentas, um em cada lado, divergiriam. O Claude Code usa a mesma URL:
    `claude mcp add --transport http botane <url>/mcp` (OAuth), ou com
    `--header "Authorization: Bearer btn_…"` (chave manual — o dono dela precisa de
    `integracao.claude`).
  - Cobertura: `smoke_tokens_api.py` (34), `smoke_conector_claude.py` (60: o fluxo do claude.ai
    passo a passo, sem biblioteca), `smoke_bloqueio_login.py` e o bloco `9a2` do
    `verificar.mjs`. Validado também com o **SDK oficial** (`mcp` 2.2.0) fazendo descoberta +
    registro + login + ferramentas contra a API local. ⚠️ O SDK 2.x mudou a API (`FastMCP` →
    `MCPServer`, atributos em snake_case); exemplo da internet quase sempre é da 1.x.
  - 🔑 **Gravação pelo Claude** (20/09/2026, pedido do dono; migração 077). Seis ferramentas:
    ligar item de nota a produto, ignorar item, criar produto do item, criar produto,
    corrigir produto e **lançar nota no estoque**. Todas passam pela MESMA rota da tela, com
    as mesmas recusas.
    🔑 **Duas portas para a escrita, e as duas exigem um "sim" explícito**: a chave gerada
    à MÃO em Usuários (`somente_leitura = false`), e — desde a migração 078 — a **caixa na
    página de entrada do claude.ai** ("Deixar o Claude alterar cadastros"), que nasce
    DESMARCADA. Chave que altera só para quem tem `integracao.claude` (a permissão é a
    mesma de conectar, por decisão do dono).
    ⚠️ **A segunda porta nasceu de topar na prática** (21/09/2026). No dia anterior o dono
    escolheu "só chave gerada pelo admin", e a conexão do claude.ai ficou sempre só
    leitura; quando ele foi juntar cadastros repetidos por lá, o Claude respondeu que o
    Botané *"só me oferece consultas"* — certo, e inútil para o trabalho que ele queria
    fazer. Lição: **quando a escrita mora numa porta e o trabalho mora na outra, o desenho
    não sobrevive ao primeiro uso.**
    ⚠️ **A escolha viaja no CÓDIGO de autorização** (`oauth_codigos.escrita`), não na
    sessão: entre a página e a troca por chave não há estado do lado de cá, e sem isso o
    "sim" se perderia no caminho. A renovação **preserva** (a linha é a mesma e
    `somente_leitura` não é tocado): renovar não amplia nem encolhe o que foi autorizado.
    ⚠️ **A frase acima da caixa teve de mudar junto**: ela dizia "não vai poder alterar
    nada", que virou mentira no instante em que a caixa apareceu logo abaixo.
    🔑 **Chave só de leitura nem VÊ as ferramentas que gravam** (`tools/list` filtra). É
    conforto, não segurança: quem barra é `contexto_da_credencial`, com 403 no POST de
    dentro. O valor está em não deixar o modelo propor ao usuário algo que vai falhar.
    ⚠️ **`destructiveHint` ligado em TUDO que grava**, inclusive no que "só corrige um
    campo": é o que faz o Claude perguntar antes. Nenhuma é idempotente.
    🔑 **O `atualizar_produto` edita TODO campo que o `PUT /produtos/{id}` aceita**
    (23/09/2026, pedido do dono: *"permitir a marcação de Controla Estoque. Pode liberar
    ajuste em todos os campos editáveis do produto."*). O `smoke_conector_claude` confere
    que `ProdutoUpdate.model_fields` ⊆ esquema da ferramenta — campo novo no PUT que não
    chegar ao conector derruba a suíte.
    ⚠️ **Até ali a unidade de estoque e o fator de compra ficavam FORA** (20/09), porque
    trocá-los converte custo e saldo. Entraram porque a ROTA já não deixa a conversão
    passar calada: o salto de custo volta 409 com os dois números, e só
    `confirmar_troca_de_unidade` explícito grava — o mesmo vale para
    `confirmar_reativacao`. A descrição manda o Claude mostrar os números e só reenviar
    com o sim da pessoa. ⚠️ `fornecedores` SUBSTITUI a lista (o `Param` ganhou `itens`
    para descrever array). ⚠️ A FOTO continua fora: é multipart.
    ⚠️ **Só o que o modelo mandou vai no corpo** — o `PUT` de produto grava com
    `exclude_unset`, e mandar os não informados como nulo apagaria campo que ninguém pediu
    para apagar.
    ⚠️ **`lancar_nota` entrou, `estornar` NÃO.** Lançar escreve no razão, que é append-only:
    desfazer é estornar, e o estorno fica na tela, com gente olhando. Dito ao dono; ele
    escolheu assim mesmo.
  - 🔑 **A auditoria diz POR ONDE veio a alteração** (`auditoria.origem`, migração 077):
    `claude` ou nulo (= a tela), com etiqueta "pelo Claude" na tela de Auditoria. A pergunta
    "o que o Claude fez ontem?" aparece justamente quando algo saiu errado; sem a coluna, a
    resposta seria cruzar horário com `ultimo_uso_em` da chave, à mão.
    🔑 **Quem marca é o MIDDLEWARE, pelo prefixo da credencial — e isso custou uma rodada.**
    A primeira versão marcava em `contexto_da_credencial`, que é SÍNCRONA: o FastAPI a roda
    numa thread com uma CÓPIA do contexto, e o `ContextVar` que ela grava morre com a
    thread. A auditoria saía sempre sem origem. **Regra de bolso: `ContextVar` que as rotas
    vão ler tem de ser posto ANTES de a requisição descer** — é onde o `pediram_o_total` já
    estava. ⚠️ E é reposto a cada requisição: sem o `reset`, uma chamada de chave deixaria a
    marca na tarefa e a requisição seguinte, de gente, sairia como se fosse do Claude.
  - 🔑 **Achar repetidos e fundi-los pelo Claude** (21/09/2026, pedido do dono: *"buscar
    pelo Claude os produtos iguais e vincular eles por lá"*): `produtos_duplicados` (nome
    idêntico, o mesmo sinal da tela), `previa_de_fusao` e `fundir_produtos`.
    ⚠️ **A prévia não é enfeite: fusão NÃO tem desfazer**, e é ela que diz com que nome
    fica, o que é completado e o que trava. A descrição da ferramenta manda chamá-la antes.
    ⚠️ **Quem SAI é o cadastro sem história** — o servidor recusa a direção invertida
    nomeando o que trava, e é o engano natural de quem olha dois nomes iguais.
    ⚠️ **A fusão em GRUPO (`/produtos/duplicados/fundir`) ficou de fora**: ela junta vários
    de uma vez sem prévia par a par, que é justamente a conferência que se quer aqui.
  - Cobertura da escrita: blocos `7c` (a chave de leitura não vê nem usa; a que altera grava;
    a auditoria marca) e `7d` (nota criada, conciliada, lançada e estornada, tudo pelo
    conector), `7e` (achar repetidos, prévia, fundir) e `7f` (a caixa do claude.ai: marcada
    grava, desmarcada não, e a renovação preserva) do `smoke_conector_claude.py`.
    ⚠️ A limpeza do `7f` revogava TODAS as conexões vivas e derrubava os blocos seguintes —
    agora acha a linha pelo **prefixo da chave**, não por "a primeira de escrita".

## Armadilhas já pagas

- 🔑 **O bloqueio por tentativas de login NUNCA funcionou até 19/09/2026.** O `UPDATE
  tentativas_login` e o `raise` moravam no MESMO `with get_cursor()`, e `get_conn` faz
  **rollback** quando uma exceção atravessa o bloco: o contador voltava a zero a cada erro.
  Qualquer um podia tentar senhas sem limite. Achado ao escrever a página de autorização do
  Claude, que precisava da mesma trava. Agora mora em `seguranca.conferir_credenciais` (login e
  página do Claude), que grava a falha e levanta o erro DEPOIS do bloco.
  🔑 **Regra de bolso: escrita que precisa sobreviver a um erro não pode estar no mesmo
  `with get_cursor()` do `raise`.** Vale para qualquer contador, registro de tentativa ou log de
  recusa. Coberto por `tests/smoke_bloqueio_login.py`.
  ⚠️ Efeito esperado: no ar, cinco senhas erradas passam a travar a conta por
  `BLOQUEIO_MINUTOS` (15) — o desbloqueio é o botão em Usuários.

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

- ⚠️ **Falha de e-mail agora vai para o LOG, não só para a tela.** O log da nuvem mostrava
  `POST /email/testar 502` e mais nada — o motivo ia para quem clicou, que quase nunca é quem lê
  o log. O `print` está em `email.entregar`, e não no router, porque são três chamadores e um
  deles é a recuperação de senha, **rota pública**: justamente a que ninguém está olhando quando
  falha. ⚠️ Servidor e porta entram na linha; usuário e senha **nunca**.

- 🔑 **`JSON.parse` antes de olhar `r.ok` transforma todo 5xx em erro de sintaxe.** Quem responde
  ao navegador não é só o FastAPI: o roteamento do App Platform responde HTML quando o app está
  reiniciando ou o tempo esgotou, e a tela dizia
  `Unexpected token '<', "<!DOCTYPE "... is not valid JSON` — engolindo o status real. Agora
  `corpoDaResposta` (em `web/lib/api.ts`) lê o corpo sem estourar e devolve frase útil. O
  `baixar()` já fazia certo; `pedir` e `login` não. ⚠️ No `login` era pior: HTML ali lê como
  **senha errada**.

- ⚠️ **O tamanho mínimo de senha mora em UM lugar**: `SENHA_MINIMA`, em `api/config.py` (hoje
  **6**), espelhado em `web/lib/senha.ts` para o `minLength` do input e a frase da dica. Estava
  escrito oito vezes, e com dois valores: 12 no start e 8 nos formulários — senha aceita na
  criação do administrador era recusada na troca obrigatória do primeiro acesso. A regra de
  verdade é a do servidor; o `minLength` só evita a viagem.

- ⚠️ **Marcador de configuração vira dado, e dado ruim não avisa.** O `ADMIN_EMAIL` do
  primeiro deploy subiu com o `DEFINA_NO_PAINEL` do `app.yaml` copiado tal e qual: passou pela
  guarda (não era o valor padrão, e a senha tinha 16 caracteres) e criou um administrador
  chamado `defina_no_painel`. A conta nasceu **morta** — `LoginRequest.email` é `EmailStr`, e o
  pedido morre com 422 antes de tocar o banco —, mas o log dizia "administrador criado" como em
  qualquer subida boa, e a única saída foi apagar a linha direto no Postgres. `garantir_admin`
  agora confere o e-mail com a **mesma regra do login** (`pydantic.validate_email`) e recusa o
  marcador como senha. Regra de bolso: **valor de configuração que vira registro no banco
  precisa passar pela validação de quem vai LER esse registro.**

- **`allowedDevOrigins` no `next.config.mjs`**: sem isso o dev server do Next devolve **403
  nos chunks** quando a página é aberta por `127.0.0.1` (ou pelo IP, no teste em celular).
  A tela renderiza, nunca hidrata, e o formulário vira submit nativo — parece bug de login.

- **`localStorage` é do domínio, não da aba**: no teste de navegador, logar como outro
  usuário em qualquer página troca a sessão de todas — voltar como admin antes de seguir.

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

- ⚠️ **O Omie tem DOIS dialetos de paginação** (`cliente.DIALETO_PADRAO` e `DIALETO_HUNGARO`).
  Os módulos antigos falam `pagina`/`registros_por_pagina`; o recebimento exige
  `nPagina`/`nRegistrosPorPagina` e recusa o outro com "Tag [PAGINA] não faz parte da
  estrutura". Cada chamada recusada gasta cota — e cota gasta bloqueia a conta.

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

- 🔑 **Nem toda rota do PDV responde um OBJETO — e isso derrubava o envio DEPOIS de gravar**
  (30/08/2026). `impressoras/update` devolve a STRING `"Registry updated successfully!"`, como
  o `delete` já fazia. O router fazia `resposta.get("id")` e levantava `AttributeError`:
  **500 com corpo vazio**, a alteração já feita do outro lado, a pendência continuando aberta
  e a tela só sabendo dizer que falhou. Clicar de novo repetia o ciclo.
  ⚠️ A nota da string já existia para o `delete` e o cliente HTTP já a tolerava — quem supunha
  o dicionário era o router, um lugar só, que a nota não alcançou.

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

- 🔑 **O cadastro vem ANTES da nota** (`importador.sincronizar_completo`, migração 053,
  03/09/2026, pedido do dono, espelhando o que o PDV já fazia). Produto criado no Omie hoje e
  comprado hoje ficava sem vínculo, ia para a fila de pendências e esperava alguém lembrar de
  clicar em "Importar catálogo" — um segundo botão que ninguém sabe que precisa apertar.
  🔑 **A lógica mora no SERVIÇO, não no router, porque há DOIS chamadores.** A primeira versão
  ficou só no endpoint, e o agendador chama `sincronizar` direto: a integração funcionaria pelo
  botão e não pela madrugada, sem nada explicando. É a mesma lição do relógio do cardápio.
  ⚠️ **Falhar no catálogo NÃO impede a busca de notas.** Nota não importada é compra faltando no
  estoque e no CMV; cadastro não sincronizado é um item que fica na fila mais um dia.
  ⚠️ **Aqui NÃO existe o "só criar, nunca alinhar" do PDV**, e a diferença é real: o `importar`
  do cardápio sobrescreve campo, então rodá-lo a cada busca desfaria calada a correção de quem
  arrumou a categoria de um prato à mão. O `_completar_produto` do Omie usa
  `coalesce(coluna, valor)` — preenche só o que está nulo. Reimportar não desfaz nada.
  ⚠️ **O catálogo custa ~115 s** contra a conta real (2.201 produtos, paginados), enquanto as
  notas sozinhas levam 4 s. Medido, não estimado — a estimativa inicial era de 15 a 30 s e estava
  errada por um fator de quatro. Por isso: a agenda faz o catálogo **uma vez por dia**
  (`integracoes.catalogo_em`), `?catalogo=false` pula o passo, e a tela avisa que a busca demora.
  ⚠️ **A agenda do Omie aceita frequência HORÁRIA** — sem a trava diária, a varredura de 2.201
  produtos rodaria vinte e quatro vezes por dia para achar os dois que nasceram.
  ⚠️ **O relógio é do AGENDADOR, não do botão**: quem clica está pedindo agora, não dispensando a
  passada da madrugada. Mesma correção que o `cardapio_em` do PDV já precisou.
  ⚠️ **A premissa de um teste caiu junto, e não se enfraqueceu o teste.** O bloco "sem produto,
  sem lançamento" dependia de a nota chegar antes de o produto existir; com o catálogo na frente,
  a fila esvazia. Aquela sincronização passou a usar `catalogo=false` (com o porquê escrito) e o
  caminho novo ganhou bloco próprio, o `8b`.
  ⚠️ **Achado à parte, não regressão:** um item de nota descrevendo café estava ligado a
  `LARANJA PERA KG`. A causa é a conta REUSAR códigos — o item traz `codigo_fornecedor` PRD00004
  e o catálogo atual diz que PRD00004 é laranja. O vínculo saiu do nível 1 da cascata
  (`codigos_externos`), que já existia. Se a conta recicla códigos, cada reciclagem vira um
  vínculo silencioso e errado numa nota antiga — vale uma investigação própria.

- 🔑 **Trocar o `JWT_SECRET` deixou de custar as integrações.** Ele assina a sessão E deriva,
  por SHA-256, a chave Fernet que cifra `integracoes.credenciais` — uma tabela, uma coluna,
  guardando Omie, PDV e a senha de SMTP. Até 11/09/2026 trocá-lo tornava tudo isso ilegível, e
  o `deploy.md` dizia em duas linhas que o valor "não se troca depois".
  ⚠️ **Uma troca que custa redigitar tudo é uma troca que não se faz** — e aí o segredo fraco
  fica. Foi o que aconteceu: a trava do segredo parou o start em produção
  (`JWT_SECRET curto demais (16 caracteres)`), a DO manteve o contêiner anterior no ar, e a
  pergunta do dono foi justamente se dava para trocar sem perder o configurado.
  ⚠️ **O caminho é `JWT_SECRET_ANTERIOR`, e ela é de UM deploy.** Definida junto com o segredo
  novo, `rotacionar_segredos()` (no start, depois das migrações) abre cada linha com a chave
  velha e a regrava com a nova. Removida no deploy seguinte — deixá-la mantém um segredo
  aposentado vivo no ambiente, que é metade do motivo de estar sendo trocado. Por isso
  `decifrar` tenta a chave anterior **depois** da atual, nunca antes.
  ⚠️ **A sessão não é preservada, de propósito**: todo mundo entra de novo. Aceitar o token
  antigo manteria o segredo aposentado valendo, que é o que a troca veio encerrar.
  ⚠️ **Linha que nenhuma das duas chaves abre é contada e deixada em paz** (outro ambiente, um
  terceiro segredo, dado corrompido): regravar seria escrever lixo por cima de lixo e apagar
  destruiria a única pista. `ilegivel()` continua denunciando na tela.
  Roteiro em `docs/deploy.md` seção 6b; regressão em `api/tests/smoke_rotacao_segredo.py`.
  ⚠️ A suíte mede as perdidas por **delta**: a base local tem credenciais reais cifradas com o
  segredo DESTE ambiente, que caem na contagem sem que nada esteja errado.

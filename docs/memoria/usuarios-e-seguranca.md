# Usuários, permissões e sessão

> Extraído do CLAUDE.md original (seções "O que já existe" e "Armadilhas já pagas").
> Consultar antes de mexer nesta área do sistema.

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

## Armadilhas já pagas

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

# Infraestrutura e deploy

> Extraído do CLAUDE.md original (seções "O que já existe" e "Armadilhas já pagas").
> Consultar antes de mexer nesta área do sistema.

## O que já existe

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

## Armadilhas já pagas

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

- 🔑 **O agendador dispara na hora da CASA, não na do contêiner** (`FUSO_DA_CASA`,
  `agenda_integracao.agora_da_casa`, 04/09/2026, relato do dono). Ele configurou a busca para as
  20h em produção e **nunca havia registro daquela execução**. A suspeita era que a busca manual
  consumisse a cota do dia — não consumia: `regra.marcar`, único lugar que move
  `agenda_rodou_em`, tem exatamente dois chamadores, os dois agendadores.
  ⚠️ **A causa era o FUSO.** O agendador perguntava a hora ao sistema operacional
  (`datetime.now().astimezone()`), e o App Platform roda o contêiner em **UTC**: "20h" era
  avaliado contra 20h UTC, que são **17h em Brasília**. A busca não deixava de rodar — rodava
  três horas antes, e por isso nunca havia registro no horário escolhido.
  🔑 **É invisível em desenvolvimento**, porque a máquina de casa está no mesmo fuso que o
  código presumia. **Nenhuma suíte pegaria rodando normal** — todas rodam local. Por isso o
  `smoke_agenda_fuso.py` força o que só acontece no ar: um `agora` em UTC, e prova que o mesmo
  instante lido nos dois fusos dá respostas opostas.
  ⚠️ **O segundo efeito era pior porque é intermitente**: `agenda_rodou_em` volta do banco com o
  fuso da sessão (São Paulo) e o `agora` estava em UTC. Entre 21h e a meia-noite as datas
  divergem, e o `.date() >= .date()` fazia o agendador ora pular um dia, ora rodar duas vezes.
  Agora as duas datas são comparadas no mesmo fuso.
  ⚠️ **`tzdata` entrou no `requirements.txt` por causa disto.** `zoneinfo` lê a base do sistema
  operacional, e a imagem enxuta do deploy não a traz: sem o pacote, o próprio conserto
  levantaria `ZoneInfoNotFoundError` no start, em produção, falando de um fuso que ninguém
  tocou. Há queda para `-03:00` fixo **com aviso no log** — o Brasil não tem horário de verão
  desde 2019, então acerta hoje, e o aviso é o que impede a descoberta pelo relatório errado se
  ele voltar.
  ⚠️ **Se `agenda_rodou_em` estiver NULO**, não é o fuso: é `agenda_frequencia` ainda em
  `MANUAL`, a integração inativa, ou o processo não ficando de pé — o laço vive no `lifespan` e
  morre com o contêiner.

- 🔑 **A DIÁRIA só rodava se alguém estivesse acordado na hora marcada — e o dia inteiro
  passava em branco** (02/09/2026, pedido do dono). `deve_rodar` exigia
  `agora.hour == agenda_hora`: o disparo existia dentro daqueles sessenta minutos e em mais
  nenhum instante. Com a API parada às 4h — um deploy, um reinício, a máquina desligada — a
  busca daquele dia **simplesmente não acontecia**, e nada dizia isso: a tela mostrava a última
  sincronização, que uma busca manual tinha atualizado, e a agenda parecia em dia.
  **Medido na base local**: a diária das 4h do PDV tinha rodado pela última vez em **31/08**,
  com hoje sendo 02/09 — dois dias de notas e cupons perdidos, ou seja compra a menos e receita
  a menos no CMV, em silêncio.
  A regra virou a pergunta que a casa faz: *já buscou hoje?* Não tendo buscado e já passada a
  hora marcada, busca — assim que houver alguém para buscar.
  ⚠️ **Continua sendo UMA vez por dia.** Voltando depois de três dias fora do ar, roda uma vez e
  não três: quem responde é a DATA do último disparo, não quantos horários passaram. Três buscas
  seguidas só gastariam cota, e a janela adaptativa cobre o período inteiro numa ida só.
  ⚠️ **E a primeira configuração dispara logo**, quando a hora escolhida já passou — em vez de
  esperar até a madrugada seguinte. A tela diz isso.

- **PWA instalável** (19/08/2026): `app/manifest.ts`, `public/sw.js`, `app/offline/page.tsx`,
  `components/pwa.tsx` (registro + convite) e `scripts/gerar-icones-pwa.mjs` (roda na mão,
  usa sharp). Regras do service worker que **não se afrouxam**: a API (outra origem) e
  `/api` são ignoradas por completo — cachear serviria o saldo de um usuário para o próximo
  que entrasse no mesmo aparelho; HTML é network-first com a página `/offline` de reserva;
  só `_next/static/*` é cache-first (o nome tem hash). ⚠️ **Em dev o cache de estático é
  desligado** (`/sw.js?dev=1`), senão o HMR do Next serve pedaço velho e vira caça a bug que
  não existe. ⚠️ `apple-mobile-web-app-capable` está declarado à mão em `metadata.other`: o
  Next 16 só emite o nome padronizado, que o Safari entende do iOS 17.4 em diante.

- Testes (1.784 verificações de API): `smoke_fundacao.py` (47, 48 em base virgem), `smoke_cadastros.py` (55),
  `smoke_fichas.py` (55), `smoke_estoque.py` (170), `smoke_cmv.py` (63), `smoke_omie.py` (116),
  `smoke_notas.py` (70), `smoke_senha.py` (40), `smoke_email_prazo.py` (15), `smoke_sessao.py` (17), `smoke_lotes.py` (28),
  `smoke_relatorios.py` (44), `smoke_kits.py` (29), `smoke_conversao.py` (29),
  `smoke_producao.py` (46), `smoke_alertas.py` (28), `smoke_paginacao.py` (25), `smoke_ajustes.py` (48), `smoke_ciclos.py` (32),
  `smoke_grupos_cmv.py` (45), `smoke_utensilios.py` (23), `smoke_inventario_filtros.py` (50),
  `smoke_exportacoes.py` (110), `smoke_produto_do_omie.py` (31), `smoke_agenda_omie.py` (31), `smoke_pdv_legal.py` (156), `smoke_vendas.py` (69), `smoke_vinculo.py` (91),
  `smoke_transferencias.py` (47), `smoke_lojas_do_usuario.py` (26),
  `smoke_memoria.py` (37),
  `cenario_cafeteria.py` (57) e `cenario_semana.py` (54); mais
  `web/scripts/testar-sw.mjs` (17, sem navegador) e
  `web/scripts/verificar.mjs` (461, no Chrome, com fotos em `web/scripts/_fotos`).
  Todos idempotentes; os de CMV medem **delta** sobre a apuração anterior, porque o banco
  local já tem dado de outras rodadas.

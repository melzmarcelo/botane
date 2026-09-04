# Cadastros, produtos e fornecedores

> Extraído do CLAUDE.md original (seções "O que já existe" e "Armadilhas já pagas").
> Consultar antes de mexer nesta área do sistema.

## O que já existe

- `api/db_scripts/`: 004 cadastros (setores, locais, categorias, UM, fornecedores, produtos,
  preços e produto×fornecedor), 005 semente dos cadastros.

- Routers da etapa 2: `cadastros.py` (as quatro tabelas de apoio no mesmo arquivo — são
  pequenas e sempre lidas juntas), `fornecedores.py`, `produtos.py`.

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

- ⚠️ **Nome repetido em tabela de apoio devolvia 500.** A unicidade é do banco (é o certo),
  mas deixar a constraint estourar dava "Internal Server Error" para quem só digitou duas
  vezes o mesmo nome — no primeiro dia, cadastrando setores e locais. `_recusar_repetido()`
  em `routers/cadastros.py` confere antes e devolve 409 com frase.

- ⚠️ **As suítes rodam contra base virgem.** `tests/comum.py` tem `garantir_local`,
  `garantir_locais`, `garantir_setores` e `garantir_fornecedor` — nenhuma suíte pode supor
  que existe local, setor ou fornecedor, nem contar linhas de semente. `garantir_fornecedor`
  procura pelo **CNPJ**, não pelo nome: o CNPJ é a chave única, e buscar por nome falhava
  quando o Omie simulado criava outro fornecedor com o mesmo documento.

- ⚠️ **A limpeza NÃO toca nas tabelas de apoio** (locais, setores, categorias): elas são
  cadastro base e ficam. Mas as suítes criam locais e setores com marcador a cada rodada, e a
  lista incha — vale tirar o que não é da semente de fábrica depois de uma bateria. A flag
  `--tabelas-de-apoio` esvazia mesmo, e aí a base fica MAIS vazia que uma instalação nova (a
  semente do script 005 não volta: o `db_updater` não reexecuta migração já aplicada).

- `api/limpar_dados.py` zera a operação e deixa a base como instalação nova (`--simular`
  mostra sem apagar). Produtos e fornecedores saem inteiros de propósito: o seed não cria
  nenhum. **Recusa banco que não seja local.**

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

- ⚠️ **Seletor com uma opção só, desabilitado, lê como travado.** O de unidade da contagem
  ficava assim para produto sem embalagem cadastrada. Agora ele oferece as três origens que
  convertem de verdade — unidade de estoque, embalagens do produto e unidades da **mesma
  grandeza** (KG↔G sem cadastro nenhum) — e, ao lado, o caminho "contar em outra embalagem?"
  para o cadastro do produto. ⚠️ Dentro de UNIDADE, siglas com o mesmo fator base ficam de
  fora: CX e PCT não se convertem entre si (é a mesma regra de `custos.converter`).

- **As quatro tabelas de apoio ficam num item de menu só** — decisão do dono, 24/08/2026,
  depois de experimentar as quatro separadas. ⚠️ Como "Tabelas de apoio" não é o nome de nada
  que alguém procura, **a tela diz o que tem dentro** logo abaixo do título, e cada aba tem
  endereço próprio (`/cadastros?aba=locais`) para guardar e voltar direto.
  ⚠️ O item de menu aceita **lista** de chaves — Tabelas de apoio serve a quatro permissões.

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

- ⚠️ **Código único repetido virava 500.** `codigo_omie`, `codigo_pdv` e `codigo_barras` têm
  índice único, e a violação vazava como "Internal Server Error" para quem só digitou um código
  que já é de outro produto. Virou 409 com frase que **nomeia o dono** — porque a ação seguinte
  quase sempre é abrir aquele cadastro e usar **Vincular**. Mesma família do nome repetido em
  tabela de apoio.

- ⚠️ **`ListarRecebimentos` não aceita filtro de data nenhum.** Testados e recusados:
  `dDtInicial`, `dDataInicial`, `dEmissaoDe`, `dDtEmissaoDe`, `dRegistroInicial`. Aceita só
  `cEtapa` e `nIdFornecedor`. Como a lista vem da nota mais VELHA para a mais nova, a varredura
  vai **da última página para a primeira** (`paginar(do_fim=True)`) e para na primeira página
  inteira fora da janela — senão a sincronização diária atravessaria três anos de histórico.

- **`nIdProduto` do item é o `codigo_omie` do produto** — nível 2 da cascata de conciliação,
  antes do EAN. É o de-para que o Omie já fez. Numa conta real, **109 de 114 itens** acharam
  produto por aí assim que o catálogo entrou.

- ⚠️ **O rodapé de tributos do DANFE vem grudado na descrição** e ia para o nome do produto:
  59 cadastros se chamavam "MAMÃO FORMOSA Trib. Aprox. (Fed: R$ 3,63…) Fonte: IBPT/…".
  `mapeadores._nome_limpo` corta na entrada; a migração 023 limpa o que já entrou.

- ⚠️ **Fator 1 num vínculo não é resposta, é a falta dela.** `codigos_externos.fator` e
  `produto_fornecedor.fator` nascem 1 por padrão — e **o lançamento da nota CRIA a linha de
  `produto_fornecedor`** só para guardar o último preço. A cascata de `_fator_do_item` aceitava
  esse 1 como informação, e o vínculo recém-criado passava na frente do `fator_compra` do
  produto: o galão de azeite de 5 L entrou certo na primeira nota e virou 1 L na segunda, sem
  ninguém mexer no cadastro. Agora só fator **diferente de 1** conta como resposta.

- ⚠️ **A unidade da nota ia CRUA para `produtos.um_compra`, que é chave estrangeira.** Uma
  conta real trouxe "UND", "BJ", "GA", "GF", "1UNID" — e criar produto a partir do item da nota
  devolvia 500 sem dizer por quê. Sigla desconhecida vira nulo.

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

- 🔑 **Os cadastros com o MESMO NOME, em lote** (`GET /produtos/duplicados`, tela
  **Integrações ▸ Cadastros com o mesmo nome**, `api/vincular_por_nome.py`, 03/09/2026, pedido
  do dono). O catálogo do Omie cria um cadastro por CÓDIGO, e o mesmo abacate aparece uma vez
  para cada fornecedor
  que já o vendeu. Juntar de dois em dois pelo Vincular resolve — mas com centenas de repetidos
  ninguém percorre a lista, e o trabalho não é feito.
  ⚠️ **O caminho mora em INTEGRAÇÕES, não em Produtos** (movido a pedido do dono, 03/09/2026).
  O primeiro lugar foi um botão no cabeçalho de Produtos, e estava errado de origem: o duplicado
  não é erro de quem cadastra — ele nasce das duas integrações, o catálogo do Omie criando um
  cadastro por CÓDIGO e o cardápio do PDV criando o dele. O caminho para desfazer fica ao lado
  do que produz. ⚠️ O cartão é guardado por `cadastros.produtos`, a permissão do ENDPOINT, e não
  por `admin.integracoes`: quem só configura credencial veria o cartão e levaria 403 no clique.
  🔑 **A tela já era referenciada e NUNCA existiu.** `/produtos/duplicados` aparecia no cartão do
  PDV em Integrações ("ver possíveis duplicados") e em dois comentários do código: o link levava
  a 404. Agora existe.
  🔑 **Isto DETECTA; quem decide é gente — e essa é a linha que não se cruza.** O projeto já
  removeu uma cascata que vinculava sozinha por semelhança de nome, porque errava nos dois
  sentidos. **Nome IDÊNTICO é um sinal muito mais forte que semelhança** — dentro de um catálogo
  só é quase sempre o mesmo item —, mas continua sendo um sinal: medido na base, **"VALE-PRESENTE"
  aparece três vezes com códigos de cardápio consecutivos**, que são quase certamente três
  valores diferentes; e o mapeador do Omie **apara todo texto no tamanho da coluna**, o que faz
  dois nomes longos e diferentes chegarem aqui iguais. A lista existe para ser OLHADA.
  ⚠️ **Por isso NÃO virou migração**, que foi o pedido literal. Migração roda sozinha no start,
  sobre a base de produção, sem ninguém ver a lista — e fusão não tem desfazer. Seria a única
  operação do projeto a juntar centenas de cadastros sem prévia, contra a regra que o Vincular
  segue desde que existe. O script faz o mesmo trabalho num comando, com `--simular` imprimindo
  cada grupo e os códigos de cada linha antes.
  ⚠️ **A razão de existir são os APELIDOS**: os códigos dos absorvidos passam a cair no
  principal. Sem isso a próxima nota que trouxesse o código de um deles não acharia o
  sobrevivente, o item cairia na fila de pendentes, e quem clicasse em "criar produto" recriaria
  o duplicado — o trabalho de juntar se desfazendo sozinho.
  ⚠️ **É a mesma `fundir` do botão Vincular**, repetida — nunca uma segunda implementação. O
  de-para, a baixa do que foi vendido e nunca saiu do estoque, o custo dos itens de venda e o
  arquivamento do absorvido são os mesmos.
  ⚠️ **O principal sai dos MESMOS critérios da tela** (`direcao`), dobrando o grupo dois a dois.
  O desempate final é o **menor id** — o cadastro mais antigo: num grupo não existe "a tela" para
  desempatar, e só um critério estável faz a prévia e a execução concordarem.
  ⚠️ **Grupo com DOIS que têm história não se junta**, e a lista diz isso em vez de omitir:
  unir dois razões exigiria reescrever movimento, e o custo médio resultante seria invenção. A
  recusa vem ANTES do laço — no meio dele o grupo ficaria pela metade e ninguém saberia dizer o
  que aconteceu com quais.
  ⚠️ **Só ATIVOS entram na lista.** O absorvido fica inativo com o mesmo nome; incluí-lo faria a
  lista nunca esvaziar, propondo de novo o que já foi feito.
  ⚠️ **O endpoint recebe os IDS que a pessoa viu, não o nome do grupo**: entre ver a lista e
  confirmar, uma importação pode ter criado mais um cadastro com aquele nome — e fundir o que
  ninguém olhou é o oposto do que a tela existe para fazer.
  ⚠️ **Uma transação por GRUPO no script.** Falhando um, os anteriores continuam feitos — que é
  um estado bom, não pela metade. É a lição do envio ao PDV, onde o laço inteiro numa transação
  só desfez 29 registros já gravados do outro lado.

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
  🔑 **E foi a inversão que quebrou a tela — só do lado do PDV** (03/09/2026, achado pelo dono:
  *"vincular dois produtos do Omie funciona, mas PDV com Omie diz que é o mesmo produto"*). A
  prévia resolve a direção e devolve `id_sai`; **quando ela inverte, `id_sai` É o cadastro em
  que a pessoa está** — e a tela mandava esse `id_sai` de volta como "o que sai". O pedido
  chegava em `POST /produtos/{X}/vincular {id_sai: X}`, e o servidor recusava com "Escolha dois
  cadastros diferentes" — com dois cadastros diferentes escolhidos.
  ⚠️ **A trava do servidor está certa e não se mexe nela**: era a tela que a acionava sem
  querer. Afrouxá-la esconderia o defeito em vez de corrigi-lo, e a suíte passou a cobrar que
  mandar o mesmo id dos dois lados continue sendo 400.
  ⚠️ **A tela manda o cadastro ESCOLHIDO**, nunca o `id_sai` resolvido — o servidor re-resolve a
  direção pela mesma `previa`, então o que a pessoa confirmou é o que acontece, venha o pedido
  de que lado vier. O id escolhido viaja DENTRO da prévia, não casado por índice na lista.
  ⚠️ **Entre dois cadastros do Omie não há inversão** (nenhum controla estoque a mais que o
  outro), e por isso aquele caminho sempre funcionou — o defeito só existia no par PDV × Omie,
  que é justamente onde o critério "controla estoque" decide.
  🔑 **As duas suítes provavam a INVERSÃO e nunca a FUSÃO a partir do lado invertido.** A de API
  parava na prévia; a de navegador funde de verdade, mas começa do lado do Omie — onde não há
  inversão. **Um caminho que nenhuma das duas percorre é onde o defeito mora**: as duas ganharam
  o caso que começa no cadastro que vai ser absorvido.
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

- ⚠️ **A linha de unidade de compra se remove ONDE ELA ESTÁ** (02/09/2026, pedido do dono).
  O rodapé dizia "remover a última": quem tinha caixa, fardo e palete e queria tirar o fardo
  apagava dois e redigitava um. Cada linha ganhou o seu `remover`, e ele some quando resta uma
  só — produto sem nenhuma unidade de compra não converte nota nenhuma.

- 🔑 **Reaproveitar "a primeira ficha homologada da base" caiu pela SEGUNDA vez** (02/09/2026),
  e agora num produto **`NA_HORA`** — que é produzido e baixado no mesmo instante da venda e por
  isso não se agenda. A primeira vez tinha sido num produto inativo. E o filtro não tinha como
  ser feito pela lista: **`/produtos` não devolve `modo_producao`**, então o teste "filtrava" por
  um campo que não vinha e o filtro era um no-op silencioso. A checagem passou a criar a
  **própria** ficha, sempre. **Precondição garantida, nunca suposta** — e cada suíte procura os
  registros DELA.

- ⚠️ **`produtos.id_local_padrao` é UM local, e local pertence a UMA loja** (31/08/2026). A
  produção usava esse local direto, com o `id_unidade` de quem estava produzindo: a filial que
  fizesse um molho cujo local padrão é a câmara da MATRIZ gravaria o movimento com a loja da
  filial e a prateleira da matriz. O saldo tem chave `(loja, local, produto)` — nascia uma
  **linha fantasma**, e o produto ficava num lugar onde ninguém o acha. `_local_desta_loja`
  aceita o local padrão só na loja dona dele; fora dela, cai no principal de quem produz.
  ⚠️ Não é o cadastro que está errado: o local padrão é a resposta certa na loja dele.

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

- 🔑 **Apagar uma categoria aqui poderia DUPLICAR o cardápio do cliente** (30/08/2026). O
  `codRefExterna` do grupo aponta para o id da nossa categoria; sem ela, o grupo sumia do
  `por_ref` (ninguém o reivindica) **e** do `por_nome` (que só recebe grupo sem dono) — e a
  categoria recadastrada com o MESMO nome não achava nada dos dois lados: a fila proporia
  **CRIAR**, e o botão Enviar criaria 30 grupos repetidos. Bastava apagar UMA categoria.
  Agora grupo de dono inexistente volta a ser adotável pelo nome, e a fixture tem um grupo
  órfão para a suíte cobrar isso sempre.

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

- **O fechamento congela a movimentação junto** (`cmv_movimentacao`): fechar o mês trava o
  relatório que explica o número, não só o número. Nome, código, categoria e setor vão
  **gravados** — renomear o produto depois não reescreve mês fechado. ⚠️ O congelado é do MÊS
  INTEIRO: um recorte dentro dele não vem congelado, e a resposta traz `mes_fechado` para a
  tela oferecer o mês completo em vez de deixar mandarem o parcial ao contador.

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

- ⚠️ **`<select>` alimentado por endpoint paginado é uma lista mentirosa — e MUDA.** O produto
  da ficha vinha de `/produtos?tipo=PRODUZIDO`: eram os 200 primeiros em ordem alfabética.
  Enquanto a casa tinha dezenas de pratos, ninguém notou; ao importar o cardápio do PDV (627
  itens), o prato recém-criado deixou de estar na lista — e o `<select>` não tem como dizer isso.
  A tela ficava certa, o produto simplesmente não estava lá, e o formulário recusava salvar sem
  explicar. Virou `BuscaCadastro`, que é o padrão da casa exatamente para isto. A regra de bolso
  do `<select>` continua valendo — **poucos por natureza** (categoria, setor, local, unidade) —,
  e produto nunca foi disso.

- ⚠️ **Rodar a suíte de API junto com a de navegador inventa falha.** As duas disputam a mesma
  API local; a de navegador espera tempos fixos, e sob a carga da outra a tela não pinta a
  tempo. Duas checagens do formulário de produto "falharam" assim e passaram sozinhas na
  rodada seguinte — meia hora atrás de um defeito que não existia.

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

## Armadilhas já pagas

- ⚠️ **Teste de tela que procura "o produto que contém X" cai no produto de outra rodada.**
  Produto com movimento não é apagado, vira INATIVO — então a base acumula um por rodada. O
  `verificar.mjs` clicava no primeiro item cujo nome continha `"Est tela"`, sem o marcador: a
  partir da segunda rodada a entrada de 10 kg ia para o produto de OUTRO teste, o desta ficava
  com saldo zero, e a checagem acusava a tela de não gravar. Duas checagens falhavam de forma
  intermitente e pareciam instabilidade do navegador. Vale a mesma regra das suítes de API:
  **cada teste procura o registro DELE**, pelo nome completo com marca de tempo.
  ⚠️ E `foto(fullPage)` no painel de CMV estoura o tempo do protocolo do Chrome — a página tem
  composição, ABC e margem, todas longas. Fotografar a tela do assunto, não a maior.

- Produto, fornecedor e categoria **não são apagados** quando já têm uso: viram inativos.
  Os testes contam com isso (reaproveitam em vez de recriar).

- **Um produto tem UMA unidade de estoque e N de compra** (20/08/2026, migração 015):
  `produto_unidades` (CX=12, FD=6, palete=480). `produtos.um_compra/fator_compra` continuam
  como reserva e são mantidos em dia pela unidade padrão. ⚠️ A ordem em `_fator_do_item`:
  de-para confirmado → **unidade da nota no cadastro** → fator do fornecedor → fator de
  compra. A unidade da nota vem antes do fornecedor porque casa pela UNIDADE; o número do
  fornecedor não diz em que embalagem.

- ⚠️ **CX, FD, PCT, BDJ e UN são todas grandeza UNIDADE com fator 1**: a conversão de
  grandeza diria que 1 CX = 1 PCT e engoliria a caixa de 12. `custos.converter()` agora
  **recusa** o par (devolve `None`) quando os dois lados são UNIDADE com o mesmo fator base —
  quem sabe o tamanho da caixa é o cadastro do PRODUTO. Dúzia continua convertendo: o fator
  12 é que separa "unidade de medida" de "nome de embalagem".

- ⚠️ **`produto_fornecedor.ultimo_preco` é POR UNIDADE DE ESTOQUE**, não pela embalagem: quem
  grava é o lançamento da nota (o `custo_aquisicao_unitario`, com frete dentro), e
  `custo_do_insumo` lê **sem dividir por fator** — dividir de novo aplicaria a caixa duas vezes
  (12,00 a caixa de 12 virava 0,08 o pacote). O lançamento faz UPSERT: com `UPDATE` só, a
  primeira compra de um insumo não gravava preço nenhum.

- ⚠️ **Salvar o produto pela tela não pode apagar o que a tela não manda**: `_gravar_fornecedores`
  apagava tudo e reinseria, levando junto `ultima_compra` e `ultimo_preco` — e com eles o custo
  de reserva de toda ficha de insumo sem entrada no estoque. Agora só sai da tabela quem saiu
  da lista.

- 🔑 **A conversão do código de fora, dita na tela do produto** (`codigos_externos.fator` +
  `fator_confirmado`, migração 054, cartão **Códigos de fora, e quanto cada um vale**,
  04/09/2026, pedido do dono). **O caso do AÇÚCAR DE CONFEITEIRO**: o fornecedor manda o pacote
  de 1 kg e o de 500 g como produtos DIFERENTES, com códigos diferentes — e aqui os dois são o
  mesmo produto. Feita a fusão, o código do de 500 g vira apelido do sobrevivente e a nota dele
  passava a entrar como **1 kg por unidade**: o estoque dobrava calado, e a diferença só
  apareceria na primeira contagem, como "ajuste de inventário".
  🔑 **Dois obstáculos reais apareceram ao construir, e os dois eram de projeto.**
  ⚠️ **Primeiro: a cascata IGNORA o fator 1 de propósito.** A coluna nasce com 1 e o lançamento
  da nota cria linhas com 1 só para guardar o último preço — aceitá-lo como informação fazia o
  vínculo recém-criado encobrir o `fator_compra` do produto (foi assim que o azeite de 5 L
  entrou certo na primeira nota e virou 1 L na segunda). Mas "por padrão 1" foi o pedido, e 1
  digitado por gente **é uma afirmação**. `fator_confirmado` separa o 1 automático do 1 dito.
  ⚠️ **Segundo, e maior: são DOIS espaços de nome de código**, e `_fator_do_item` só olhava um.
  `OMIE` é o código do produto **no fornecedor**, que vem na linha da nota e só existe quando
  alguém vinculou um item com "aprender"; `OMIE_PRODUTO` é o identificador do produto **no
  Omie**, que é o que a FUSÃO transforma em apelido. Sem o degrau novo, **produto fundido nunca
  poderia ter conversão por embalagem** — por construção, não por esquecimento.
  ⚠️ O degrau novo exige `fator_confirmado`: estes apelidos nascem em massa na fusão, todos com
  fator 1, e aceitá-los sem a marca faria cada fusão encobrir o `fator_compra` do produto — o
  defeito que a regra do "fator 1 não é resposta" existe para impedir.
  ⚠️ **Não recalcula nota já lançada.** O razão é append-only e a entrada antiga ficou com a
  quantidade que se acreditava na época; corrigir o passado é estorno, à mão.
  ⚠️ **`response_model` descarta chave não declarada**: o campo novo saía do SELECT e sumia na
  resposta até ser declarado em `models/produtos.CodigoExterno`. O sintoma foi o teste dizendo
  que a marca não gravava, quando ela gravava e não viajava.
  ⚠️ O `id_produto` entra no WHERE do UPDATE: sem ele, mandar o código de outro produto
  repontaria a conversão para o cadastro errado. E fator zero é recusado (422) — a nota inteira
  entraria como nada, e é erro de digitação plausível.

# Os módulos do Botané

> O sistema pensado por área de negócio, e não por camada. Serve para responder
> três perguntas que apareciam toda vez: **o que eu leio antes de mexer aqui**,
> **o que eu rodo depois** e **onde isto mora**.

⚠️ **Os módulos são organização, não pastas.** O código continua onde sempre
esteve — `api/routers/`, `api/services/`, `web/app/(app)/`. Mover arquivo para
pasta de módulo mexeria em dezenas de imports e na ordem de declaração de rota
(que já custou um bug neste projeto) sem entregar nada que este documento não
entregue.

🔑 **A memória segue os módulos**, um arquivo por módulo em
[`docs/memoria/`](docs/memoria/). Antes de mexer num módulo, leia o arquivo dele
— é lá que estão os "já tentei assim e quebrou".

| Módulo | Memória | Suítes |
|---|---|---|
| [Cadastros](#cadastros) | `docs/memoria/cadastros.md` | `cadastros`, `pessoas`, `produto_do_omie`, `vinculo`, `conversao`, `acucar_500g`, `utensilios`, `troca_de_unidade`, `openfoodfacts`, `kits` |
| [Produção](#produção) | `docs/memoria/producao.md` | `fichas`, `producao`, `rendimento`, `rendimento_por_local` |
| [Compras](#compras) | `docs/memoria/compras.md` | `notas`, `ean_das_notas` |
| [Custos](#custos) | `docs/memoria/custos.md` | `memoria`, `lotes` |
| [Estoque](#estoque) | `docs/memoria/estoque.md` | `estoque`, `ajustes`, `reprocessar`, `inventario_filtros`, `transferencias`, `alertas`, `lotes` |
| [Vendas](#vendas) | `docs/memoria/vendas.md` | `vendas`, `consumo_pessoa`, `consumo_periodo`, `pdv_legal` |
| [Administrativo](#administrativo) | `docs/memoria/administrativo.md` | `fundacao`, `sessao`, `senha`, `bloqueio_login`, `tokens_api`, `conector_claude`, `lojas_do_usuario`, `setor_do_usuario`, `omie`, `agenda_omie`, `agenda_fuso`, `email_prazo` |
| [CMV](#cmv) | `docs/memoria/cmv.md` | `cmv`, `grupos_cmv`, `ciclos`, `relatorios` |
| [Reservas](#reservas) | `docs/memoria/reservas.md`, `catalogos.md` | `reservas_config`, `reservas_disponibilidade`, `reservas_salao`, `reserva_site`, `catalogos`, `catalogo_produtos`, `produto_catalogo`, `publico` |
| _(transversal)_ | `docs/memoria/_transversais/` | `paginacao`, `exportacoes` |

---

## Cadastros

Produtos, pessoas e as tabelas de apoio — o que todo o resto referencia.

- **Rotas:** `produtos.py`, `fornecedores.py`, `cadastros.py`
- **Serviços:** `produtos_vinculo.py`, `kits.py`, `precos.py`, `troca_de_unidade.py`, `openfoodfacts.py`
- **Telas:** `produtos/`, `produtos/[id]/`, `produtos/duplicados/`, `produtos/ean-das-notas/`, `fornecedores/`, `cadastros/`
- **Permissões:** `cadastros.produtos`, `cadastros.fornecedores`, `cadastros.categorias`, `cadastros.setores`, `cadastros.locais`, `cadastros.unidades_medida`

⚠️ **"Pessoa" é `fornecedores`**, e a tabela não foi renomeada: desde a migração
055 ela guarda quem compra, quem trabalha e quem consome. `fornecedor = true`
distingue.
⚠️ **Mas quem reserva mesa pelo site NÃO mora aqui** (migração 082): fica em
`reserva_clientes`, do módulo Reservas. O esboço dizia o contrário, e a razão de
ter mudado está em `docs/memoria/reservas.md` — foi esta tabela que recebeu 888
clientes do Omie por engano, e o filtro por etiqueta existe para separá-los.

⚠️ **A unidade de estoque é o denominador de tudo** — trocá-la converte custo,
mínimo, máximo e as embalagens, e é recusada em produto que já tem razão.

## Produção

- **Rotas:** `fichas.py`, `producao_agenda.py`
- **Serviços:** `producao_agenda.py`, e o custo da ficha vive em `custos.py`
- **Telas:** `fichas/`, `producao/`
- **Permissões:** `fichas.visualizar`, `fichas.editar`, `fichas.homologar`, `fichas.custos`, `producao.agenda`

⚠️ **A ficha é versionada e o custo é congelado no uso** — recalcular depois
faria a produção de ontem mudar de valor sozinha.

## Compras

Notas de entrada: XML, digitação, conciliação e lançamento no razão.

- **Rotas:** `notas.py`
- **Serviços:** `nfe_xml.py`, `ean_das_notas.py`
- **Telas:** `compras/`, `compras/[id]/`, `compras/nova/`
- **Permissões:** `compras.notas`, `compras.conciliar`, `compras.lancar`

⚠️ **A nota só vira estoque no LANÇAMENTO**, não na importação: o XML entra como
documento, e é a conciliação item→produto que decide o que baixa.

## Custos

Tudo que decide quanto uma coisa custa.

- **Serviço central:** `custos.py` — **o único lugar que sabe quanto custa um insumo**
- **Também:** `precos.py`, `memoria_calculo.py`, o ajuste de custo em `ajustes.py`
- **Telas:** o cartão de custo em `produtos/[id]/custo.tsx`, os relatórios de memória

🔑 **A ordem de precedência é a da confiança:** custo médio do razão → último
preço do fornecedor → `produtos.custo_referencia`. O médio é o que a casa pagou;
a referência é o que outro sistema acha.

⚠️ **Custo em `numeric` com 6 casas, jamais float.**

## Estoque

Saldos, movimentos, ajustes, inventário e transferências entre lojas.

- **Rotas:** `estoque.py`, `ajustes.py`, `inventario.py`, `transferencias.py`, `alertas.py`
- **Serviços:** `estoque.py` (**a única porta de escrita no razão**), `ajustes.py`, `inventario_selecao.py`, `transferencias.py`, `alertas.py`
- **Telas:** `estoque/`, `ajustes/`, `inventario/`, `transferencias/`, `rede/`, `alertas/`
- **Permissões:** `estoque.saldos`, `estoque.entradas`, `estoque.saidas`, `estoque.perdas`, `estoque.ajuste`, `estoque.custo`, `estoque.inventario`, `estoque.inventario_criar`, `estoque.transferencias`, `estoque.transferencia_receber`, `estoque.retroativo`

⚠️ **`estoque_movimentos` é append-only.** Correção é estorno, nunca `UPDATE` ou
`DELETE` — e é por isso que trocar a unidade de um produto com razão é recusado.

## Vendas

- **Rotas:** `vendas.py`, `consumo.py`, `pdv.py`
- **Serviços:** `consumo_pessoa.py`, `consumo_periodo.py`, `services/pdv/`
- **Telas:** `vendas/`, `vendas/[id]/`, `vendas/lancar/`, `vendas/por-pessoa/`, `vendas/sem-vinculo/`, `consumo/`, `meu-consumo/`
- **Permissões:** `cmv.painel`, `cmv.relatorios`, `cmv.fechamento`, `consumo.periodos`

⚠️ **"Em aberto" é a venda SEM carimbo de período** (`vendas.id_consumo_periodo`),
nunca uma conta de datas.

⚠️ **Consumo de pessoa exige ciclo ABERTO** (08/09/2026) — venda de balcão, não.

🔑 **O PDV mora AQUI, e não em Integrações** (decidido em 09/09/2026). É a única
integração que não fica com as outras, e a razão é o que ela alimenta: o Omie
traz cadastro e nota, então pertence ao Administrativo; o PDV traz **venda**, que
é este módulo. Quem for corrigir um cupom que entrou errado abre Vendas, não
Integrações — e é por essa pergunta que o mapa se organiza, não pela natureza
técnica de "ser uma integração".

## Administrativo

Empresa, lojas, parâmetros, integrações e usuários.

- **Rotas:** `empresa.py`, `usuarios.py`, `tokens_api.py`, `oauth.py`, `mcp.py`, `papeis.py`, `autenticacao.py`, `omie.py`, `email_config.py`, `historico.py`, `inicio.py`
- **Serviços:** `services/omie/`, `agenda_integracao.py`, `email.py`, `segredos.py`, `senhas.py`, `oauth.py`, `mcp_ferramentas.py`
- **Telas:** `empresa/`, `lojas/`, `usuarios/`, `papeis/`, `integracoes/`, `perfil/`, `auditoria/`, `trocar-senha/`
- **Permissões:** `admin.empresa`, `admin.unidades`, `admin.usuarios`, `admin.papeis`, `admin.integracoes`, `admin.auditoria`, `integracao.omie`, `integracao.pdv`, `integracao.claude`

⚠️ **Credencial de integração é cifrada** (`segredos.py`) e **não se promove por
merge**: `api/.env` está fora do versionamento de propósito.

🔑 **Conector do Claude (MCP)** em `POST /mcp`, cadastrado no claude.ai pela URL, com
login OAuth (`oauth.py`) e a permissão `integracao.claude`. Cada conexão é uma linha de
`tokens_api` (migrações 074/075), **só de leitura**, que age como o usuário e se revoga em
Usuários ou em Perfil ▸ Claude. As ferramentas são rotas que já existem, chamadas por dentro
(`mcp_ferramentas.py`): 62 de leitura e, só para chave gerada à mão com "permite alterar",
7 de gravação (conciliar nota, criar e corrigir produto, fundir repetidos, lançar nota).
A auditoria marca o que veio por ali (`origem = claude`, migração 077). Detalhes na
memória do módulo.

## CMV

- **Rotas:** `cmv.py`
- **Serviços:** `cmv.py`, `cmv_grupos.py`, `periodos.py`, `relatorios.py`, `memoria_calculo.py`
- **Telas:** `cmv/`
- **Permissões:** `cmv.painel`, `cmv.relatorios`, `cmv.fechamento`, `cmv.grupos`, `cmv.reabrir`

🔑 **`CMV real = estoque inicial + compras − estoque final`**, e o teórico sai da
ficha. A diferença entre os dois é a variância, que é o número que interessa.

O painel é **uma tela de sete abas** (16/09/2026): `A conta` (a cascata da
subtração), `Quebra por <eixo>`, `Curva ABC`, `Margem por prato`,
`Movimentação`, `O que subiu de preço` e `Memória de cálculo`. O **recorte** fica
no cabeçalho e vale para todas: período, `escopo` (`loja` ou `empresa`) e `eixo`
(`loja`, `local`, `setor`, `categoria`, `grupo`, `produto`).
⚠️ **Percentual não se soma**: no escopo de empresa, food cost e cobertura de
ficha são REFEITOS dos totais — é por isso que a apuração devolve
`receita_com_custo` em reais e não só a cobertura em %.

---

## Reservas

- **Rotas:** `reservas.py`, `catalogos.py`, `publico.py` (o site do cliente)
- **Serviços:** `reservas.py`, `reservas_agenda.py` (a regra de disponibilidade),
  `reserva_clientes.py` (quem reserva pelo site, e o limite de abuso),
  `catalogos.py` (a capa), `catalogo_conteudo.py` (o cardápio montado por produtos)
- **Telas:** `reservas/agenda/`, `reservas/salao/`, `reservas/configuracoes/`,
  `catalogos/`
- **Permissões:** `reservas.ver`, `reservas.editar`, `reservas.configurar`,
  `catalogos.ver`, `catalogos.editar`

🔑 **É o primeiro módulo LIGADO POR LOJA** (`parametros.reservas_ligado`,
migração 068). Desligado, ele não existe: sem grupo no menu, com as rotas
recusando 409 e com as chaves `reservas.*` fora do catálogo de permissões.

⚠️ Construído até aqui: a **configuração** (três horas por dia — abre, fecha e
última reserva — e permanência por faixa), o **salão** (salões, mesas e a junta
entre vizinhas), a **regra de disponibilidade**, a **reserva pelo balcão** (com
ciclo de status, remarcar e bloqueios) e a **reserva pelo site**, com o cadastro
de quem marca.

🔑 **O SITE DO CLIENTE é o terceiro artefato da casa** (21/09/2026): `site/`,
um `index.html` estático que vai para `reservas.botanedeliecafe.com.br` e lê a
MESMA API por `/publico/{loja}/...` — o único router sem permissão.
Três portas: **Reserve sua Mesa**, **Cardápios** (os catálogos ativos, no ar e
com PDF) e **Entre em contato** (abre o WhatsApp da empresa).
⚠️ **O CORS volta a existir**: front separado em outro domínio precisa da origem
em `CORS_ORIGINS`, senão o site abre e não carrega nada.

🔑 **A reserva pelo site GRAVA** (migração 082, 21/09/2026): telefone primeiro,
cadastro de quem é novo (nome, gênero, cidade) em `reserva_clientes`, e a mesa
alocada pela MESMA `reservas_agenda.criar` do balcão.
⚠️ **São as duas únicas rotas públicas que ESCREVEM no sistema**, e por isso as
únicas com limite: 3 reservas vivas por telefone e 20 tentativas por hora por
origem — esta guardada como hash, não como endereço.
⚠️ **A porta nasce FECHADA** (`reserva_config.aceita_online`) e exige salão e
mesas cadastrados: sem eles não há horário a oferecer.
⚠️ **O telefone CONFIRMA o nome, não o revela** (`M••••• D•••••`) — sem isso o
site seria uma consulta aberta de telefone→nome, sem login nenhum na frente.

🔑 **O CATÁLOGO é daqui** (migração 079, 21/09/2026): a capa do que o site de
reservas apresenta — nome, **origem `PDF`** (o arquivo importado), período de
publicação e situação (`RASCUNHO` · `ATIVO` · `INATIVO`). **É só o cabeçalho.**
⚠️ De cada LOJA, e **vários ATIVOS convivem**: não há trava de um só nem de
períodos sobrepostos — quem publicar no site precisará de uma regra que escolha
entre eles, e ela não existe ainda.
⚠️ **`PDF` é arquivo, não `PDV`** — o módulo nasceu com a sigla errada.
🔑 **"No ar hoje" não é o mesmo que ATIVO**: um ativo com período vencido não
está publicado. Quem responde é o servidor, e a tela mostra em coluna própria.

🔑 **A regra de disponibilidade mora em UM lugar** (`reservas_agenda.py`): a tela
consulta a mesma que a gravação aplica. "Esgotado" depende do TAMANHO DO GRUPO, a
alocação é por MESA (não por soma de lugares), mesa inteira ganha da junta, e a
verificação e a gravação acontecem na mesma transação com trava por (loja, dia).

🔑 **`lugares` (o confortável) e `capacidade_max` (com a cadeira extra) são dois
números**: a alocação usa o máximo, os relatórios usam os lugares. E `maior_grupo`
existe para ser comparado com `teto_online` — teto maior que a maior junta é uma
promessa que o salão não cumpre.

---

## Transversal

O que não pertence a um módulo e atravessa todos. Fica em
[`docs/memoria/_transversais/`](docs/memoria/_transversais/).

| | |
|---|---|
| `padroes-de-ui.md` | paginação, modais, avisos, componentes |
| `exportacao-e-relatorios.md` | o catálogo de exportação (CSV/PDF) e seus filtros |
| `infra-e-deploy.md` | migrações, agendador, SMTP, App Platform |
| `geral.md` | lições de teste e o que não caiu em nenhum módulo |

- **Rotas:** `exportacoes.py`  ·  **Tela:** `exportacao/`
- **Serviços:** `exportacao.py`, `exportacao_catalogo.py`, `paginacao.py`

---

## Como usar isto

**Ao corrigir um defeito:** identifique o módulo pela tela ou pela rota, leia
`docs/memoria/<módulo>.md` **antes** de abrir o código, e rode as suítes daquele
módulo depois. A bateria inteira só antes de promover.

**Como rodar**, com a API de pé na 9200 e o web na 3100:

| O quê | Comando |
|---|---|
| Uma suíte | `python tests/smoke_<nome>.py` (da pasta `api`) |
| A bateria da API inteira | `python tests/rodar_tudo.py` (da pasta `api`) |
| A bateria de navegador | `node scripts/verificar.mjs` (da pasta `web`) |

⚠️ **Uma suíte de cada vez, nunca em paralelo** — elas escrevem na mesma base
local, e duas ao mesmo tempo disputam saldo e código. A falha que isso produz
não parece concorrência: parece um defeito de estoque.

**Ao implementar algo novo:** o módulo diz onde a rota, o serviço e a tela devem
nascer, e qual arquivo de memória recebe a decisão no fim. Toda decisão que
custou caro vira entrada lá — é isso que impede o próximo de repetir.

⚠️ **Um recurso que cruza módulos existe e é normal** — a colheita de EAN nasce
em Compras e escreve em Cadastros; o consumo por pessoa é Vendas mas usa Custos.
Nesse caso a decisão vai na memória do módulo **dono da regra**, com um ponteiro
no outro.

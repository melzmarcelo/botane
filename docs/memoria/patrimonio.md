# Patrimônio

> Os bens da casa — equipamentos e móveis —, um registro por item físico, e a manutenção deles.
> Leia antes de mexer neste módulo.

## O que já existe

- 🔑 **O módulo** (1.1.143, migração `139_patrimonio.sql`, 27/10/2026). Pedido do dono: *"Agora
  que temos o tipo de produto Patrimônio, gostaria de um processo para inventariar o
  patrimônio"*, com a planilha `Inventario_Equipamentos_Botane.xlsx` (uma aba por setor; 27
  equipamentos, 6 vindos dos locais de estoque e 21 "Sugestão", todos sem marca, série ou
  preventiva). Da proposta em 4 etapas, *"pode seguir com as etapas 1 e 2"*:
  1. cadastro com plaqueta de QR e importação da planilha;
  2. manutenção: plano de preventiva, histórico (preventiva e corretiva, com custo) e alertas.
  ⏳ Ficaram para depois: **3** a conferência patrimonial pelo QR (abrir por setor, ler as
  plaquetas, fechar com transferência/baixa) e **4** a ligação com as notas do Omie (item do
  tipo Patrimônio → cadastrar os bens) e a depreciação.

- 🔑 **Patrimônio NÃO é estoque.** O produto do tipo PATRIMONIO conta QUANTIDADE por local, a
  custo médio; a batedeira tem série, garantia, estado e história PRÓPRIOS. `bens` é um
  registro por item, e o produto entra só como "modelo" opcional (`id_produto`). **Nada aqui
  escreve no razão.** ⏳ Não foi decidido se os produtos do tipo Patrimônio deixam de controlar
  estoque (como o Serviço) — a proposta sugeriu, o dono não respondeu.

- 🔑 **O bem nasce do PRODUTO Patrimônio** (mesmo dia, pedido do dono: *"quando cadastrar um
  novo bem, o equipamento poderia ser um produto patrimônio, onde teria a opção de busca por
  produtos deste tipo. E caso entre um produto novo como patrimônio, o usuário deverá
  cadastrar ele como um novo bem — aí vinculamos todo o sistema"*, e *"pode seguir com as suas
  sugestões também"*).
  - `bens.id_produto` só aceita produto do tipo **PATRIMONIO** (400 nomeado: reclassifique ou
    deixe sem produto). Na ficha, o campo "Produto (Patrimônio)" é a busca da casa com
    `tipo=PATRIMONIO`.
  - 🔑 **O que entrou e não virou bem** (`GET /patrimonio/a-cadastrar`): a régua é o SALDO do
    produto na loja contra os bens ligados a ele (fora os baixados) — 3 no estoque e 1 bem =
    faltam 2. Saldo quebrado arredonda para baixo. Aparece no quadro "Entrou como Patrimônio
    e falta cadastrar" da lista (`#a-cadastrar`) e no alerta `patrimonio.a_cadastrar`
    (atenção, conta os ITENS que faltam).
  - 🔑 **O Novo bem vem preenchido da ÚLTIMA ENTRADA** (`GET /patrimonio/do-produto/{id}`,
    `ENTRADA_NF`/`ENTRADA_MANUAL` mais recente): nome, setor do produto, o local com mais saldo,
    data, nota (número da nota do Omie, senão o documento), fornecedor (o cadastrado, senão o
    emitente) e o custo unitário como valor de compra — ⚠️ **o valor só para quem tem
    `estoque.saldos`**. Na tela, só os campos VAZIOS são preenchidos.
  - O **cadastro do produto** Patrimônio ganhou o quadro "Bens deste produto"
    (`produtos/[id]/bens.tsx`, aba Principal): os bens, o aviso de quantos faltam e o
    "Cadastrar bem" (`/patrimonio/novo?produto=`).
  - A **planilha** liga pelo "Código do produto" (exato) ou pelo "Produto" (nome, sem acento
    nem maiúscula; nome repetido pede o código); o relatório exporta as duas colunas.

- 🔑 **O código da plaqueta é fixo e não diz o setor** (`PAT-0001`, da sequência
  `bens_codigo_seq`). A planilha usava `ADM-01`/`BAR-02`: quando o bem muda de setor, um código
  desses mente ou precisa mudar — e a plaqueta colada no equipamento perde o sentido. O código
  da casa fica como **apelido** (único por loja, sem diferença de maiúscula).

- 🔑 **A próxima preventiva e o status são CALCULADOS na consulta** (`_SELECT` em
  `services/patrimonio.py`): próxima = última + intervalo (`make_interval(months => …)`);
  status `VENCIDA` / `VENCE_30` (janela `JANELA_DIAS = 30`, a da planilha) / `EM_DIA` /
  `SEM_REGISTRO` (tem plano, falta a última) / `SEM_PLANO` / `FORA`. Gravados, mentiriam no dia
  em que alguém corrigisse o intervalo.
  ⚠️ `FORA` = **A confirmar, Desativado e Baixado**: não cobram preventiva nem entram nos alertas.

- 🔑 **Situações**: `A_CONFIRMAR` (a "Sugestão" da planilha, que ninguém conferiu se existe),
  `EM_USO`, `EM_MANUTENCAO`, `PARADO`, `DESATIVADO`, `BAIXADO`.
  ⚠️ **Baixa pede motivo** (modelo e serviço). ⚠️ **Bem com manutenção não se apaga** (409):
  apagar é para cadastro errado; o que existiu se baixa, para o histórico ficar. ⚠️ A lista e
  o resumo **escondem o baixado** sem filtro; `situacao=BAIXADO` o traz.

- 🔑 **Manutenção** (`bem_manutencoes`): preventiva ou corretiva, data, quem fez, custo, o que.
  - A **preventiva mais nova que a última anda o plano** (`ultima_preventiva`); uma mais velha
    não volta a data para trás.
  - ⚠️ **Data no futuro é 400**: o registro é do que FOI feito.
  - `situacao_depois`: a corretiva que consertou devolve o bem ao uso no mesmo gesto. Baixa
    não passa por aqui (precisa do motivo).
  - ⚠️ **Apagar a preventiva que marcava a "última"** volta a última para a preventiva anterior
    (ou nulo) — senão o plano contaria de uma visita que não aconteceu.
  - Não é razão: um registro errado se apaga.

- 🔑 **O equipamento que É um local de estoque** (a câmara fria): `id_local` aponta para o
  local, e a ficha diz quantos produtos com saldo estão dentro dele (o valor só para quem tem
  `estoque.saldos`). Com o bem parado ou em manutenção, a tela avisa.

- 🔑 **Alertas** (`services/alertas.py`, chaves em `routers/alertas.py` → `patrimonio.ver`):
  `patrimonio.critico_parado` (crítico: criticidade alta em manutenção ou parado),
  `patrimonio.preventiva_vencida` (atenção), `patrimonio.preventiva_30` (aviso). Cada um leva à
  lista já filtrada pela URL (`?preventiva=VENCIDA`, `?criticidade=ALTA&situacao=PARADOS` —
  `PARADOS` é o atalho da tela para as duas situações).
  ⚠️ O Início mostra os alertas da loja SEM filtrar por permissão (comportamento anterior, que
  vale para todos os alertas); a tela /alertas filtra.

- 🔑 **Plaqueta** (`GET /patrimonio/plaquetas.pdf?ids=`, `patrimonio.cadastrar`): **o mesmo rolo e
  a mesma impressora das etiquetas de validade** (`etiquetas.config` / `pagina_mm`, e o cabeçalho
  `X-Impressao`), A4 = folha 3 × 7. QR à esquerda → `WEB_URL/patrimonio/b/<código>`; código
  grande, equipamento, setor · local, série. A tela de leitura troca a loja do seletor para a
  do bem quando difere (recarrega a página, como o seletor).

- 🔑 **Importação** (`POST /patrimonio/importar`, `services/patrimonio_planilha.py`), com as regras
  da reclassificação: prévia antes (`simular=true` padrão), recusa por linha nomeada, **célula
  vazia não mexe**, setor e local pelo NOME (sem acento nem maiúscula), local `OUTRO` = sem local.
  - Lê o **.xlsx da casa** (`services/planilha_xlsx.py`: ZIP + XML da biblioteca padrão, sem
    `openpyxl`; recusa DTD/entidade e ZIP que descompacta para mais de 60 MB) e o **CSV
    exportado** do relatório `patrimonio`.
  - ⚠️ **O cabeçalho é procurado em cada aba** (coluna "Equipamento" + outra conhecida); abas sem
    ele (Resumo, Como usar, Listas) são puladas; linha sem equipamento é linha vazia do modelo.
  - O **setor** vem da linha "Setor no sistema Botané: X · Loja: …" acima do cabeçalho; sem ela,
    do nome da aba. Coluna Setor na linha (o CSV exportado) vence.
  - ⚠️ **Data do Excel vem como número** (série desde 30/12/1899) — `data_do_excel` aceita isso,
    `15/03/2022`, `15/03/22` e ISO.
  - **Como a linha acha o bem**: código `PAT-…` → pela plaqueta (inexistente = recusa); outro
    código → apelido. É o que faz a segunda importação ATUALIZAR, não duplicar.
  - ⚠️ **O NOME da aba é só palpite de setor**: vale se existir setor com aquele nome e não
    recusa se não existir (achado pela suíte: uma aba "Bens" recusava todas as linhas). A linha
    "Setor no sistema" e a coluna Setor recusam.
  - **"Sugestão"** entra como `A_CONFIRMAR` (ou fica de fora com `incluir_sugestoes=false`).
  - ⚠️ **Linha vazia seguida de um título de uma célula só encerra a tabela**: o CSV exportado
    traz, depois dos bens, o quadro "Por setor" — sem parar, os totais dele viravam
    equipamentos chamados "Criticidade alta" (achado pela suíte, 27/10/2026).

- **Relatórios** (catálogo de exportação): `patrimonio` — **as mesmas colunas e nomes da
  planilha da casa** (a planilha baixada volta pela importação sem mudar nada — a suíte confere);
  no PDF, as que cabem numa folha deitada; anexo "Por setor" (a aba Resumo). E
  `patrimonio-manutencoes` — cada registro com quem fez e custo, anexo por setor; ⚠️ **sem
  datas, os últimos 12 meses** (preventiva é semestral/anual; o mês corrente mostraria nada).

- **Conector**: `patrimonio` (com `id_produto`), `resumo_do_patrimonio`, `bem_patrimonial`,
  `patrimonio_a_cadastrar` (leitura) e
  `registrar_manutencao` (escrita, confirmar antes).
- **Permissões** (139): Administrador, Gerente e Conferente/Estoque tudo; Cozinha e Salão
  `ver` + `manutencao` (são quem vê o equipamento parar e recebe o técnico); Contador `ver`.
  ⚠️ Concedidas na própria 139 (ver 091).
- **Limpeza**: `bem_manutencoes` e `bens` em OPERACAO (`limpar_dados.py`) — o bem aponta
  para o produto, o local e o usuário.
- Cobertura: `smoke_patrimonio.py` (50) e `verificar-patrimonio.mjs` (16).
  ⚠️ **A limpeza NÃO zera o saldo do produto de teste** (ele fica desativado com estoque): o
  acerto para zero é uma saída de Patrimônio no período, e foi ele que expôs a quebra do CMV
  contando o tipo fora do CMV (ver `cmv.md`, 1.1.144). O `smoke_cmv` já desconta os inativos.

## ⏳ Decidido sem o dono — validar

1. O estoque dos produtos do tipo Patrimônio continua como está (não virou "sem estoque") —
   e é justamente o saldo que diz quantos bens faltam cadastrar. Cadastrar o bem NÃO baixa
   o estoque.
2. Plaqueta para qualquer bem cadastrado — sem corte por valor.
3. Sem depreciação (só o valor de compra guardado).
4. Assistência técnica e fornecedor da compra são TEXTO (como na planilha), não um vínculo
   com Pessoas.
5. Os alertas são da loja inteira, não só do setor de quem olha.

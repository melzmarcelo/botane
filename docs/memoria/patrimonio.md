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
  A **3**, a conferência pelas plaquetas, e a **4**, o valor e a depreciação, vieram em
  28/10/2026 (ver abaixo) — a proposta está inteira. A ligação com as notas — o item do tipo Patrimônio que entra vira
  pendência de cadastrar o bem — já veio junto da 1, a pedido do dono.

- 🔑 **A CONFERÊNCIA pelas plaquetas** (1.1.146, migração `140_conferencia_patrimonio.sql`,
  `services/patrimonio_conferencia.py`, 28/10/2026 — *"pode seguir com a etapa 3 do
  patrimônio"*). Abrir (um setor ou a loja inteira) → ler → fechar.
  - **Não é inventário de estoque**: confere PRESENÇA de cada bem, não quantidade; nada toca o
    razão.
  - 🔑 **A lista de esperados é FOTOGRAFIA da abertura** (`bem_conferencia_itens.esperado`).
    Baixado não entra; desativado e "A confirmar" entram (o segundo é justamente o que a
    conferência confirma). Bem lido que não estava na lista entra `esperado = false` — o "de
    outro setor".
  - ⚠️ **Uma aberta por setor, e loja inteira × setor não se sobrepõem** (índice único parcial
    + checagem no serviço): o mesmo bem em duas listas abertas não saberia onde contar.
  - **Ler** aceita o LINK do QR (o leitor USB e a câmera devolvem a URL inteira — o código
    sai pelo padrão `PAT-\d+`), o código digitado e o **apelido** da casa. Segunda leitura =
    "já lido", não conta duas. Bem de outra loja e bem BAIXADO são 409 nomeados.
  - 🔑 **Três jeitos de ler, uma rota**: câmera DENTRO da tela (`components/leitor-qr.tsx`,
    `BarcodeDetector` — Chrome do Android; sem biblioteca no pacote); leitor/teclado; e a
    câmera COMUM do celular (iPhone): a plaqueta abre `/patrimonio/b/…`, e se ESTE aparelho
    está marcado como conferindo (`localStorage botane.patrimonio.conferindo`, marcado ao abrir
    a tela da conferência, limpo ao fechar/cancelar) e a conferência aberta é a que procura o
    bem (`conferencia_aberta` em `GET /patrimonio/codigo/…`), a leitura conta ali. Em outro
    aparelho a plaqueta continua abrindo a ficha.
  - **Fechar**: lido e esperado → CONFERIDO (`bens.conferido_em` = hoje; "A confirmar" → "Em
    uso", desligável); lido de fora → TRANSFERIDO para o setor (o local sai quando é de outro
    setor — "Cozinha · Bar" mentiria); não lido → **MANTIDO por padrão** (NAO_ENCONTRADO) ou
    BAIXADO, bem a bem, com motivo (vazio = "Não encontrado na conferência nº X"). ⚠️ Manter é
    o padrão: o equipamento no conserto não pode sumir porque não estava na hora. Baixar o que
    FOI lido é 400. **Cancelar** não muda nenhum bem.
  - ⚠️ **Conferência FECHADA é história**: o bem que passou por uma não se apaga (409, como o
    com manutenção), e o setor que teve conferência é DESATIVADO em vez de apagado
    (`routers/cadastros.py`, senão a chave estrangeira dava 500).
  - **Folha da conferência** (`/exportar/conferencia-patrimonio/{id}.pdf|csv`, botão no
    cabeçalho): aberta, lista o que falta (dá para conferir no papel); fechada, o resultado de
    cada bem, para assinar. O relatório `patrimonio` ganhou a coluna **Conferido em** (só
    exportação: a importação ignora — quem escreve é a conferência).
  - Leitura não vai para a auditoria (dezenas por volta; o item guarda quem e quando); abrir,
    fechar e cancelar vão.
  - **Permissão** `patrimonio.conferir` (Administrador, Gerente, Conferente) — o fechamento
    transfere e baixa. Quem só vê acompanha e baixa a folha.
  - Conector: `conferencias_do_patrimonio`, `conferencia_do_patrimonio` (leitura).
  - Cobertura: `smoke_patrimonio_conferencia.py` (31) e a seção 7 do `verificar-patrimonio.mjs`
    (leitura pelo link "digitado", a plaqueta pela câmera comum contando, fechar com baixa).
    ⚠️ O roteiro do navegador não consegue apagar o bem conferido: deixa-o BAIXADO e o setor
    desativado (a suíte da API apaga por SQL).

- 🔑 **O VALOR e a DEPRECIAÇÃO** (1.1.147, migração `141_depreciacao_patrimonio.sql`,
  `services/patrimonio_valor.py`, 28/10/2026 — *"pode seguir com a etapa 4 do patrimônio"*;
  da proposta: "valor patrimonial por setor e depreciação, só como relatório").
  - 🔑 **Só relatório, e CALCULADO** — nada é gravado mês a mês e nada vai para o CMV. Mudar
    a vida útil ou a data de compra muda também o relatório de ontem (o errado era o de antes).
  - **Linear, por mês INTEIRO** (o método da Receita): cota = compra ÷ meses da vida útil; o
    mês conta no "aniversário" da compra (de 15/01 a 14/02 é zero). Sem valor residual: ao fim
    da vida, zero. Centavos arredondados na acumulada, nunca somando cotas arredondadas.
  - **`bens.vida_util_anos`** (1 a 50), **vazia = 10 anos** (`VIDA_UTIL_PADRAO`, o da Receita
    para máquinas, equipamentos e móveis). ⚠️ Não se grava o padrão no bem: esconderia quem
    foi escolhido de propósito. A ficha e o relatório dizem "(padrão)".
  - 🔑 **`bens.data_baixa` é de GATILHO** (`tg_bem_data_baixa`, o segundo do projeto, pela
    razão do 036): a baixa entra pela ficha, pelo fechamento da conferência, pela planilha e
    pelo conector. Baixado sem data → hoje; saiu do baixado → a data some. A ficha deixa
    corrigir (não no futuro). Os já baixados receberam `atualizado_em::date`.
  - **Quem conta no valor numa data**: o "A confirmar" NÃO (ninguém viu se existe); o
    desativado SIM; o baixado até a data da baixa ("Baixado depois (dd/mm)"); o comprado
    depois da data, não. **Sem data de compra** entra pelo valor de compra, sem depreciar
    (marcado); **sem valor**, conta como bem e não soma.
  - A mesma conta (`calcular`) na tela **Patrimônio ▸ Valor** (`/patrimonio/valor`: data,
    setor, totais, por setor e bem a bem), na ficha (`bem.valor`, "Valor atual" ou "Valor na
    baixa") e no relatório **`patrimonio-valor`** (filtros data e setores; anexo por setor).
    O relatório `patrimonio` ganhou **Vida útil (anos)**, **Valor atual** e **Data da baixa**;
    a importação lê a vida útil (as outras duas são só leitura).
  - Permissão: `patrimonio.ver` (o valor de compra já aparecia no resumo para quem vê).
  - Conector: `valor_do_patrimonio`.
  - Cobertura: `smoke_patrimonio_valor.py` (36) e a seção 8 do `verificar-patrimonio.mjs`.

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
3. ~~Sem depreciação~~ → veio na etapa 4 (141): linear, vida útil padrão de 10 anos, sem
   valor residual; o "A confirmar" fica fora do valor.
4. Assistência técnica e fornecedor da compra são TEXTO (como na planilha), não um vínculo
   com Pessoas.
5. Os alertas são da loja inteira, não só do setor de quem olha.
6. (Conferência, 28/10) Não lido é MANTIDO por padrão; a baixa é escolha bem a bem.
7. (Conferência) O "A confirmar" visto vira "Em uso" no fechamento (dá para desligar).
8. (Conferência) Sem alerta de "bem nunca conferido" nem de conferência esquecida aberta.

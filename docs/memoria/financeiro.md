# Financeiro

> Contas a pagar (e, no menu, as contas a receber, cuja memória continua em `vendas.md`).
> Leia antes de mexer neste módulo. Estudo em `docs/financeiro-estudo.md`.

## O que já existe

- 🔑 **Contas a pagar, etapa 1** (1.3.23, migração 163, 24/11/2026, pedido do dono: *"vamos criar
  um novo módulo financeiro… um contas a pagar… neste primeiro momento suprir a organização de
  pagamentos e agendamentos de funcionários freelancer, mas a ideia é englobar tudo"*).
  Tela `financeiro/pagar/` (page + `janelas.tsx`), `routers/contas_pagar.py`,
  `services/contas_pagar.py`, tabelas `contas_pagar` e `financeiro_categorias`, relatórios
  `contas-pagar` e `pagamentos-pessoa`.
  - **Grupo Financeiro no menu** (seção Gestão, depois do CMV): Contas a receber saiu de Vendas
    sem mudar de endereço (`/receber`).
  - 🔑 **Situações**: A_PAGAR → AGENDADO → PAGO, e CANCELADO. Estornar a baixa volta a AGENDADO
    se havia `agendado_para`, senão a A_PAGAR. Transição errada = 409 com a frase.
  - 🔑 **Baixa automática**: AGENDADO com `baixa_automatica` e data chegada vira PAGO **na data
    agendada**, `baixado_automaticamente = true`, `pago_por` nulo. Roda no laço
    (`contas_pagar.laco`, meia hora, em `main.py`) E antes de cada leitura da tela/resumo
    (`baixar_e_registrar`), com auditoria. ⚠️ Não confere o banco: o resumo mostra "baixadas
    sozinhas hoje", e o estorno de uma automática desliga a baixa automática dela (quem estornou
    sabe que o banco não pagou).
  - **A pessoa é do cadastro de Pessoas** (`fontePessoas`, todas, não só fornecedores). O cadastro
    ganhou **chave Pix** (`fornecedores.chave_pix`); o **CPF mora no `cnpj`** (só dígitos) e a tela
    usa `mascaraDocumento` (até 11 dígitos é CPF).
  - **Equipe do dia** (`POST /contas-pagar/equipe`): uma conta por pessoa, mesmo `lote`, tudo ou
    nada; o valor e a função vêm do último lançamento da pessoa (`/pessoa/{id}/ultimo`).
  - **Pagar**: várias de uma vez (cada uma pelo seu valor); valor diferente só com UMA conta.
    "Pagar todas" de uma pessoa no modo agrupado usa um comprovante só.
  - 🔑 **Comprovante** (foto ou PDF) em `arquivos` (banco), por `POST /contas-pagar/comprovante`
    (várias contas, troca o anterior, apaga o velho se ninguém mais aponta) e SÓ sai por
    `GET /contas-pagar/{id}/comprovante` autenticada. A tela abre num iframe (foto ou PDF).
  - **Permissões**: `financeiro.pagar_ver`, `financeiro.pagar_lancar` (lançar, corrigir, agendar,
    cancelar, categorias), `financeiro.pagar_baixar` (pagar, comprovante, estornar) — Administrador
    e Gerente. A Cozinha não vê.
  - ⚠️ **Campo de valor livre usa `textoParaNumero`, NUNCA `moedaParaNumero`**: esta trata o
    texto como máscara de centavos, e "120" virava R$ 1,20 (a bateria pegou na equipe do dia; o
    mesmo erro estava no contado do caixa da 1.3.21 e foi corrigido junto).
  - ⚠️ No modo "agrupar por pessoa" o nome fica no cabeçalho do grupo, não na linha.
  - ⚠️ A janela do comprovante não fecha com Escape quando o foco está dentro do iframe (a tecla
    vai para o documento dele); o botão fechar funciona.
  - Não entra no CMV nem no estoque.
  - Cobertura: `smoke_contas_pagar.py` (37) e `verificar-contas-pagar.mjs` (13).

- 🔑 **Painel, etapa 2** (1.3.24, 25/11/2026, sem migração). Tela `financeiro/painel/` (primeiro
  item do grupo, mesmas três chaves), `GET /contas-pagar/painel?de&ate` (sem período = o mês
  corrente; período invertido ou maior que um ano = 422) e `contas_pagar.painel`, que o relatório
  `painel-financeiro` também usa (um só cálculo para a tela e o papel).
  - 🔑 **Dois recortes**: "pela frente" NÃO depende do período (resumo, os próximos 14 dias dia a
    dia, as baixas automáticas dos últimos 7 dias para conferir no banco); "o período" separa
    **pago (pela data do pagamento) × em aberto (pelo vencimento)** — a mesma regra da tela de
    contas — por categoria, pessoa e forma. Cancelada não entra em nada.
  - Os números e os dias levam para Contas a pagar já filtrada (aba e `de`/`ate` na URL).
  - ⚠️ O relatório põe as categorias no quadro e pessoa, forma, próximos dias e baixadas sozinhas
    nos anexos — que o `/exportar/{rel}/dados` não traz; o teste chama `_painel_financeiro` direto.
  - Cobertura: `smoke_contas_pagar.py` (50) e `verificar-contas-pagar.mjs` (18).

- 🔑 **Contas fixas e parcelas, etapa 3** (1.3.27, migração 167, 25/11/2026, pedido do dono: *"pode
  seguir com a etapa 3 do financeiro"*). `services/contas_fixas.py`, tabela `contas_fixas`,
  colunas `contas_pagar.id_conta_fixa`, `parcela`, `parcelas`; janela `financeiro/pagar/fixas.tsx`
  (botão "Contas fixas", para quem vê; editar e encerrar só com `pagar_lancar`); relatório
  `contas-fixas`.
  - 🔑 **Conta fixa = molde do mês** (pessoa, categoria, o que é, valor, dia do vencimento, primeiro
    e último mês, antecedência). A conta de cada mês nasce em `contas_pagar` quando
    `vencimento - antecedência <= hoje`, com competência no dia 1º do mês e a descrição
    "Aluguel — nov/2026". Dia 31 em mês curto vence no último dia (`somar_meses`).
  - 🔑 **Idempotência do banco** (regra 8): índice único `(id_conta_fixa, competencia)` e
    `ON CONFLICT DO NOTHING`. A geração roda dentro de `baixar_e_registrar` (o laço de meia hora E
    toda leitura da tela), ANTES da baixa automática, com auditoria `gerar_conta_fixa`.
  - ⚠️ **Nunca volta para trás do último mês gerado**: começa no mês seguinte a ele (ou no início,
    se for depois). Cancelar a conta de um mês não a faz nascer de novo (o mês segue ocupado).
    Início no passado gera os meses atrasados de uma vez (foi o que a pessoa pediu).
  - ⚠️ **Mudar a conta fixa vale para os meses que ainda não nasceram**; a gerada se corrige nela.
    Encerrar para de gerar; com "cancelar as em aberto", cancela as geradas que vencem de hoje em
    diante (as atrasadas ficam: são dívida). Reativar volta a gerar **a partir deste mês** (o
    início vai para o mês corrente): os meses encerrados não nascem atrasados.
  - **Débito automático** (`agendar`, exige `forma`): nasce AGENDADA para o vencimento com baixa
    automática — então uma conta fixa de débito com início no passado nasce e é baixada na mesma
    passada. **Valor variável** (luz, água): a observação avisa "valor previsto: corrija quando a
    fatura chegar".
  - 🔑 **Parcelar**: `POST /contas-pagar` com `parcelas` 2–60; `valor` é o TOTAL, rateado em
    centavos com a sobra nas primeiras (`contas_pagar.ratear`, espelhado em `lib/contas-pagar.ts`
    para a prévia da janela); o `vencimento` é o da 1ª e as outras um mês depois cada; mesma
    competência; lote `PC…`. Corrigir mexe numa parcela só. A linha e o relatório mostram
    "parcela 2/3" e "conta fixa".
  - ⚠️ O teste simula datas futuras com `contas_fixas.gerar(hoje=..., so_ids=[...])`: sem
    `so_ids`, uma data de 2031 geraria anos de contas para as contas fixas DE VERDADE da base.
    O roteiro do navegador encerra a conta fixa de teste no fim, senão ela gera todo mês.
  - Cobertura: `smoke_contas_fixas.py` (47) e `verificar-contas-pagar.mjs` seção 8 (25 no total).

- 🔑 **Fluxo de caixa, etapa 4** (1.3.28, 25/11/2026, sem migração, pedido do dono: *"pode seguir
  com a etapa 4 do financeiro"*). `services/fluxo_caixa.py`, `GET /contas-pagar/fluxo?de&ate&previsao&saldo_inicial`
  (mesmas três chaves; sem período = dia 1º do mês até hoje + 30; invertido ou > 400 dias = 422),
  tela `financeiro/fluxo/` (no menu entre Painel e Contas a receber), relatório `fluxo-caixa`.
  🔑 **Nada é gravado**: tudo é calculado do que as outras telas registram.
  - **Entra**: vendas pelas finalizadoras (160), dinheiro LÍQUIDO do troco; a venda sem forma
    entra pelo total como "não informado" (e o aviso diz quantas); lote de cobrança RECEBIDO na
    data da baixa. **Sai**: pago (data do pagamento, valor pago); em aberto pela data agendada ou
    pelo vencimento; a conta fixa que ainda NÃO nasceu, no vencimento do mês (o cálculo roda
    depois de `baixar_e_registrar`, então o mês nascido não conta duas vezes); taxa de cartão
    estimada pela taxa da loja (161).
  - ⚠️ **Fica de fora**: venda com pessoa (é contas a receber: entra quando o lote é recebido —
    contar as duas dobraria), consumo interno, cancelada, pagamento em VALE (o dinheiro entrou
    quando o vale foi vendido), lote em PERMUTA ou FOLHA. Lote em cobrança e consumo sem lote não
    têm data: aparecem só como "a receber sem data".
  - ⚠️ **O atrasado vai para HOJE** (é o primeiro dia em que ainda pode sair); período que não
    inclui hoje não o mostra. ⚠️ **O cartão conta no dia da venda**, não no depósito (a casa não
    registra o prazo de cada maquininha — possível etapa futura).
  - 🔑 **Previsão de vendas** (liga e desliga, padrão ligada): média do mesmo dia da semana nas 4
    semanas antes de hoje, só nos dias depois de hoje; a taxa dela é a taxa média real da loja.
  - **Saldo inicial**: o do banco não está no sistema; a pessoa digita (fica na URL). Sem ele o
    acumulado parte de zero, e o "menor saldo" diz isso. O relatório sempre parte de zero.
  - Cobertura: `smoke_fluxo_caixa.py` (42, por DIFERENÇA numa janela de 2032 — a base pode ter
    contas fixas de verdade projetando lá; zera as taxas da loja durante o teste e devolve) e
    `verificar-contas-pagar.mjs` seção 9 (34 no total).

## Etapas seguintes

As quatro do estudo estão feitas. Ideias que ficaram: prazo de depósito do cartão por forma no
fluxo; integrar com o financeiro do Omie, se a casa usar.

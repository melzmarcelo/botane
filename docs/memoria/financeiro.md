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

## Etapas seguintes (do estudo)

3. Recorrência e parcelas. 4. Fluxo de caixa (a receber × a pagar).

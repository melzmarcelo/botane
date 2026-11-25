# Módulo Financeiro — estudo (contas a pagar)

🔑 **Pedido do dono (24/11/2026):** *"vamos criar um novo módulo financeiro. Vamos ter o contas a
receber, que já existe, e vamos criar um contas a pagar, onde poderemos realizar lançamentos a
serem pagos. Neste primeiro momento a ideia é suprir a organização de pagamentos e agendamentos
de funcionários freelancer, mas a ideia é englobar tudo. Selecionar a pessoa, a discriminação do
que é, vencimento, se já foi agendado, se já foi pago; caso agendado, na data pode haver a baixa
automática. Anexo do comprovante."*

Estado: **etapa 1 construída em 24/11/2026** (1.3.23, migração 163), com as oito decisões da
seção 3 (o CPF entrou no campo de documento que já existia). **Etapa 2 (painel) construída em
25/11/2026** (1.3.24, sem migração). **Etapa 3 (contas fixas e parcelas) construída em
25/11/2026** (1.3.27, migração 167). O que foi decidido está em `docs/memoria/financeiro.md`; a
etapa 4 segue por fazer.

## 1. O que já existe e serve

| Já existe | Onde | Uso aqui |
|---|---|---|
| Contas a receber (lotes de cobrança do consumo, baixa, estorno da baixa) | `receber.py`, tela `/receber` | Vai para o grupo Financeiro, sem mudar nada por dentro |
| Cadastro de **Pessoas** (fornecedor, funcionário, sócio) | `fornecedores`, tela `/fornecedores` | A pessoa a quem se paga, o freelancer inclusive |
| Anexo guardado no banco, servido por rota autenticada | `arquivos.py`, recebimento de notas (162) | O comprovante (foto ou PDF) |
| Agendadores que rodam sozinhos no servidor (Omie, PDV, WhatsApp) | `main.py`, `asyncio` | A baixa automática do agendado |
| Formas de pagamento da casa | finalizadoras (160) | O vocabulário de "pago em Pix, dinheiro…" |

⚠️ O cadastro de Pessoas **não tem chave Pix nem CPF**. Para pagar freelancer, a chave Pix é o
dado que mais se procura no dia.

## 2. Como funciona

Cada **lançamento** é uma conta a pagar: pessoa, o que é (categoria e descrição), valor, data de
competência (o dia do trabalho ou do serviço) e vencimento. Ela passa por quatro situações:

```
A PAGAR ──agendar──▶ AGENDADO ──na data, sozinho (ou à mão)──▶ PAGO
   │                    │                                         │
   └──────────────── cancelar                       estornar a baixa volta ao estado anterior
```

- **Agendar** = "o pagamento já está programado no banco para tal dia, por tal forma".
- **Baixa automática**: todo dia, o agendado cuja data chegou vira PAGO, com a data agendada e a
  marca "baixa automática". Dá para desfazer (estornar a baixa).
- **Pagar à mão** pede data, valor pago (pode diferir: juros, desconto), forma e o comprovante.
- **Comprovante**: foto ou PDF, anexado no pagamento ou depois.

### Freelancer, o caso de agora

O jeito do dia a dia: **"lançar a equipe do dia"**. Escolhe o dia, marca as pessoas que
trabalharam, a função e o valor da diária de cada uma (o valor vem do último lançamento da pessoa),
e o sistema gera uma conta por pessoa, com vencimento no dia combinado. Um sábado com seis
freelancers vira seis contas em uma tela.

Depois, a lista "A pagar" agrupada por pessoa mostra quanto cada um tem a receber na semana, e
"pagar todos" baixa as contas de uma pessoa de uma vez, com um comprovante só.

## 3. Decisões que recomendo

1. **Grupo novo "Financeiro" no menu**, com Contas a receber (que sai de Vendas) e Contas a pagar.
   A rota `/receber` não muda: só o lugar no menu.
2. **A pessoa é do cadastro de Pessoas**, nunca texto livre: freelancer recorrente vira cadastro,
   e o histórico de pagamentos dele aparece na ficha. Acrescentar ao cadastro **chave Pix** e
   **CPF/CNPJ do favorecido** (o CNPJ já existe; o CPF entra no mesmo campo).
3. **Categorias editáveis** numa tabela de apoio, já com: Freelancer, Fornecedor, Aluguel,
   Contas de consumo (água, luz, gás, internet), Impostos e taxas, Serviços, Manutenção, Outros.
4. **Baixa automática ligada por padrão para o agendado**, porque agendar já é a promessa de que o
   banco vai pagar. Quem não confia desliga na conta; e a lista "pagos hoje automaticamente" aparece
   no painel, para alguém olhar.
5. **Sem parcelamento e sem recorrência na etapa 1.** Aluguel mensal e parcelas vêm na etapa 3; o
   freelancer, que é o pedido de agora, não precisa disso.
6. **Não entra no CMV nem no estoque.** Freelancer é despesa operacional; o CMV continua sendo
   mercadoria. (A Precificação já tem o "custo operacional" digitado, e uma etapa futura pode
   sugerir esse número a partir do que foi pago.)
7. **Permissões novas**: `financeiro.pagar_ver`, `financeiro.pagar_lancar`,
   `financeiro.pagar_baixar` (Administrador e Gerente). Ver o que se paga a cada pessoa é dado
   sensível: a Cozinha não vê.
8. **Nada do Omie agora.** O Omie tem contas a pagar; integrar é uma etapa à parte, se a casa usar
   o financeiro de lá.

## 4. Telas

- **Financeiro ▸ Contas a pagar**: abas A pagar · Agendados · Pagos, filtros de período, pessoa e
  categoria, total do recorte, lista agrupável por pessoa. Botões: Nova conta, Lançar equipe do dia.
- **Janela da conta**: pessoa, categoria, descrição, competência, vencimento, valor, observação;
  ações Agendar, Pagar, Anexar comprovante, Estornar baixa, Cancelar.
- **Relatórios** (na mesma entrega, regra da casa): contas por situação e período; pagamentos por
  pessoa (o extrato do freelancer) e por categoria.

## 5. Etapas

| Etapa | Entrega |
|---|---|
| **1. Contas a pagar** | Grupo Financeiro, tabela, categorias, lançar, agendar, pagar, baixa automática, estorno, comprovante, lançar equipe do dia, chave Pix e CPF no cadastro, relatórios, testes |
| 2. Painel | Quanto vence hoje, na semana, atrasado; o que foi pago sozinho hoje; total por categoria no mês |
| 3. Recorrência e parcelas | Aluguel e contas mensais gerados sozinhos; parcelar uma compra |
| 4. Fluxo de caixa | A receber (vendas por forma, contas a receber) × a pagar, dia a dia |

## 6. Riscos

- ⚠️ **Baixa automática não confere o banco.** Ela registra que o pagamento agendado aconteceu; se
  o banco recusar, alguém tem de estornar a baixa. Por isso a lista do que foi baixado sozinho.
- ⚠️ **Anexo é dado sensível** (comprovante com dados bancários): rota autenticada, nunca
  `/arquivos/{nome}`, que é pública.
- ⚠️ **Duas lojas**: a conta é da loja (`id_unidade`); a pessoa é da casa.

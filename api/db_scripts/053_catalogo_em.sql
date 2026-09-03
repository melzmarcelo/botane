-- Botané 053 — o relógio do catálogo do Omie. Idempotente.
--
-- 🔑 **O cadastro passa a vir antes da nota** (pedido do dono, 03/09/2026),
-- espelhando o que a integração do PDV já fazia: produto criado no Omie hoje e
-- comprado hoje ficava sem vínculo, ia para a fila de pendências e esperava
-- alguém lembrar de clicar em "Importar catálogo" — um segundo botão que
-- ninguém sabe que precisa apertar.
--
-- ⚠️ **Mas o catálogo do Omie é CARO**: são milhares de produtos, paginados, e
-- a varredura leva dezenas de segundos. A agenda do Omie aceita frequência
-- HORÁRIA — sem uma trava, ela varreria o catálogo inteiro vinte e quatro vezes
-- por dia para achar os dois produtos que nasceram. Uma vez por dia basta:
-- produto novo espera algumas horas, nota nova não espera nada.
--
-- ⚠️ **Relógio PRÓPRIO, não `ultima_sincronizacao`** — aquela é o relógio das
-- NOTAS e avança a cada busca. É a mesma lição do `agenda_rodou_em` e do
-- `cardapio_em` do PDV.
--
-- ⚠️ **Por que uma coluna nova e não o `cardapio_em`**: aquela coluna é do
-- cardápio do PDV, e a linha do Omie é outra linha da mesma tabela. Guardar o
-- catálogo do Omie num campo com nome de cardápio funcionaria e mentiria para
-- quem lesse o schema depois. São dois relógios porque são duas integrações.

ALTER TABLE integracoes ADD COLUMN IF NOT EXISTS catalogo_em timestamptz;

COMMENT ON COLUMN integracoes.catalogo_em IS
    'Quando o AGENDADOR trouxe o catálogo desta integração pela última vez. '
    'Só o agendador move este relógio: busca manual não consome a cota do dia.';

-- 135 — A contagem em PARCELAS: "3 UN + 948 ML". Idempotente.
--
-- 🔑 **Pedido do dono (27/10/2026)**, no teste do CAMPARI: o estoque é em UN e a dose
-- sai em ML, então a prateleira tem garrafas fechadas e UMA aberta. Quem conta conta
-- "3 garrafas e a aberta com 948 ml" — e a tela só aceitava um número numa unidade,
-- obrigando a conta de cabeça (3,95 UN ou 3.942 ML), que é onde o erro entra.
--
-- `qtd_contada` continua sendo a verdade, na unidade de ESTOQUE (a soma das parcelas
-- convertidas). Aqui fica o que foi digitado, parcela a parcela: [{"qtd": 3, "um":
-- "UN"}, {"qtd": 948, "um": "ML"}]. Nulo quando a contagem foi de uma parcela só —
-- aí `qtd_informada`/`um_informada` (019) já dizem tudo.
-- ⚠️ Com parcelas, `qtd_informada`/`um_informada` ficam NULOS: um número só ali
-- mentiria sobre o que foi contado.
ALTER TABLE inventario_itens ADD COLUMN IF NOT EXISTS parcelas jsonb;

COMMENT ON COLUMN inventario_itens.parcelas IS
    'Contagem em mais de uma unidade (3 UN + 948 ML), como digitada. Nulo com uma só.';

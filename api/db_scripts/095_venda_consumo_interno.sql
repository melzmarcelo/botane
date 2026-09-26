-- A venda lançada para uma pessoa pode ser CONSUMO INTERNO.
--
-- 🔑 **Pedido do dono (26/09/2026):** *"quando lanço uma venda para uma pessoa, habilitar
-- um novo campo, Considerar consumo interno. Quando marcada, este documento entra como
-- consumo interno e não é considerado no CMV, somente o custo … deve manter a mesma regra
-- do consumo interno."*
--
-- A mesma regra do consumo interno de sempre (`SAIDA_CONSUMO_INTERNO`):
-- * o estoque sai como CONSUMO INTERNO, não como venda — e o custo aparece na linha
--   "dos quais: consumo interno" da apuração;
-- * NÃO é receita nem CMV teórico: um prato que ninguém vendeu não pode entrar no food
--   cost como se tivesse sido vendido (nem pelo preço, nem pela ficha).
-- ⚠️ O documento continua sendo da PESSOA: aparece no consumo por pessoa e no ciclo.
-- Idempotente.

ALTER TABLE vendas ADD COLUMN IF NOT EXISTS consumo_interno boolean NOT NULL DEFAULT false;

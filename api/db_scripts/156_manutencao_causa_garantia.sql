-- 156 — Patrimônio: o que gerou cada manutenção e se a garantia cobriu.
--
-- 🔑 Pedido do dono (09/11/2026), da ficha do bem em abas: o histórico de manutenção diz "o que
-- gerou a manutenção, o que foi feito e se a garantia cobriu". O que foi feito já existia
-- (`descricao`); faltavam os outros dois.
-- ⚠️ Os acionamentos da garantia NÃO são um cadastro à parte: são as manutenções marcadas aqui.
-- Duas listas da mesma visita divergiriam no primeiro registro esquecido.
-- Idempotente.

-- O motivo da visita: "preventiva programada", "parou de gelar", "barulho no motor"...
ALTER TABLE bem_manutencoes ADD COLUMN IF NOT EXISTS causa varchar(120);
-- A visita que a garantia pagou. O custo continua sendo o que a casa pagou (zero, quase sempre).
ALTER TABLE bem_manutencoes ADD COLUMN IF NOT EXISTS coberta_garantia boolean NOT NULL DEFAULT false;

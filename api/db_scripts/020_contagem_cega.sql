-- Botané 020 — contagem cega. Idempotente.
--
-- Mostrar o saldo do sistema para quem conta transforma a contagem em
-- conferência: a pessoa vê 12, olha a prateleira, acha que são 12 e escreve 12.
-- Na contagem cega o número esperado não aparece — nem na tela, nem na folha
-- impressa, nem no JSON —, e a diferença só surge quando a contagem fecha.
ALTER TABLE inventarios ADD COLUMN IF NOT EXISTS cega boolean NOT NULL DEFAULT false;

COMMENT ON COLUMN inventarios.cega IS
    'Enquanto ABERTO, esconde o saldo do sistema de todos — inclusive na API.';

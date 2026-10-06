-- 106 — Características da mesa. Idempotente.
--
-- 🔑 **Pedido do dono (06/10/2026)**, primeira entrega do estudo
-- `docs/salao-estudo.md`. "Mesa perto da janela", "precisa de cadeirão",
-- "cadeirante" chegavam na observação da reserva e a recepção resolvia de
-- memória: a mesa não sabia dizer nada sobre si além de quantos cabem.
--
-- ⚠️ **Lista FIXA, conferida pelo banco.** Texto livre viraria "Janela",
-- "janela " e "perto da janela" — três valores para a mesma coisa, e um filtro
-- que não acha nenhuma. Acrescentar uma característica é uma migração de uma
-- linha, o que é o preço certo para algo que a recepção vai filtrar.
--
-- ⚠️ **Só INFORMA.** A regra de disponibilidade não lê esta coluna: quem decide
-- se há mesa continua sendo a capacidade. A característica serve à pessoa que
-- escolhe a mesa, não ao cálculo.

ALTER TABLE mesas
    ADD COLUMN IF NOT EXISTS caracteristicas text[] NOT NULL DEFAULT '{}';

ALTER TABLE mesas DROP CONSTRAINT IF EXISTS ck_mesa_caracteristicas;
ALTER TABLE mesas ADD CONSTRAINT ck_mesa_caracteristicas CHECK (
    caracteristicas <@ ARRAY['JANELA', 'SOFA', 'ACESSIVEL', 'CADEIRAO', 'TOMADA', 'COBERTA']::text[]
);

COMMENT ON COLUMN mesas.caracteristicas IS
    'O que a mesa tem (JANELA, SOFA, ACESSIVEL, CADEIRAO, TOMADA, COBERTA). '
    'Só informa a recepção — a disponibilidade não lê.';

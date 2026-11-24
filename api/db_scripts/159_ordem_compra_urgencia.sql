-- 159 — Ordem de compra: para quando o item precisa chegar.
-- Idempotente. Só acrescenta uma coluna com padrão: as linhas que já existem ficam "Esta semana".
--
-- 🔑 **Pedido do dono (24/11/2026)**, no modelo "Ordem de compra — versão didática": o pedido
-- ganha "Para quando?" (Pode esperar · Esta semana · Urgente — hoje), e A comprar vem com os mais
-- urgentes primeiro. É para quem compra decidir a ordem, não um prazo com cobrança.

ALTER TABLE ordem_compra_itens
    ADD COLUMN IF NOT EXISTS urgencia varchar(12) NOT NULL DEFAULT 'SEMANA'
        CHECK (urgencia IN ('PODE_ESPERAR', 'SEMANA', 'HOJE'));

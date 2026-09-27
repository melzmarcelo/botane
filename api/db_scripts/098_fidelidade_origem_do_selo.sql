-- Fidelidade: de onde veio cada selo, e o selo dado à mão.
--
-- 🔑 **Pedido do dono (27/09/2026):** *"implementar uma tela para verificar os selos, os
-- resgates, a validade, ajustar o vencimento, dar selos, visualizar tudo que diz respeito
-- ao plano de fidelidade em uma só tela."*
--
-- `origem`: QRCODE (o QR da mesa), CODIGO (o código do caixa), MANUAL (dado pela gerência,
-- com `motivo` e `concedido_por`). As linhas de antes da 098 não sabem de qual QR vieram:
-- ficam `VISITA`, que é a verdade que se tem.
-- ⚠️ **O selo MANUAL não é a visita do dia**: ele entra numa `parte` acima de zero, e a
-- `parte 0` continua livre para a visita de verdade.
-- Idempotente.

ALTER TABLE fidelidade_checkins ADD COLUMN IF NOT EXISTS origem varchar(10) NOT NULL DEFAULT 'VISITA';
ALTER TABLE fidelidade_checkins ADD COLUMN IF NOT EXISTS motivo varchar(200);
ALTER TABLE fidelidade_checkins
    ADD COLUMN IF NOT EXISTS concedido_por integer REFERENCES usuarios(id) ON DELETE SET NULL;
DO $$ BEGIN
    ALTER TABLE fidelidade_checkins ADD CONSTRAINT ck_fidelidade_origem
        CHECK (origem IN ('VISITA', 'QRCODE', 'CODIGO', 'MANUAL'));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- Quem mexeu no vencimento de um prêmio, e o que estava antes (a auditoria guarda também).
ALTER TABLE fidelidade_premios ADD COLUMN IF NOT EXISTS vencimento_original date;

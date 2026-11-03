-- 147 — O documento com motivo Prêmio LIGA (ou entrega) o prêmio da fidelidade. Idempotente.
--
-- 🔑 **Pedido do dono (03/11/2026):** *"vincular o documento com o resgate de prêmios"* —
-- código obrigatório no motivo Prêmio. Estudo: docs/fidelidade-resgate-estudo.md.
-- O almoço do prêmio vai num documento do PDV que NÃO é importado e é lançado à mão
-- depois: o documento manual é o único registro dele no Botané, e quase sempre chega
-- quando o balcão já entregou o prêmio. Aí ele só LIGA; se o prêmio ainda estava
-- disponível, o documento o ENTREGA (e lembra disso, para devolver se for cancelado).
--
-- ⚠️ Um prêmio, um documento VIVO (regra 8: quem garante é o banco, não a tela). O
-- cancelado sai do índice — o prêmio pode ir para um documento novo, o correto.
-- ⚠️ O CHECK não exige `id_premio` no motivo PREMIO: os documentos Prêmio de antes desta
-- migração não têm código, e a exigência mora na API (para documento novo).

ALTER TABLE fidelidade_premios
    ADD COLUMN IF NOT EXISTS entregue_pelo_documento boolean NOT NULL DEFAULT false;

COMMENT ON COLUMN fidelidade_premios.entregue_pelo_documento IS
    'Verdadeiro quando quem marcou a entrega foi o documento com motivo Prêmio (147), e não '
    'o balcão. Cancelar esse documento devolve o prêmio; o entregue no balcão continua entregue.';

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_vendas_premio') THEN
        ALTER TABLE vendas ADD CONSTRAINT ck_vendas_premio
            CHECK (id_premio IS NULL OR motivo = 'PREMIO');
    END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS ux_venda_premio
    ON vendas (id_premio) WHERE id_premio IS NOT NULL AND NOT cancelada;

COMMENT ON COLUMN vendas.id_premio IS
    'O prêmio da fidelidade servido com este documento (motivo PREMIO, migração 147). '
    'Um prêmio tem no máximo um documento não cancelado.';

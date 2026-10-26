-- 134 — O MOTIVO de um documento que não é venda. Idempotente.
--
-- 🔑 **Pedido do dono (26/10/2026):** *"ao lançar um documento à mão, gostaria de ter um
-- campo Motivo, e quando selecionado algum, ter um campo Observação. Motivos: Perda,
-- Prêmio, Brinde/Aniversário, Outros … basicamente seria um consumo interno, saindo pelo
-- custo"*. E unificar com a caixa "Considerar consumo interno" (migração 095), que vira
-- o motivo CONSUMO_INTERNO.
--
-- ⚠️ **`consumo_interno` continua sendo a chave de "fora da receita"**, e vale para TODO
-- motivo. São mais de dez consultas (apuração, margem, painel, início, cardápio) que já
-- excluem `consumo_interno`; trocá-las por "motivo IS NULL" seria espalhar a mesma regra
-- em dez lugares para dizer o que a coluna já diz. O motivo diz POR QUE; a coluna diz
-- que não é venda.
-- ⚠️ O motivo decide a SAÍDA do estoque: PERDA sai como `SAIDA_PERDA` (com o motivo da
-- perda, a mesma lista de Ajustes ▸ Perda); os outros como `SAIDA_CONSUMO_INTERNO`.
ALTER TABLE vendas
    ADD COLUMN IF NOT EXISTS motivo varchar(20),
    ADD COLUMN IF NOT EXISTS motivo_observacao text,
    ADD COLUMN IF NOT EXISTS id_motivo_perda integer REFERENCES perda_motivos(id),
    -- 🔑 Previsto para a fidelidade: o prêmio entregue com este documento. Ainda sem uso.
    ADD COLUMN IF NOT EXISTS id_premio integer REFERENCES fidelidade_premios(id);

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_vendas_motivo') THEN
        ALTER TABLE vendas ADD CONSTRAINT ck_vendas_motivo CHECK (
            motivo IS NULL
            OR (motivo IN ('CONSUMO_INTERNO', 'PERDA', 'PREMIO', 'BRINDE', 'OUTROS')
                AND consumo_interno));
    END IF;
END $$;

-- O consumo interno de antes da 134 ganha o motivo que ele sempre foi.
UPDATE vendas SET motivo = 'CONSUMO_INTERNO'
 WHERE consumo_interno AND motivo IS NULL;

COMMENT ON COLUMN vendas.motivo IS
    'Por que este documento não é venda (migração 134): CONSUMO_INTERNO, PERDA, PREMIO, '
    'BRINDE ou OUTROS. Com motivo, consumo_interno é sempre verdadeiro (fora da receita).';

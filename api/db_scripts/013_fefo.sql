-- Botané 013 — o índice que sustenta o FEFO. Idempotente.

-- A saída passa a escolher lote sozinha: o que vence primeiro sai primeiro.
-- Esta é a leitura que roda a cada saída de produto com lote, então precisa ser
-- barata. `NULLS LAST` no índice porque lote sem validade é o último da fila:
-- não se descarta o que não vence na frente do que vence.
CREATE INDEX IF NOT EXISTS ix_lote_fefo
    ON estoque_lotes (id_unidade, id_local, id_produto, validade NULLS LAST, id)
 WHERE quantidade > 0;

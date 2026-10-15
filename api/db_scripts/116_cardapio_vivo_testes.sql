-- 116 — Cardápio Vivo, fase 3: testes A/B (mídia e ordem) e a mídia preferida do item.
-- Idempotente. Decisões do dono (15/10/2026) na seção 9 de `docs/cardapio-vivo-estudo.md`.
--
-- 🔑 **A variante NÃO é gravada por sessão.** Ela sai de uma conta determinística sobre o id
-- anônimo da sessão e o id do teste — `mod(abs(hashtext(sessao || ':' || teste)), 2)` —, feita
-- no BANCO tanto ao montar o feed quanto ao analisar. Uma conta só, num lugar só: o feed e o
-- resultado nunca discordam sobre quem viu o quê, e nenhuma tabela cresce por visita.

CREATE TABLE IF NOT EXISTS cardapio_testes (
    id            serial PRIMARY KEY,
    id_unidade    integer NOT NULL REFERENCES unidades(id) ON DELETE CASCADE,
    id_catalogo   integer NOT NULL REFERENCES catalogos(id) ON DELETE CASCADE,
    -- MIDIA: no prato, A = vídeo, B = foto. ORDEM: A = a ordem do catálogo, B = a sugerida.
    tipo          varchar(5) NOT NULL CHECK (tipo IN ('MIDIA', 'ORDEM')),
    nome          varchar(120) NOT NULL,
    id_produto    integer REFERENCES produtos(id) ON DELETE CASCADE,
    -- A ordem B CONGELADA no início (ids dos itens, na ordem do feed): a sugestão do painel
    -- muda com os dias, e um teste cuja variante muda no meio não mede nada.
    ordem_b       jsonb,
    inicio        timestamptz NOT NULL DEFAULT now(),
    encerrado_em  timestamptz,
    vencedor      char(1) CHECK (vencedor IN ('A', 'B')),
    aplicado_em   timestamptz,
    criado_por    integer REFERENCES usuarios(id) ON DELETE SET NULL,
    encerrado_por integer REFERENCES usuarios(id) ON DELETE SET NULL,
    CONSTRAINT ck_teste_alvo CHECK (
        (tipo = 'MIDIA' AND id_produto IS NOT NULL AND ordem_b IS NULL) OR
        (tipo = 'ORDEM' AND id_produto IS NULL AND ordem_b IS NOT NULL))
);
-- ⚠️ **Um teste ABERTO por prato (mídia) e um de ordem por cardápio**: dois testes mexendo na
-- mesma coisa ao mesmo tempo misturariam os efeitos, e nenhum dos dois mediria nada.
CREATE UNIQUE INDEX IF NOT EXISTS ux_teste_midia_aberto
    ON cardapio_testes (id_catalogo, id_produto) WHERE tipo = 'MIDIA' AND encerrado_em IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS ux_teste_ordem_aberto
    ON cardapio_testes (id_catalogo) WHERE tipo = 'ORDEM' AND encerrado_em IS NULL;
CREATE INDEX IF NOT EXISTS ix_teste_loja ON cardapio_testes (id_unidade, inicio DESC);

-- 🔑 **O vencedor "foto" vira decisão do ITEM**: o prato tem vídeo, mas o feed passa a mostrar
-- a foto. No item (como destaque e esgotado), porque é decisão deste cardápio.
ALTER TABLE catalogo_itens ADD COLUMN IF NOT EXISTS midia_preferida varchar(5)
    CHECK (midia_preferida IN ('FOTO'));

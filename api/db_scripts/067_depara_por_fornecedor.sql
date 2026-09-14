-- Botané 067 — o código que vem na linha da nota é do FORNECEDOR, e só é único
-- dentro dele. A chave do de-para passa a dizer isso. Idempotente.
--
-- 🔑 **O caso real (14/09/2026, relatado pelo dono).** No Omie o ABACATE de um
-- fornecedor tem `cCodigo = 1`. Chega a nota de OUTRO fornecedor com o MORANGO,
-- também `cCodigo = 1`. A conciliação casava o MORANGO com o ABACATE, e a nota
-- conciliada assim levava a mercadoria errada para o razão.
--
-- ⚠️ **A coluna `id_fornecedor` JÁ EXISTIA nesta tabela, e já era gravada** por
-- `vincular_item` desde sempre — só não entrava nem na chave nem na pergunta.
-- Ou seja: o dado que separava os dois casos estava guardado e era ignorado.
--
-- ⚠️ **E a correção manual PIORAVA o quadro.** Com `PRIMARY KEY (sistema,
-- codigo)`, o `ON CONFLICT (sistema, codigo) DO UPDATE` de `vincular_item`
-- fazia a correção do MORANGO SOBRESCREVER o vínculo do ABACATE do outro
-- fornecedor. A próxima nota dele entrava como MORANGO, alguém corrigia, e o
-- MORANGO quebrava de volta — um vai-e-vem em que cada rodada é mercadoria
-- errada num razão que é append-only.
--
-- ⚠️ **`coalesce(id_fornecedor, 0)` e não uma coluna NOT NULL**: `id_fornecedor`
-- é chave estrangeira para `fornecedores(id)`, e 0 não é fornecedor nenhum. O
-- nulo continua querendo dizer "não sei de quem é este código" — é o caso das
-- linhas de `OMIE_PRODUTO`, `EAN` e `PDV_LEGAL`, que são códigos globais de
-- verdade (o id do Omie, o código de barras do fabricante, o código do
-- cardápio) e seguem valendo uma vez só, como antes.
--
-- ⚠️ **Não há o que deduplicar.** A chave antiga era MAIS restritiva, então
-- existe no máximo uma linha por (sistema, código) — toda linha de hoje cabe na
-- chave nova sem colidir. Esta migração só AFROUXA, e não reescreve vínculo
-- nenhum.
--
-- ⚠️ **O efeito visível em base com dado**: item que antes casava sozinho pelo
-- código de OUTRO fornecedor passa a cair em PENDENTE, e alguém resolve na
-- conferência. É a troca certa — pendente aparece na tela, casamento errado não
-- aparece em lugar nenhum até o CMV do mês.

ALTER TABLE codigos_externos DROP CONSTRAINT IF EXISTS codigos_externos_pkey;

CREATE UNIQUE INDEX IF NOT EXISTS ux_codigos_externos_por_fornecedor
    ON codigos_externos (sistema, codigo, coalesce(id_fornecedor, 0));

-- A busca da conciliação passa a filtrar por fornecedor; sem este índice ela
-- varreria a tabela inteira a cada item de cada nota.
CREATE INDEX IF NOT EXISTS ix_codigos_externos_fornecedor
    ON codigos_externos (id_fornecedor) WHERE id_fornecedor IS NOT NULL;

COMMENT ON COLUMN codigos_externos.id_fornecedor IS
    'De quem é este código. Faz PARTE da chave: o mesmo cCodigo significa '
    'produtos diferentes em fornecedores diferentes. Nulo só para código '
    'global de verdade (OMIE_PRODUTO, EAN, PDV_LEGAL).';

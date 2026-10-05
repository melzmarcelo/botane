-- 104 — a ORDEM em que o saldo de cada movimento foi acumulado.
--
-- 🔑 **O defeito (achado em 05/10/2026).** `saldo_apos`/`custo_medio_apos` são a
-- fotografia do estoque depois de cada movimento, e quem pergunta "quanto havia
-- no dia X" pega o ÚLTIMO movimento antes de X. "Último" era o de maior `id` —
-- a ordem de LANÇAMENTO, que é a ordem em que a fotografia é tirada.
-- Só que `POST /estoque/reprocessar` (15/09/2026) refaz a fotografia na ordem da
-- DATA. Depois dele, o movimento de maior `id` deixa de ser o fim da corrente:
-- num produto com venda de setembro lançada depois da entrada de outubro, o
-- relatório lia saldo −5 onde havia 15, e a soma do CMV por grupo abria em
-- exatamente o valor da entrada.
--
-- 🔑 **A correção: a ordem da corrente passa a estar ESCRITA.** `ordem_cadeia`
-- diz em que posição da corrente o movimento está. Nula, vale o `id` — é o caso
-- de todo movimento que nunca foi reprocessado, e por isso nada muda para eles.
-- O reprocessamento redistribui os PRÓPRIOS ids do produto na ordem da data:
-- os valores continuam únicos, e continuam menores que o id de qualquer
-- movimento futuro — que entra no fim da corrente, como sempre.
--
-- ⚠️ **É coluna DERIVADA**, da mesma família de `saldo_apos`: reescrevê-la não
-- fura o append-only. Tipo, quantidade, data e origem continuam intocados.

ALTER TABLE estoque_movimentos ADD COLUMN IF NOT EXISTS ordem_cadeia bigint;

COMMENT ON COLUMN estoque_movimentos.ordem_cadeia IS
    'Posição na corrente em que saldo_apos foi acumulado. Nula = o próprio id '
    '(ordem de lançamento). Preenchida pelo reprocessamento, que refaz a corrente '
    'na ordem da data.';

-- O índice da fotografia (027) ordenava por `id DESC`; a leitura passou a
-- ordenar pela posição na corrente.
CREATE INDEX IF NOT EXISTS ix_mov_fotografia_cadeia
    ON estoque_movimentos (id_unidade, id_produto, id_local,
                           (coalesce(ordem_cadeia, id)) DESC);

-- 🔑 **Quem JÁ foi reprocessado antes desta migração.** A auditoria guarda cada
-- reprocessamento aplicado (entidade `estoque`, ação `reprocessar`, com a loja e
-- a hora). Os movimentos daquele produto que existiam até o ÚLTIMO
-- reprocessamento estão com a fotografia na ordem da data — é o que a coluna
-- passa a dizer. Os lançados depois entraram no fim da corrente e ficam nulos.
-- ⚠️ Idempotente: recalcula a mesma permutação a partir dos mesmos dados, e só
-- escreve onde o valor muda.
WITH reprocessado AS (
    SELECT a.id_unidade, a.id_entidade::integer AS id_produto, max(a.em) AS quando
      FROM auditoria a
     WHERE a.entidade = 'estoque' AND a.acao = 'reprocessar'
       AND a.id_unidade IS NOT NULL AND a.id_entidade ~ '^[0-9]+$'
     GROUP BY a.id_unidade, a.id_entidade
),
alvo AS (
    SELECT m.id, m.id_unidade, m.id_produto, m.data_movimento
      FROM estoque_movimentos m
      JOIN reprocessado r ON r.id_unidade = m.id_unidade AND r.id_produto = m.id_produto
     WHERE m.criado_em <= r.quando
),
por_data AS (
    SELECT id, id_unidade, id_produto,
           row_number() OVER (PARTITION BY id_unidade, id_produto
                                  ORDER BY data_movimento, id) AS n
      FROM alvo
),
por_id AS (
    SELECT id AS posicao, id_unidade, id_produto,
           row_number() OVER (PARTITION BY id_unidade, id_produto ORDER BY id) AS n
      FROM alvo
)
UPDATE estoque_movimentos m
   SET ordem_cadeia = i.posicao
  FROM por_data d
  JOIN por_id i ON i.id_unidade = d.id_unidade AND i.id_produto = d.id_produto AND i.n = d.n
 WHERE m.id = d.id
   AND coalesce(m.ordem_cadeia, m.id) <> i.posicao;

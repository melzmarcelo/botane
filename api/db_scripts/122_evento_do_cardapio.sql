-- ============================================================================
-- 122 — de QUAL Cardápio Vivo veio cada evento (17/10/2026)
-- ============================================================================
-- 🔑 Achado da análise pedida pelo dono (17/10/2026): com mais de um Cardápio Vivo na loja
-- (117: a cafeteria e o catering), a medição não dizia de qual deles veio a visita. O lote
-- de eventos já mandava `catalogo`, mas nada o gravava: sessões, funil, Atenção × Vendas,
-- testes A/B e o relatório dos anúncios somavam os dois cardápios.
--
-- ⚠️ No EVENTO, não na sessão: a sessão anônima mora no aparelho e é a mesma quando a pessoa
-- passa do cardápio da mesa para o do catering (um anúncio leva de um ao outro).
-- ⚠️ Sem chave estrangeira, como `id_item`, `id_cartao` e `id_anuncio`: o evento é história, e
-- apagar um catálogo não pode reescrever (nem travar) o que foi medido.

ALTER TABLE cardapio_eventos ADD COLUMN IF NOT EXISTS id_catalogo integer;

CREATE INDEX IF NOT EXISTS ix_cardapio_evento_catalogo
    ON cardapio_eventos (id_catalogo, quando) WHERE id_catalogo IS NOT NULL;

-- O que já foi medido, pelo que o próprio evento aponta: o prato, o cartão ou a seção.
UPDATE cardapio_eventos e SET id_catalogo = g.id_catalogo
  FROM catalogo_itens i JOIN catalogo_categorias g ON g.id = i.id_categoria
 WHERE e.id_catalogo IS NULL AND e.id_item = i.id;

UPDATE cardapio_eventos e SET id_catalogo = k.id_catalogo
  FROM catalogo_cartoes k
 WHERE e.id_catalogo IS NULL AND e.id_cartao = k.id;

UPDATE cardapio_eventos e SET id_catalogo = g.id_catalogo
  FROM catalogo_categorias g
 WHERE e.id_catalogo IS NULL AND e.id_categoria = g.id;

-- O resto (abrir, sair, o anúncio, o Hub): o cardápio da sessão, quando ela viu um só.
UPDATE cardapio_eventos e SET id_catalogo = s.id_catalogo
  FROM (SELECT id_sessao, min(id_catalogo) AS id_catalogo
          FROM cardapio_eventos WHERE id_catalogo IS NOT NULL
         GROUP BY id_sessao HAVING count(DISTINCT id_catalogo) = 1) s
 WHERE e.id_catalogo IS NULL AND e.id_sessao = s.id_sessao;

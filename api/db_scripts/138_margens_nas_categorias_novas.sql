-- 138 — As margens por categoria passam para as categorias NOVAS. Idempotente.
--
-- 🔑 **Pedido do dono (27/10/2026):** *"consegue fazer a migração para as novas categorias
-- estes cadastros como fizemos nos produtos"* — e, sobre a proposta: *"pode seguir com
-- 38,5% e fazer por migração"*.
--
-- O que aconteceu: em 17/10 a configuração ganhou 27 margens por categoria; em 25/10 a
-- reestruturação dos cadastros DESATIVOU essas categorias e passou os produtos para as 36
-- novas (planilha `reclassificacao_IMPORTAR.csv`). Desde então as 27 valiam para ninguém,
-- e todo produto saía pela margem geral.
--
-- 🔑 **A margem de cada categoria nova é a PREDOMINANTE entre os produtos que vieram para
-- ela** (contados na planilha da reclassificação, sem os arquivados — o mesmo de-para dos
-- produtos). Bebidas preparadas juntou café (38,5%), drinks e sucos (41,5%) e chá
-- (48,5%): o dono escolheu 38,5%. Pratos preparados dá 35,5%, a margem geral — sem linha,
-- porque não mudaria nada. Serviços e embalagens ficam de fora.
--
-- ⚠️ **Pelo NOME das categorias, e só onde o cenário é o do ar**: a loja que ainda tem
-- margem presa a uma das 27 categorias antigas DESATIVADAS. Base sem elas (uma instalação
-- nova, a base de testes) não muda nada. Rodar de novo também não: as antigas já saíram.
-- ⚠️ O nome da linha nova é o das antigas (no ar, "Margem"): é pelo nome que a linha de
-- categoria substitui a geral.
-- ⚠️ Linha que já exista para a categoria nova (alguém refez na tela antes) é mantida —
-- `ON CONFLICT DO NOTHING` no índice único da 105.

DROP TABLE IF EXISTS _margens_antigas, _margens_novas, _presas;
CREATE TEMP TABLE _margens_antigas (nome text PRIMARY KEY) ON COMMIT DROP;
INSERT INTO _margens_antigas VALUES
    ('ALMOCO'), ('BRUNCH'), ('ENTRADA'), ('SALADA'), ('SANDUICHES'), ('KIDS'), ('EXTRAS'),
    ('CATERING'), ('VITRINE FRIA'), ('VITRINE SECA DOCE'), ('VITRINE SECA SALGADA'),
    ('PAO FRESCO'), ('BOLO INTEIRO'), ('NATAL'), ('PASCOA'), ('DIA DOS NAMORADOS'),
    ('CAFETERIA'), ('CHA'), ('SUCOS E DRINKS SEM ALCOOL'), ('DRINK'), ('TACAS VINHO'),
    ('GELADEIRA'), ('VINHO ESPUMANTE'), ('MERCEARIA CAFES'), ('PRODUTOS MERCEARIA'),
    ('MERCEARIA LOUCAS'), ('MERCEARIA PRESENTES');

CREATE TEMP TABLE _margens_novas (nome text PRIMARY KEY, valor numeric(12,4), ordem int)
    ON COMMIT DROP;
INSERT INTO _margens_novas VALUES
    ('DOCES, BOLOS E SOBREMESAS',        38.5, 1),
    ('BEBIDAS PREPARADAS',               38.5, 2),
    ('ALIMENTOS EMBALADOS PARA REVENDA', 23.5, 3),
    ('VINHOS E ESPUMANTES',              18.5, 4),
    ('PRODUTOS DE PANIFICAÇÃO',          38.5, 5),
    ('SALGADOS',                         38.5, 6),
    ('BEBIDAS PRONTAS PARA REVENDA',     23.5, 7),
    ('CERVEJAS E DESTILADOS',            23.5, 8),
    ('PRESENTES, LOUÇAS E ACESSÓRIOS',   13.5, 9),
    ('CAFÉS E CHÁS PARA REVENDA',        28.5, 10),
    ('KITS E CESTAS',                    33.5, 11);

-- As linhas presas: margem de categoria, numa das 27 antigas, e a categoria desativada.
CREATE TEMP TABLE _presas ON COMMIT DROP AS
SELECT l.id, l.id_unidade, l.nome
  FROM precificacao_linhas l
  JOIN categorias c ON c.id = l.id_categoria
  JOIN _margens_antigas a ON a.nome = upper(c.nome)
 WHERE l.tipo = 'MARGEM' AND l.alcance = 'CATEGORIA' AND NOT c.ativo;

-- 1. As novas, para cada loja que tem presas — com o nome que as antigas usavam.
INSERT INTO precificacao_linhas (id_unidade, nome, tipo, valor, alcance, id_categoria, ordem)
SELECT p.id_unidade, p.nome, 'MARGEM', n.valor, 'CATEGORIA', c.id, 200 + n.ordem
  FROM (SELECT id_unidade, min(nome) AS nome FROM _presas GROUP BY id_unidade) p
  JOIN _margens_novas n ON true
  JOIN categorias c ON upper(c.nome) = n.nome AND c.ativo
ON CONFLICT DO NOTHING;

-- 2. E as antigas saem.
DELETE FROM precificacao_linhas WHERE id IN (SELECT id FROM _presas);

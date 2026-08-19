-- Botané 005 — o mínimo para a casa começar a cadastrar produto no primeiro dia.
-- Só semeia se a tabela estiver vazia: quem apagar não vê o item voltar.

INSERT INTO setores (nome, ordem)
SELECT * FROM (VALUES
    ('Cozinha', 10), ('Confeitaria', 20), ('Bar', 30), ('Salão', 40), ('Delivery', 50)
) AS s(nome, ordem)
WHERE NOT EXISTS (SELECT 1 FROM setores);

INSERT INTO locais_estoque (id_unidade, nome, tipo, principal)
SELECT u.id, v.nome, v.tipo, v.principal
  FROM unidades u
 CROSS JOIN (VALUES
    ('Estoque seco', 'SECO',      true),
    ('Câmara fria',  'RESFRIADO', false),
    ('Freezer',      'CONGELADO', false),
    ('Bar',          'BAR',       false)
 ) AS v(nome, tipo, principal)
 WHERE u.matriz
   AND NOT EXISTS (SELECT 1 FROM locais_estoque);

INSERT INTO categorias (nome, tipo, ordem)
SELECT * FROM (VALUES
    ('Hortifrúti',        'INSUMO',     10),
    ('Carnes e frios',    'INSUMO',     20),
    ('Laticínios',        'INSUMO',     30),
    ('Mercearia',         'INSUMO',     40),
    ('Panificação',       'INSUMO',     50),
    ('Café e chá',        'INSUMO',     60),
    ('Bebidas',           'REVENDA',    70),
    ('Descartáveis',      'EMBALAGEM',  80),
    ('Limpeza',           'INSUMO',     90),
    ('Pratos',            'PRODUZIDO', 100),
    ('Doces e sobremesas','PRODUZIDO', 110)
) AS c(nome, tipo, ordem)
WHERE NOT EXISTS (SELECT 1 FROM categorias);

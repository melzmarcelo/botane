-- Botané 030 — o inventário deixa de ser sempre "um local inteiro". Idempotente.
--
-- Contar a despensa inteira é raro. O que a casa faz é contar a câmara fria,
-- ou só as bebidas, ou só o hortifrúti antes da feira. Até aqui a única
-- pergunta era o LOCAL, e quem quisesse contar um pedaço tinha de escolher
-- produto por produto.
--
-- Agora a contagem se monta por **local, setor, categoria e tipo de produto** —
-- cada um opcional, em branco querendo dizer "todos".
--
-- ⚠️ **A consequência estrutural é o item passar a saber o local dele.** Com um
-- local por contagem, `qtd_sistema` era o saldo naquele local e o ajuste do
-- fechamento ia para lá. Sem local escolhido, o mesmo produto pode ter saldo em
-- dois lugares — e são duas linhas para contar, com dois ajustes diferentes. Sem
-- `inventario_itens.id_local`, o fechamento lançaria os dois no mesmo lugar e
-- sumiria com o estoque de um deles.

-- ---------------------------------------------------------------- cabeçalho

-- ⚠️ `id_local` continua existindo e passa a ser NULO quando a contagem cobre
-- mais de um local. Não é redundância: é o atalho que mantém de pé tudo o que
-- já pergunta "de que local é esta contagem", e continua sendo a resposta certa
-- no caso comum, que é contar um lugar só.
ALTER TABLE inventarios ALTER COLUMN id_local DROP NOT NULL;
COMMENT ON COLUMN inventarios.id_local IS
    'O local, quando a contagem é de um só. NULO quando ela cobre vários.';

ALTER TABLE inventarios ADD COLUMN IF NOT EXISTS nome varchar(80);

-- O que gerou a lista fica gravado: sem isto, quem abre uma contagem de três
-- meses atrás vê 40 produtos e não tem como saber por que aqueles 40.
ALTER TABLE inventarios ADD COLUMN IF NOT EXISTS filtro_locais integer[];
ALTER TABLE inventarios ADD COLUMN IF NOT EXISTS filtro_setores integer[];
ALTER TABLE inventarios ADD COLUMN IF NOT EXISTS filtro_categorias integer[];
ALTER TABLE inventarios ADD COLUMN IF NOT EXISTS filtro_tipos varchar(20)[];

-- Nome para o que já existe, para a lista não ficar com linhas sem título.
UPDATE inventarios i
   SET nome = coalesce(
       nullif(i.nome, ''),
       (SELECT 'Contagem de ' || l.nome FROM locais_estoque l WHERE l.id = i.id_local),
       'Contagem geral')
 WHERE i.nome IS NULL OR i.nome = '';

-- ------------------------------------------------------------------- itens

ALTER TABLE inventario_itens ADD COLUMN IF NOT EXISTS id_local integer
    REFERENCES locais_estoque(id);

-- Backfill: o item herda o local do cabeçalho, que até agora era obrigatório.
UPDATE inventario_itens ii
   SET id_local = i.id_local
  FROM inventarios i
 WHERE i.id = ii.id_inventario AND ii.id_local IS NULL AND i.id_local IS NOT NULL;

-- ⚠️ Item sem local não pode existir daqui para a frente: o fechamento precisa
-- saber onde lançar o ajuste. A trava só entra depois do backfill, e só se ele
-- tiver dado conta de tudo — numa base com item órfão, derrubar a migração
-- seria pior que deixar a coluna solta.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM inventario_itens WHERE id_local IS NULL) THEN
        BEGIN
            ALTER TABLE inventario_itens ALTER COLUMN id_local SET NOT NULL;
        EXCEPTION WHEN others THEN
            RAISE NOTICE 'inventario_itens.id_local segue opcional: %', SQLERRM;
        END;
    ELSE
        RAISE NOTICE 'inventario_itens tem item sem local; a coluna segue opcional';
    END IF;
END $$;

-- ⚠️ A unicidade passa a incluir o local. Com `(id_inventario, id_produto)` só,
-- o mesmo café em duas câmaras seria uma linha só — e o `ON CONFLICT` da
-- contagem sobrescreveria uma com a outra, calado.
DO $$
DECLARE
    antigo text;
BEGIN
    SELECT conname INTO antigo
      FROM pg_constraint
     WHERE conrelid = 'inventario_itens'::regclass
       AND contype = 'u'
       AND pg_get_constraintdef(oid) = 'UNIQUE (id_inventario, id_produto)';
    IF antigo IS NOT NULL THEN
        EXECUTE format('ALTER TABLE inventario_itens DROP CONSTRAINT %I', antigo);
    END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS ux_inventario_item
    ON inventario_itens (id_inventario, id_produto, id_local);

-- Responde "este produto neste local já está em alguma contagem aberta?", que é
-- a guarda que substituiu "um inventário aberto por local".
CREATE INDEX IF NOT EXISTS ix_inventario_item_produto_local
    ON inventario_itens (id_produto, id_local);

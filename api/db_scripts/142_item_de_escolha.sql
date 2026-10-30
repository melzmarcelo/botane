-- 142 — Item de escolha no catálogo, e adicionais que repetem. Idempotente.
--
-- 🔑 **Pedido do dono (29/10/2026)**, estudo em `docs/item-de-escolha-estudo.md`:
-- "Monte sua cesta" (escolhe a embalagem Pequena/Média/Grande, depois os itens, de um
-- mínimo a um máximo, somando o valor) e "Chocolate Quente" (este não é um produto: ao
-- tocar, escolhe Preto ou Branco — e ESSES são os produtos).
--
-- 🔑 **O item de escolha é uma linha do catálogo SEM produto**, com nome, descrição e foto
-- próprios, que oferece uma lista de produtos. O pedido leva o PRODUTO escolhido — o painel,
-- o "lançar no PDV" e o PDF não mudam de conta.
-- ⚠️ As consultas que fazem `JOIN produtos ON p.id = i.id_produto` deixam o item de escolha
-- de fora sozinhas: é o comportamento certo para A/B, atenção, anúncios e cartões nesta
-- primeira fase. Quem precisa dele (feed, site, cadastro, pedido) o pede de propósito.

ALTER TABLE catalogo_itens ADD COLUMN IF NOT EXISTS tipo varchar(8) NOT NULL DEFAULT 'PRODUTO';
ALTER TABLE catalogo_itens ALTER COLUMN id_produto DROP NOT NULL;
ALTER TABLE catalogo_itens ADD COLUMN IF NOT EXISTS nome        varchar(120);
ALTER TABLE catalogo_itens ADD COLUMN IF NOT EXISTS nome_en     varchar(120);
ALTER TABLE catalogo_itens ADD COLUMN IF NOT EXISTS nome_de     varchar(120);
ALTER TABLE catalogo_itens ADD COLUMN IF NOT EXISTS descricao    text;
ALTER TABLE catalogo_itens ADD COLUMN IF NOT EXISTS descricao_en text;
ALTER TABLE catalogo_itens ADD COLUMN IF NOT EXISTS descricao_de text;
-- A foto, com as mesmas colunas da seção: `guardar_foto` serve aos três.
ALTER TABLE catalogo_itens ADD COLUMN IF NOT EXISTS foto_url     text;
ALTER TABLE catalogo_itens ADD COLUMN IF NOT EXISTS foto_nome    varchar(255);
ALTER TABLE catalogo_itens ADD COLUMN IF NOT EXISTS foto_bytes   integer;
ALTER TABLE catalogo_itens ADD COLUMN IF NOT EXISTS foto_em      timestamptz;

-- 🔑 PRODUTO tem produto; ESCOLHA tem nome e NÃO tem produto. O banco garante, não a rota.
DO $$ BEGIN
    ALTER TABLE catalogo_itens ADD CONSTRAINT ck_catalogo_item_tipo CHECK (
        (tipo = 'PRODUTO' AND id_produto IS NOT NULL)
     OR (tipo = 'ESCOLHA' AND id_produto IS NULL AND nullif(btrim(nome), '') IS NOT NULL));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- As opções do item de escolha: cada uma é um PRODUTO, com um rótulo curto opcional
-- ("Branco" no lugar de "Chocolate Quente Branco").
-- ⚠️ Sem `ON DELETE CASCADE` no produto, como em `catalogo_itens`: produto se desativa.
CREATE TABLE IF NOT EXISTS catalogo_item_escolhas (
    id         serial PRIMARY KEY,
    id_item    integer NOT NULL REFERENCES catalogo_itens(id) ON DELETE CASCADE,
    id_produto integer NOT NULL REFERENCES produtos(id),
    rotulo     varchar(60),
    rotulo_en  varchar(60),
    rotulo_de  varchar(60),
    ordem      smallint NOT NULL DEFAULT 0,
    CONSTRAINT ux_catalogo_item_escolha UNIQUE (id_item, id_produto)
);
CREATE INDEX IF NOT EXISTS ix_catalogo_item_escolha_produto ON catalogo_item_escolhas (id_produto);

-- 🔑 **O mesmo item mais de uma vez** (decisão 1 do dono: "2 geleias"). Padrão FALSO: os
-- grupos que existem continuam marcando cada opção uma vez só. Com ele ligado, mínimo e
-- máximo contam UNIDADES.
ALTER TABLE produto_adicionais_grupos ADD COLUMN IF NOT EXISTS permite_repetir boolean NOT NULL DEFAULT false;

-- 🔑 **Incluso** (decisão 2): a opção entra por R$ 0 mesmo apontando para um produto com
-- preço — o item que já vem no preço da embalagem.
ALTER TABLE produto_adicionais_opcoes ADD COLUMN IF NOT EXISTS incluso boolean NOT NULL DEFAULT false;

-- O catálogo montado AQUI: categorias, subcategorias e os produtos de cada uma.
--
-- 🔑 **Pedido do dono (22/09/2026):** *"vamos adicionar a Origem Produtos.
-- Quando for esta origem, ao listar os catálogos, ao clicar sobre vai abrir uma
-- nova página para configuração. Neste, podemos criar Categorias (exemplo: Menu
-- Principal) e suas SubCategorias (exemplo: Pra Dividir), cada item terá o Nome,
-- Descrição e uma foto. Após isto, podemos vincular os produtos disponíveis no
-- PDV para a subcategoria. Somente produtos ativos."*
--
-- 🔑 **É a segunda origem que a 079 previu**, com estas palavras: *"no dia em
-- que entrar a segunda origem — o cardápio montado item a item aqui dentro — os
-- catálogos antigos precisam continuar sabendo de onde vieram"*. Por isso
-- `origem` é coluna desde aquele dia, e nada precisa ser reescrito agora.
-- ⚠️ `PRODUTOS` não substitui `PDF`: são dois jeitos de publicar um cardápio, e
-- a casa escolhe por catálogo.

-- ---------------------------------------------------------------------------
-- As categorias do catálogo
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS catalogo_categorias (
    id          serial PRIMARY KEY,
    -- ⚠️ **`ON DELETE CASCADE`**: apagar o catálogo leva o conteúdo junto. Um
    -- catálogo só se exclui em RASCUNHO (regra da 079), e rascunho que se apaga
    -- não deve deixar categorias órfãs esperando um pai que não volta.
    id_catalogo integer NOT NULL REFERENCES catalogos(id) ON DELETE CASCADE,
    nome        varchar(120) NOT NULL,
    descricao   varchar(500),
    -- 🔑 **Foto na categoria, não só no produto** — foi o que o dono pediu:
    -- *"cada item terá o Nome, Descrição e uma foto"*. É a imagem que abre a
    -- seção no cardápio.
    foto_url    varchar(255),
    foto_nome   varchar(255),
    foto_bytes  integer,
    foto_em     timestamptz,
    -- ⚠️ **A ordem é do CARDÁPIO, não alfabética.** "Entradas" antes de
    -- "Sobremesas" não é ordem de nome nenhuma — é a sequência da refeição, e
    -- só a casa sabe qual é.
    ordem       smallint NOT NULL DEFAULT 0,
    criado_em   timestamptz NOT NULL DEFAULT now(),
    -- 🔑 Alvo da chave composta lá embaixo: é o que permite ao BANCO garantir
    -- que a subcategoria de um item é da categoria daquele item.
    CONSTRAINT ux_catalogo_categoria_id UNIQUE (id, id_catalogo)
);

-- ⚠️ **Nome repetido no MESMO catálogo é engano, e o índice é quem garante.**
-- `lower()` porque "Bebidas" e "bebidas" são a mesma seção para quem lê.
CREATE UNIQUE INDEX IF NOT EXISTS ux_catalogo_categoria_nome
    ON catalogo_categorias (id_catalogo, lower(nome));

-- ---------------------------------------------------------------------------
-- As subcategorias — e elas são OPCIONAIS
-- ---------------------------------------------------------------------------
-- 🔑 **Decisão do dono (22/09/2026):** categoria pode ter produto direto, sem
-- subcategoria. Cardápio de verdade tem os dois casos — "Menu Principal" se
-- divide em "Pra Dividir" e "Pratos", mas "Bebidas" costuma ser uma lista só.
-- ⚠️ Obrigar a subcategoria faria a casa criar uma com o mesmo nome da
-- categoria, só para pendurar os itens — e o site mostraria o título duas vezes.
CREATE TABLE IF NOT EXISTS catalogo_subcategorias (
    id           serial PRIMARY KEY,
    id_categoria integer NOT NULL
                 REFERENCES catalogo_categorias(id) ON DELETE CASCADE,
    nome         varchar(120) NOT NULL,
    descricao    varchar(500),
    foto_url     varchar(255),
    foto_nome    varchar(255),
    foto_bytes   integer,
    foto_em      timestamptz,
    ordem        smallint NOT NULL DEFAULT 0,
    criado_em    timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ux_catalogo_subcategoria_id UNIQUE (id, id_categoria)
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_catalogo_subcategoria_nome
    ON catalogo_subcategorias (id_categoria, lower(nome));

-- ---------------------------------------------------------------------------
-- Os produtos pendurados
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS catalogo_itens (
    id              serial PRIMARY KEY,
    -- 🔑 **A categoria é SEMPRE obrigatória; a subcategoria, não.** Assim o item
    -- sabe onde mora nos dois casos, e a consulta do cardápio é uma só.
    id_categoria    integer NOT NULL
                    REFERENCES catalogo_categorias(id) ON DELETE CASCADE,
    id_subcategoria integer,
    -- ⚠️ **Sem `ON DELETE CASCADE` aqui, de propósito.** Produto não se apaga
    -- neste sistema — se desativa (regra da casa). Um cascade daria a impressão
    -- de que apagar é caminho normal.
    id_produto      integer NOT NULL REFERENCES produtos(id),
    ordem           smallint NOT NULL DEFAULT 0,
    criado_em       timestamptz NOT NULL DEFAULT now(),
    -- 🔑 **Quem GARANTE que a subcategoria é desta categoria é o banco**, pela
    -- chave composta — não a rota. ⚠️ E com `id_subcategoria` NULO a chave não
    -- é cobrada (`MATCH SIMPLE`, o padrão), que é exatamente o item pendurado
    -- direto na categoria.
    CONSTRAINT fk_catalogo_item_subcategoria
        FOREIGN KEY (id_subcategoria, id_categoria)
        REFERENCES catalogo_subcategorias (id, id_categoria) ON DELETE CASCADE
);

-- 🔑 **Decisão do dono:** o mesmo produto PODE estar em mais de uma
-- subcategoria — uma porção serve a "Pra Dividir" e a "Menu Principal" —, e o
-- que se impede é a repetição DENTRO da mesma lista, que é sempre engano.
-- ⚠️ **São dois índices porque `NULL` não repete em índice único**: um par
-- (NULL, 42) nunca colidiria com outro (NULL, 42). O parcial separa os dois
-- mundos — com subcategoria e sem ela.
CREATE UNIQUE INDEX IF NOT EXISTS ux_catalogo_item_na_subcategoria
    ON catalogo_itens (id_subcategoria, id_produto)
 WHERE id_subcategoria IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS ux_catalogo_item_na_categoria
    ON catalogo_itens (id_categoria, id_produto)
 WHERE id_subcategoria IS NULL;

CREATE INDEX IF NOT EXISTS ix_catalogo_item_produto
    ON catalogo_itens (id_produto);

-- 120 — Cartões de conteúdo no Cardápio Vivo: a abertura do cardápio, a abertura de cada seção
-- e cartões livres entre os pratos.
--
-- 🔑 Pedido do dono (16/10/2026): "quando estamos em formato de feed, gostaria de colocar algo
-- entre os pratos que vai além de pratos — por exemplo, um cardápio de massas, e antes postar
-- um vídeo, texto ou foto com uma introdução, bem como seções entre os pratos". Decisões dele:
-- abertura de seção AUTOMÁTICA (a foto e a descrição que a seção já tem), vídeo SUBIDO no
-- sistema e cartões SÓ no feed (o site e o PDF continuam só com os pratos).
--
-- ⚠️ O cartão NÃO é um item do catálogo: item é produto (preço, PDV, estoque, A/B), e um
-- `id_produto` nulo em `catalogo_itens` espalharia "e se não tiver produto?" por todo canto
-- que lê o cardápio. Tabela própria.
-- 🔑 **A posição é "antes do prato X"**, não um número de ordem: os pratos se reordenam (as
-- setas, o vencedor de um teste A/B de ordem) e o cartão continua colado no prato que ele
-- apresenta. Sem prato (ou o prato saiu da lista), o cartão vai ao FIM da lista dele.
-- `id_categoria` nulo = abertura do cardápio (antes de tudo).
-- Idempotente; ⚠️ não editar depois de promovida (o db_updater roda de novo se o checksum mudar).

CREATE TABLE IF NOT EXISTS catalogo_cartoes (
    id               serial PRIMARY KEY,
    id_catalogo      integer NOT NULL REFERENCES catalogos(id) ON DELETE CASCADE,
    id_categoria     integer REFERENCES catalogo_categorias(id) ON DELETE CASCADE,
    id_subcategoria  integer REFERENCES catalogo_subcategorias(id) ON DELETE CASCADE,
    antes_do_item    integer REFERENCES catalogo_itens(id) ON DELETE SET NULL,
    titulo           varchar(120),
    texto            varchar(700),
    titulo_en        varchar(120),
    titulo_de        varchar(120),
    texto_en         varchar(700),
    texto_de         varchar(700),
    traducao_editada text[] NOT NULL DEFAULT '{}',
    traducao_origem  varchar(64),
    traducao_em      timestamptz,
    foto_url         varchar(300),
    video_url        varchar(300),
    video_capa_url   varchar(300),
    video_segundos   numeric(5, 1),
    -- O botão "Ver o prato": leva a um prato do mesmo cardápio.
    id_item_link     integer REFERENCES catalogo_itens(id) ON DELETE SET NULL,
    ativo            boolean NOT NULL DEFAULT true,
    criado_em        timestamptz NOT NULL DEFAULT now(),
    criado_por       integer REFERENCES usuarios(id) ON DELETE SET NULL,
    -- ⚠️ Sem CHECK de "tem conteúdo": o cartão de SÓ vídeo nasce vazio e recebe o vídeo no
    -- passo seguinte. Quem esconde o cartão vazio é o feed.
    CONSTRAINT ck_cartao_sub_tem_categoria CHECK (id_subcategoria IS NULL OR id_categoria IS NOT NULL)
);
CREATE INDEX IF NOT EXISTS ix_catalogo_cartoes_catalogo ON catalogo_cartoes (id_catalogo);

-- 🔑 A abertura AUTOMÁTICA de seção usa a foto e a descrição que a seção já tem; o vídeo é
-- a única coisa nova, e ganha da foto quando existe.
ALTER TABLE catalogo_categorias ADD COLUMN IF NOT EXISTS video_url varchar(300);
ALTER TABLE catalogo_categorias ADD COLUMN IF NOT EXISTS video_capa_url varchar(300);
ALTER TABLE catalogo_subcategorias ADD COLUMN IF NOT EXISTS video_url varchar(300);
ALTER TABLE catalogo_subcategorias ADD COLUMN IF NOT EXISTS video_capa_url varchar(300);

-- ---------------------------------------------------------------- a medição
-- `viu_cartao` (o cartão livre ou a abertura do cardápio) e `viu_secao` (a abertura
-- automática da seção, pelo `id_categoria`/`id_subcategoria` que o evento já leva).
-- `clicou_cartao` = o "Ver o prato".
ALTER TABLE cardapio_eventos ADD COLUMN IF NOT EXISTS id_cartao integer;
ALTER TABLE cardapio_eventos ADD COLUMN IF NOT EXISTS id_subcategoria integer;
ALTER TABLE cardapio_eventos DROP CONSTRAINT IF EXISTS cardapio_eventos_tipo_check;
ALTER TABLE cardapio_eventos ADD CONSTRAINT cardapio_eventos_tipo_check CHECK (tipo IN (
    'abriu_cardapio', 'viu_item', 'tocou_categoria', 'abriu_detalhe', 'adicionou', 'removeu',
    'enviou_pedido', 'chamou_garcom', 'pediu_conta', 'saiu',
    'deslizou_frente', 'deslizou_tras', 'favoritou', 'desfavoritou', 'abriu_personalizacao',
    'escolheu_opcao', 'abriu_hub', 'clicou_avaliacao', 'clicou_wifi',
    'viu_cartao', 'viu_secao', 'clicou_cartao'));
CREATE INDEX IF NOT EXISTS ix_cardapio_evento_cartao ON cardapio_eventos (id_cartao, quando)
    WHERE id_cartao IS NOT NULL;

COMMENT ON TABLE catalogo_cartoes IS
  'Cartões de conteúdo do Cardápio Vivo (120): abertura do cardápio (sem categoria) e cartões '
  'entre os pratos, colados ANTES de um prato (ou no fim da lista). Só no feed.';

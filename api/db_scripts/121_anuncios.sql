-- 121 — Anúncios no Cardápio Vivo (fase 1) e as aberturas de seção configuráveis.
--
-- 🔑 Pedido do dono (16/10/2026): "um plano de anúncios no meio do cardápio" — texto, foto ou
-- vídeo, com período e dias; externo (outra marca) ou da casa (o catálogo do Dia dos
-- Namorados); com links; formas e tempo de exibição; métricas; e nada pesado: "algo bem
-- orgânico". Respostas dele: a casa cadastra e apresenta o RELATÓRIO ao parceiro (sem acesso
-- de anunciante); na mesa E pelo link; regras de partida 5º prato / 8 de distância / máximo 2,
-- ajustáveis; grupo de controle de 10% sem anúncio (fase 2).
--
-- ⚠️ Anúncio NÃO é cartão (120): cartão é editorial e fixo, colado num prato; anúncio é
-- dinâmico — tem período e o feed decide quando e qual mostrar, pelas regras da casa.
-- ⚠️ É da LOJA (`id_unidade`), como os Cardápios Vivos: a matriz e a filial anunciam o seu.
-- Idempotente; ⚠️ não editar depois de promovida (o db_updater roda de novo se o checksum mudar).

CREATE TABLE IF NOT EXISTS cardapio_anuncios (
    id               serial PRIMARY KEY,
    id_unidade       integer NOT NULL REFERENCES unidades(id) ON DELETE CASCADE,
    -- O nome para a casa achar ("Cerveja X — outubro"); o cliente não vê.
    nome             varchar(120) NOT NULL,
    -- 🔑 CASA = um catálogo ou prato da própria casa ("Da casa"); EXTERNO = outra marca
    -- ("Patrocinado"). A etiqueta no feed sai daqui: propaganda tem de ser reconhecível.
    origem           varchar(7) NOT NULL DEFAULT 'CASA' CHECK (origem IN ('CASA', 'EXTERNO')),
    anunciante       varchar(120),
    titulo           varchar(120),
    texto            varchar(500),
    titulo_en        varchar(120),
    titulo_de        varchar(120),
    texto_en         varchar(500),
    texto_de         varchar(500),
    traducao_editada text[] NOT NULL DEFAULT '{}',
    traducao_origem  varchar(64),
    traducao_em      timestamptz,
    foto_url         varchar(300),
    video_url        varchar(300),
    video_capa_url   varchar(300),
    video_segundos   numeric(5, 1),
    -- O botão: abrir um catálogo da casa, ir a um prato deste cardápio, ou um link.
    acao             varchar(8) NOT NULL DEFAULT 'NENHUMA'
                     CHECK (acao IN ('NENHUMA', 'CATALOGO', 'PRATO', 'LINK')),
    acao_catalogo    integer REFERENCES catalogos(id) ON DELETE SET NULL,
    acao_item        integer REFERENCES catalogo_itens(id) ON DELETE SET NULL,
    acao_url         varchar(500),
    acao_rotulo      varchar(40),
    -- Quando: período (datas), dias da semana (1=seg … 7=dom), faixa de horário e dias especiais
    -- das Reservas — a MESMA regra das seções do Cardápio Vivo.
    inicio           date,
    fim              date,
    dias             smallint[],
    hora_de          time,
    hora_ate         time,
    horario_especial boolean NOT NULL DEFAULT false,
    -- Onde: quais Cardápios Vivos (catálogos; nulo = todos da loja) e por qual porta.
    cardapios        integer[],
    canal            varchar(5) NOT NULL DEFAULT 'AMBOS' CHECK (canal IN ('AMBOS', 'MESA', 'LINK')),
    -- Peso no sorteio: 2 aparece o dobro de 1.
    peso             smallint NOT NULL DEFAULT 1 CHECK (peso BETWEEN 1 AND 10),
    ativo            boolean NOT NULL DEFAULT true,
    criado_em        timestamptz NOT NULL DEFAULT now(),
    criado_por       integer REFERENCES usuarios(id) ON DELETE SET NULL,
    CONSTRAINT ck_anuncio_periodo CHECK (inicio IS NULL OR fim IS NULL OR inicio <= fim),
    CONSTRAINT ck_anuncio_faixa CHECK ((hora_de IS NULL) = (hora_ate IS NULL))
);
CREATE INDEX IF NOT EXISTS ix_cardapio_anuncios_loja ON cardapio_anuncios (id_unidade, ativo);

-- 🔑 As regras de frequência são da CASA (uma por loja), ajustáveis na tela dos anúncios.
-- ⚠️ Colunas fora do `_PADRAO` da configuração: o "Aparência e opções da casa" grava só o que
-- é dele, e estas não voltam ao padrão quando alguém mexe na cor.
ALTER TABLE cardapio_config ADD COLUMN IF NOT EXISTS anuncio_depois_de smallint NOT NULL DEFAULT 5;
ALTER TABLE cardapio_config ADD COLUMN IF NOT EXISTS anuncio_intervalo smallint NOT NULL DEFAULT 8;
ALTER TABLE cardapio_config ADD COLUMN IF NOT EXISTS anuncio_maximo smallint NOT NULL DEFAULT 2;
-- Na mesa, menos: quem está sentado quer achar o prato.
ALTER TABLE cardapio_config ADD COLUMN IF NOT EXISTS anuncio_maximo_mesa smallint NOT NULL DEFAULT 1;

-- ---------------------------------------------------------------- as aberturas de seção
-- 🔑 "Isto poderia ser configurado" (o dono, mesmo pedido): por Cardápio Vivo, AUTOMATICA
-- (seção com foto ou vídeo abre), SO_VIDEO ou NUNCA; e cada seção pode desligar a sua.
ALTER TABLE cardapio_vivos ADD COLUMN IF NOT EXISTS aberturas varchar(10) NOT NULL DEFAULT 'AUTOMATICA';
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_vivo_aberturas') THEN
        ALTER TABLE cardapio_vivos ADD CONSTRAINT ck_vivo_aberturas
            CHECK (aberturas IN ('AUTOMATICA', 'SO_VIDEO', 'NUNCA'));
    END IF;
END $$;
ALTER TABLE catalogo_categorias ADD COLUMN IF NOT EXISTS abertura boolean NOT NULL DEFAULT true;
ALTER TABLE catalogo_subcategorias ADD COLUMN IF NOT EXISTS abertura boolean NOT NULL DEFAULT true;

-- ---------------------------------------------------------------- a medição
ALTER TABLE cardapio_eventos ADD COLUMN IF NOT EXISTS id_anuncio integer;
ALTER TABLE cardapio_eventos DROP CONSTRAINT IF EXISTS cardapio_eventos_tipo_check;
ALTER TABLE cardapio_eventos ADD CONSTRAINT cardapio_eventos_tipo_check CHECK (tipo IN (
    'abriu_cardapio', 'viu_item', 'tocou_categoria', 'abriu_detalhe', 'adicionou', 'removeu',
    'enviou_pedido', 'chamou_garcom', 'pediu_conta', 'saiu',
    'deslizou_frente', 'deslizou_tras', 'favoritou', 'desfavoritou', 'abriu_personalizacao',
    'escolheu_opcao', 'abriu_hub', 'clicou_avaliacao', 'clicou_wifi',
    'viu_cartao', 'viu_secao', 'clicou_cartao',
    'viu_anuncio', 'clicou_anuncio'));
CREATE INDEX IF NOT EXISTS ix_cardapio_evento_anuncio ON cardapio_eventos (id_anuncio, quando)
    WHERE id_anuncio IS NOT NULL;

COMMENT ON TABLE cardapio_anuncios IS
  'Anúncios do Cardápio Vivo (121): da casa ou de outra marca, com período e regras de exibição '
  'da loja (cardapio_config.anuncio_*). Só no feed.';

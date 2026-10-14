-- 114 — Cardápio Vivo: a tela de entrada (Hub), favoritos e os eventos novos. Idempotente.
-- Complemento do dono de 14/10/2026 (ver `docs/cardapio-vivo-estudo.md`, seção 0b).

-- ---------------------------------------------------------------- a loja
-- 🔑 **No cadastro da LOJA, não na configuração do cardápio**: o link de avaliação e o
-- Wi-Fi são da casa, e servem a mais coisas que o feed (o site, um dia a placa do balcão).
ALTER TABLE unidades
    ADD COLUMN IF NOT EXISTS google_avaliacao_url varchar(300),
    ADD COLUMN IF NOT EXISTS wifi_rede            varchar(64),
    -- ⚠️ A senha do Wi-Fi de CLIENTE é pública por natureza (está na parede): texto puro.
    ADD COLUMN IF NOT EXISTS wifi_senha           varchar(64);

-- ---------------------------------------------------------------- o Hub
-- Cada botão do Hub se liga à parte; "Ver cardápio" está sempre lá. Com os dois desligados
-- (ou sem o dado na loja), o Hub é pulado e o cliente cai direto no feed.
ALTER TABLE cardapio_config
    ADD COLUMN IF NOT EXISTS hub_avaliacao boolean NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS hub_wifi      boolean NOT NULL DEFAULT false;

-- ---------------------------------------------------------------- eventos novos
ALTER TABLE cardapio_eventos DROP CONSTRAINT IF EXISTS cardapio_eventos_tipo_check;
ALTER TABLE cardapio_eventos ADD CONSTRAINT cardapio_eventos_tipo_check CHECK (tipo IN (
    'abriu_cardapio', 'viu_item', 'tocou_categoria', 'abriu_detalhe', 'adicionou', 'removeu',
    'enviou_pedido', 'chamou_garcom', 'pediu_conta', 'saiu',
    'deslizou_frente', 'deslizou_tras', 'favoritou', 'desfavoritou', 'abriu_personalizacao',
    'escolheu_opcao', 'abriu_hub', 'clicou_avaliacao', 'clicou_wifi'));

-- ---------------------------------------------------------------- o que sobra da retenção
ALTER TABLE cardapio_agregados_dia
    ADD COLUMN IF NOT EXISTS favoritos     integer NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS deslizes_tras integer NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS personalizacoes integer NOT NULL DEFAULT 0;

-- 🔑 **O resumo da LOJA por dia**: sessões abertas e ENGAJADAS, e os cliques do Hub. Sem
-- isto, a retenção apagaria a base dos indicadores do topo do painel.
-- "Sessão engajada" = ≥ 3 itens vistos OU 1 interação (favorito, personalização, adição).
CREATE TABLE IF NOT EXISTS cardapio_resumo_dia (
    dia              date    NOT NULL,
    id_unidade       integer NOT NULL REFERENCES unidades(id) ON DELETE CASCADE,
    sessoes          integer NOT NULL DEFAULT 0,
    engajadas        integer NOT NULL DEFAULT 0,
    hubs             integer NOT NULL DEFAULT 0,
    cliques_avaliacao integer NOT NULL DEFAULT 0,
    cliques_wifi     integer NOT NULL DEFAULT 0,
    PRIMARY KEY (dia, id_unidade)
);

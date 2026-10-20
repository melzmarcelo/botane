-- 125 — Anúncios do Cardápio Vivo, fases 2 e 3: o ritmo que aprende, a relevância, o grupo de
-- controle e as variações com vencedora.
--
-- 🔑 Pedido do dono (16/10/2026), na proposta em três fases que ele aprovou: "um ritmo que
-- aprende", "relevância pelo que a pessoa está vendo", "grupo de controle de 10% pode" e
-- "variações". A fase 1 é a 121.
-- ⚠️ O que a pessoa fez continua na sessão anônima: o grupo e a variante são do NAVEGADOR da
-- visita, nunca de alguém.
-- Idempotente; ⚠️ não editar depois de promovida (o db_updater roda de novo se o checksum mudar).

-- ---------------------------------------------------------------- fase 2
-- 🔑 Relevância: as seções em que o anúncio "combina". Nulo = combina com tudo. O anúncio que
-- combina com a seção do prato seguinte tem o peso multiplicado ali (a tela decide).
ALTER TABLE cardapio_anuncios ADD COLUMN IF NOT EXISTS secoes integer[];

-- 🔑 Grupo de controle: a fatia das visitas que NÃO vê anúncio nenhum — é ela que diz se os
-- anúncios mudam o que a pessoa faz no cardápio. 10% é o que o dono aceitou; 0 desliga.
ALTER TABLE cardapio_config ADD COLUMN IF NOT EXISTS anuncio_controle smallint NOT NULL DEFAULT 10;
-- 🔑 O ritmo que aprende: pulou (menos de 1,5 s) → a distância até o próximo dobra; dois vistos
-- sem toque → acabaram os anúncios desta visita. Desligável.
ALTER TABLE cardapio_config ADD COLUMN IF NOT EXISTS anuncio_recuo boolean NOT NULL DEFAULT true;
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_config_anuncio_controle') THEN
        ALTER TABLE cardapio_config ADD CONSTRAINT ck_config_anuncio_controle
            CHECK (anuncio_controle BETWEEN 0 AND 50);
    END IF;
END $$;

-- O grupo da visita gravado em cada evento: a comparação não depende de o percentual de hoje ser
-- o de ontem. Nulo = a visita não tinha anúncio para ver (ou é anterior à 125).
ALTER TABLE cardapio_eventos ADD COLUMN IF NOT EXISTS grupo_anuncio varchar(8);
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_evento_grupo_anuncio') THEN
        ALTER TABLE cardapio_eventos ADD CONSTRAINT ck_evento_grupo_anuncio
            CHECK (grupo_anuncio IS NULL OR grupo_anuncio IN ('CONTROLE', 'EXPOSTO'));
    END IF;
END $$;

-- ---------------------------------------------------------------- fase 3
-- 🔑 Variações do TEXTO do anúncio: o título, o texto e o rótulo do botão. O próprio anúncio é a
-- variação "A" (original); estas são B, C… A mídia e o destino são os do anúncio.
CREATE TABLE IF NOT EXISTS cardapio_anuncio_variantes (
    id               serial PRIMARY KEY,
    id_anuncio       integer NOT NULL REFERENCES cardapio_anuncios(id) ON DELETE CASCADE,
    titulo           varchar(120),
    texto            varchar(500),
    acao_rotulo      varchar(40),
    titulo_en        varchar(120),
    titulo_de        varchar(120),
    texto_en         varchar(500),
    texto_de         varchar(500),
    traducao_editada text[] NOT NULL DEFAULT '{}',
    traducao_origem  varchar(64),
    traducao_em      timestamptz,
    ativo            boolean NOT NULL DEFAULT true,
    criado_em        timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_anuncio_variantes ON cardapio_anuncio_variantes (id_anuncio);

-- Qual variação a visita viu. Nulo = a original (ou anterior à 125). ⚠️ Sem chave estrangeira: a
-- variação apagada (ou a vencedora aplicada) não pode apagar a medição.
ALTER TABLE cardapio_eventos ADD COLUMN IF NOT EXISTS id_variante integer;
CREATE INDEX IF NOT EXISTS ix_eventos_variante ON cardapio_eventos (id_anuncio, id_variante)
    WHERE id_variante IS NOT NULL;

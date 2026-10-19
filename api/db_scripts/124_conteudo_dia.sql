-- 124 · O resumo diário de anúncios, cartões e aberturas de seção (1.1.109).
--
-- 🔑 Proposta da análise de 17/10/2026: `cardapio_agregados_dia` guarda só os PRATOS. O que o
-- feed mostra entre eles — anúncio, cartão, abertura de seção — morria com o bruto na retenção
-- da loja (de 1 a 60 meses), e o relatório que a casa apresenta ao anunciante perdia o começo de
-- uma campanha longa. O agendador da madrugada resume aqui o dia de ontem, junto com os pratos.
--
-- Uma linha por dia, loja, tipo, o que foi visto, Cardápio Vivo e canal (mesa ou link).
-- * `id_ref`: o anúncio, o cartão ou a CATEGORIA da abertura; `id_sub`: a subcategoria da
--   abertura (0 = nenhuma). `id_catalogo` 0 = evento de antes da 122, sem cardápio.
-- * `soma_ms` + `vistas` refazem a média de segundos; `sessoes` é a contagem DISTINTA do dia —
--   somar dias conta duas vezes quem voltou noutro dia, e o relatório diz isso.
-- ⚠️ Sem FK para o anúncio/cartão: o resumo sobrevive a quem foi apagado, como o evento.
-- ⚠️ Idempotente: só cria a tabela. O agendador refaz cada dia que resume.

CREATE TABLE IF NOT EXISTS cardapio_conteudo_dia (
    dia             date        NOT NULL,
    id_unidade      integer     NOT NULL REFERENCES unidades(id) ON DELETE CASCADE,
    tipo            varchar(8)  NOT NULL CHECK (tipo IN ('ANUNCIO', 'CARTAO', 'SECAO')),
    id_ref          integer     NOT NULL,
    id_sub          integer     NOT NULL DEFAULT 0,
    id_catalogo     integer     NOT NULL DEFAULT 0,
    canal           varchar(4)  NOT NULL CHECK (canal IN ('MESA', 'LINK')),
    vistas          integer     NOT NULL DEFAULT 0,
    sessoes         integer     NOT NULL DEFAULT 0,
    soma_ms         bigint      NOT NULL DEFAULT 0,
    pulados         integer     NOT NULL DEFAULT 0,
    cliques         integer     NOT NULL DEFAULT 0,
    sessoes_clicaram integer    NOT NULL DEFAULT 0,
    PRIMARY KEY (dia, id_unidade, tipo, id_ref, id_sub, id_catalogo, canal)
);

CREATE INDEX IF NOT EXISTS ix_conteudo_dia_ref ON cardapio_conteudo_dia (tipo, id_ref, dia);

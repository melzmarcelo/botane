-- 117 — Vários Cardápios Vivos por loja. Idempotente.
--
-- 🔑 **Pedido do dono (15/10/2026):** *"hoje podemos ter somente 1 cardápio vivo, poderíamos
-- ter mais de um. Exemplo: no Botané vai ter um que é o da cafeteria, e ela pode configurar
-- outro que é destinado ao Catering."*
--
-- Até a 116, `cardapio_config` tinha a LOJA como chave e um `id_catalogo` só. Agora:
--   * `cardapio_config` fica com o que é da CASA: aparência (cores, fonte, logo), Hub,
--     esconder esgotado e retenção — decisão do dono: um layout só para o site inteiro;
--   * `cardapio_vivos` tem cada Cardápio Vivo: o catálogo, o nome no link, se é o PRINCIPAL
--     (o que o QR da mesa abre) e o comportamento — modo, confirmação, horário do pedido,
--     chamar garçom.
-- ⚠️ As colunas de comportamento de `cardapio_config` (modo, exige_confirmacao, pedido_hora_*,
-- chamar_garcom) FICAM, sem uso: tirá-las agora quebraria o contêiner antigo, que convive com
-- o novo por um ou dois minutos no deploy e ainda as lê.

CREATE TABLE IF NOT EXISTS cardapio_vivos (
    id_unidade        integer NOT NULL REFERENCES unidades(id) ON DELETE CASCADE,
    id_catalogo       integer NOT NULL REFERENCES catalogos(id) ON DELETE CASCADE,
    -- O nome no link: `/c/{loja}?cardapio=catering`. Minúsculas, números e hífen.
    slug              varchar(40) NOT NULL CHECK (slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'),
    -- 🔑 O que o QR da MESA abre (decisão do dono). Os outros, só pelo link.
    principal         boolean NOT NULL DEFAULT false,
    modo              varchar(8) NOT NULL DEFAULT 'VITRINE' CHECK (modo IN ('VITRINE', 'PEDIDO')),
    exige_confirmacao boolean NOT NULL DEFAULT true,
    pedido_hora_de    time,
    pedido_hora_ate   time,
    chamar_garcom     boolean NOT NULL DEFAULT false,
    atualizado_por    integer REFERENCES usuarios(id) ON DELETE SET NULL,
    atualizado_em     timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (id_unidade, id_catalogo),
    CONSTRAINT ck_vivo_horario CHECK ((pedido_hora_de IS NULL) = (pedido_hora_ate IS NULL))
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_cardapio_vivo_slug ON cardapio_vivos (id_unidade, slug);
-- Um principal por loja — no máximo; a loja pode não ter nenhum (o QR da mesa diz "não achei").
CREATE UNIQUE INDEX IF NOT EXISTS ux_cardapio_vivo_principal ON cardapio_vivos (id_unidade)
    WHERE principal;

-- 🔑 **O que está no ar continua igual**: o catálogo que cada loja apontava vira o Cardápio
-- Vivo PRINCIPAL dela, com o comportamento que estava gravado.
INSERT INTO cardapio_vivos (id_unidade, id_catalogo, slug, principal, modo, exige_confirmacao,
                            pedido_hora_de, pedido_hora_ate, chamar_garcom)
SELECT c.id_unidade, c.id_catalogo, 'cardapio', true, c.modo, c.exige_confirmacao,
       c.pedido_hora_de, c.pedido_hora_ate, c.chamar_garcom
  FROM cardapio_config c
 WHERE c.id_catalogo IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM cardapio_vivos v WHERE v.id_unidade = c.id_unidade)
ON CONFLICT DO NOTHING;

-- ⚠️ `cardapio_config.id_catalogo` NÃO é zerado: o contêiner antigo ainda o lê no minuto em que
-- convive, e zerá-lo faria o QR da mesa responder 404 nesse minuto. Desta versão em diante
-- ninguém o lê nem o grava — a fonte é `cardapio_vivos`. (A migração roda uma vez só; a cópia
-- acima não se repete.)

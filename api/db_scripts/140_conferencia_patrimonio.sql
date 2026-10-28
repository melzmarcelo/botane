-- 140 — Patrimônio, etapa 3: a CONFERÊNCIA pelas plaquetas. Idempotente.
--
-- 🔑 **Pedido do dono (28/10/2026):** *"pode seguir com a etapa 3 do patrimônio"* — da
-- proposta de 27/10: abrir a conferência por setor, ler as plaquetas com o celular e
-- fechar com transferência (o bem achado em outro setor) ou baixa (o que não apareceu).
--
-- 🔑 **Não é inventário de estoque**: não conta quantidade, confere PRESENÇA de cada bem.
-- Nada aqui toca o razão.
-- 🔑 **A lista de esperados é uma FOTOGRAFIA da abertura** (`esperado`): o bem cadastrado
-- ou mudado de setor depois de aberta não muda o que se estava procurando. O bem lido que
-- não estava na lista entra como `esperado = false` — é o "estava aqui e o sistema dizia
-- que era de outro setor".

CREATE TABLE IF NOT EXISTS bem_conferencias (
    id            serial PRIMARY KEY,
    id_unidade    integer NOT NULL REFERENCES unidades(id),
    -- Nulo = a loja inteira.
    id_setor      integer REFERENCES setores(id),
    status        varchar(10) NOT NULL DEFAULT 'ABERTA'
                  CHECK (status IN ('ABERTA', 'FECHADA', 'CANCELADA')),
    observacao    varchar(300),
    aberta_por    integer REFERENCES usuarios(id),
    aberta_em     timestamptz NOT NULL DEFAULT now(),
    fechada_por   integer REFERENCES usuarios(id),
    fechada_em    timestamptz
);
-- ⚠️ **Uma conferência aberta por setor (ou da loja inteira) de cada vez** — duas abertas
-- sobre o mesmo setor dariam duas respostas para "este bem foi achado?". A sobreposição
-- loja-inteira × setor é recusada no serviço (o índice não enxerga).
CREATE UNIQUE INDEX IF NOT EXISTS ux_bem_conferencia_aberta
    ON bem_conferencias (id_unidade, coalesce(id_setor, 0)) WHERE status = 'ABERTA';

CREATE TABLE IF NOT EXISTS bem_conferencia_itens (
    id              serial PRIMARY KEY,
    id_conferencia  integer NOT NULL REFERENCES bem_conferencias(id) ON DELETE CASCADE,
    id_bem          integer NOT NULL REFERENCES bens(id) ON DELETE CASCADE,
    -- Estava na lista da abertura? `false` = achado aqui, mas o sistema o punha em outro setor.
    esperado        boolean NOT NULL,
    -- Como o bem estava na abertura (ou na leitura, para o de fora): o "de onde" da
    -- transferência e o "antes" da folha da conferência.
    id_setor_antes  integer REFERENCES setores(id) ON DELETE SET NULL,
    situacao_antes  varchar(15) NOT NULL,
    lido_em         timestamptz,
    lido_por        integer REFERENCES usuarios(id),
    -- O que o fechamento fez: CONFERIDO, TRANSFERIDO, NAO_ENCONTRADO (mantido) ou BAIXADO.
    resultado       varchar(15)
                    CHECK (resultado IN ('CONFERIDO', 'TRANSFERIDO', 'NAO_ENCONTRADO', 'BAIXADO')),
    UNIQUE (id_conferencia, id_bem)
);
CREATE INDEX IF NOT EXISTS ix_bem_conferencia_item_bem ON bem_conferencia_itens (id_bem);

-- A última vez que o bem foi VISTO numa conferência fechada.
ALTER TABLE bens ADD COLUMN IF NOT EXISTS conferido_em date;

INSERT INTO permissoes (chave, modulo, descricao, ordem) VALUES
    ('patrimonio.conferir', 'Patrimônio',
     'Abrir a conferência do patrimônio, ler as plaquetas e fechar (transferir e dar baixa)', 755)
ON CONFLICT (chave) DO UPDATE
    SET modulo = EXCLUDED.modulo, descricao = EXCLUDED.descricao, ordem = EXCLUDED.ordem;

-- ⚠️ Concedido AQUI (ver 091). Os mesmos que cadastram: o fechamento transfere e dá baixa.
INSERT INTO papel_permissoes (id_papel, chave)
SELECT p.id, 'patrimonio.conferir'
  FROM papeis p
 WHERE p.sistema AND p.nome IN ('Administrador', 'Gerente', 'Conferente / Estoque')
ON CONFLICT DO NOTHING;

-- 165 — Ordem de compra: aprovação do pedido.
-- Idempotente. Não reescreve dado: o que já está na lista continua onde está.
--
-- 🔑 **Pedido do dono (25/11/2026):** *"vamos criar um processo de aprovação de ordem de compra.
-- vamos criar um item em permissão para o papel que podem aprovar. quando o usuario sem permissão
-- realiza a ordem de compra este vai para a aprovação de um usuario que tem permissão. quando
-- aprovado ele vai para ser comprado"*.
--
-- 🔑 **O caminho passa a ser AGUARDANDO → A_COMPRAR → COMPRADO.** Quem tem
-- `compras.ordem_aprovar` pede direto em A_COMPRAR (já nasce aprovado por ele mesmo).
-- Recusado é situação própria (RECUSADO), e não CANCELADO: quem pediu precisa ver que foi
-- recusado, e por quê.
-- ⚠️ Linha antiga (antes desta migração) fica com `aprovado_por` nulo: é "de antes da aprovação",
-- e nada a manda de volta para aprovar.

ALTER TABLE ordem_compra_itens DROP CONSTRAINT IF EXISTS ordem_compra_itens_status_check;
ALTER TABLE ordem_compra_itens ADD CONSTRAINT ordem_compra_itens_status_check
    CHECK (status IN ('AGUARDANDO', 'A_COMPRAR', 'COMPRADO', 'CANCELADO', 'RECUSADO'));

ALTER TABLE ordem_compra_itens ADD COLUMN IF NOT EXISTS aprovado_em   timestamptz;
ALTER TABLE ordem_compra_itens ADD COLUMN IF NOT EXISTS aprovado_por  integer REFERENCES usuarios(id);
ALTER TABLE ordem_compra_itens ADD COLUMN IF NOT EXISTS recusado_em   timestamptz;
ALTER TABLE ordem_compra_itens ADD COLUMN IF NOT EXISTS recusado_por  integer REFERENCES usuarios(id);
ALTER TABLE ordem_compra_itens ADD COLUMN IF NOT EXISTS motivo_recusa varchar(300);

CREATE INDEX IF NOT EXISTS ix_ordem_aguardando
    ON ordem_compra_itens (id_unidade, criado_em) WHERE status = 'AGUARDANDO';

INSERT INTO permissoes (chave, modulo, descricao, ordem) VALUES
    ('compras.ordem_aprovar', 'Compras',
     'Aprovar ou recusar os pedidos da ordem de compra; o próprio pedido já nasce aprovado', 445)
ON CONFLICT (chave) DO UPDATE
    SET modulo = EXCLUDED.modulo, descricao = EXCLUDED.descricao, ordem = EXCLUDED.ordem;

-- ⚠️ Concedido AQUI (ver 091): Administrador e Gerente. Os outros papéis o dono dá na tela de
-- papéis, se quiser.
INSERT INTO papel_permissoes (id_papel, chave)
SELECT p.id, 'compras.ordem_aprovar'
  FROM papeis p
 WHERE p.sistema AND p.nome IN ('Administrador', 'Gerente')
ON CONFLICT DO NOTHING;

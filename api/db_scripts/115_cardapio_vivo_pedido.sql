-- 115 — Cardápio Vivo, fase 2: pedido pela mesa, chamar garçom/pedir a conta, objetivo e
-- margem do item, e a permissão do painel Atenção × Vendas. Idempotente.
-- Estudo em `docs/cardapio-vivo-estudo.md`.

-- ---------------------------------------------------------------- o pedido da MESA
-- 🔑 **Cada envio é um pedido, ligado à mesa e à sessão** (decisão 3 do dono). É a MESMA
-- tabela dos pedidos do site — mesmo painel, mesma numeração, mesmo "lançado no PDV".
-- ⚠️ **O que muda para o pedido do site: NADA.** Telefone e forma de pagamento deixam de ser
-- NOT NULL, mas a CHECK abaixo continua exigindo os dois fora do modo MESA.
ALTER TABLE pedidos DROP CONSTRAINT IF EXISTS pedidos_modo_check;
ALTER TABLE pedidos ADD CONSTRAINT pedidos_modo_check
    CHECK (modo IN ('RETIRADA', 'ENTREGA', 'MESA'));
ALTER TABLE pedidos ALTER COLUMN telefone DROP NOT NULL;
ALTER TABLE pedidos ALTER COLUMN forma_pagamento DROP NOT NULL;
ALTER TABLE pedidos DROP CONSTRAINT IF EXISTS ck_pedido_site_completo;
ALTER TABLE pedidos ADD CONSTRAINT ck_pedido_site_completo
    CHECK (modo = 'MESA' OR (telefone IS NOT NULL AND forma_pagamento IS NOT NULL));

ALTER TABLE pedidos
    ADD COLUMN IF NOT EXISTS origem    varchar(8) NOT NULL DEFAULT 'SITE',
    ADD COLUMN IF NOT EXISTS id_mesa   integer REFERENCES mesas(id) ON DELETE SET NULL,
    -- 🔑 O NOME da mesa, congelado: a mesa pode ser apagada ou renomeada depois, e o pedido
    -- de ontem continua dizendo para onde foi.
    ADD COLUMN IF NOT EXISTS mesa_nome varchar(20),
    ADD COLUMN IF NOT EXISTS id_sessao uuid;
ALTER TABLE pedidos DROP CONSTRAINT IF EXISTS ck_pedido_origem;
ALTER TABLE pedidos ADD CONSTRAINT ck_pedido_origem CHECK (origem IN ('SITE', 'CARDAPIO'));
-- ⚠️ No modo MESA, a origem é o cardápio e o nome da mesa existe. ⚠️ **NÃO o `id_mesa`**: o
-- `ON DELETE SET NULL` o zera quando a mesa é apagada, e uma CHECK sobre ele faria a
-- exclusão da mesa estourar por causa de um pedido antigo.
ALTER TABLE pedidos DROP CONSTRAINT IF EXISTS ck_pedido_mesa;
ALTER TABLE pedidos ADD CONSTRAINT ck_pedido_mesa
    CHECK (modo <> 'MESA' OR (mesa_nome IS NOT NULL AND origem = 'CARDAPIO'));
CREATE INDEX IF NOT EXISTS ix_pedido_sessao ON pedidos (id_sessao) WHERE id_sessao IS NOT NULL;

-- 🔑 **Os adicionais escolhidos, CONGELADOS no item** (nome e preço do momento do envio).
-- `preco_unitario` já inclui os adicionais, então total, painel e PDF não mudam de conta.
-- jsonb e não tabela: a troca de produtos na confirmação regrava os itens, e uma tabela
-- filha se perderia junto.
ALTER TABLE pedido_itens ADD COLUMN IF NOT EXISTS adicionais jsonb;

-- ---------------------------------------------------------------- chamar garçom / conta
CREATE TABLE IF NOT EXISTS cardapio_chamados (
    id           serial PRIMARY KEY,
    id_unidade   integer NOT NULL REFERENCES unidades(id) ON DELETE CASCADE,
    id_mesa      integer NOT NULL REFERENCES mesas(id) ON DELETE CASCADE,
    id_sessao    uuid,
    tipo         varchar(6) NOT NULL CHECK (tipo IN ('GARCOM', 'CONTA')),
    criado_em    timestamptz NOT NULL DEFAULT now(),
    atendido_em  timestamptz,
    atendido_por integer REFERENCES usuarios(id) ON DELETE SET NULL
);
-- ⚠️ **Um chamado ABERTO por mesa e tipo**: o cliente aperta dez vezes, o painel mostra um.
CREATE UNIQUE INDEX IF NOT EXISTS ux_chamado_aberto
    ON cardapio_chamados (id_mesa, tipo) WHERE atendido_em IS NULL;
CREATE INDEX IF NOT EXISTS ix_chamado_loja ON cardapio_chamados (id_unidade, criado_em);

-- ---------------------------------------------------------------- objetivo e margem do item
-- 🔑 **No ITEM, como destaque e esgotado**: é decisão deste cardápio. O nível de margem é
-- CALCULADO (ficha × preço × margem-alvo da Precificação); aqui fica só o ajuste manual.
ALTER TABLE catalogo_itens
    ADD COLUMN IF NOT EXISTS objetivo     varchar(14)
        CHECK (objetivo IN ('AUMENTAR_VENDA', 'GIRAR_ESTOQUE', 'LANCAMENTO', 'MANTER')),
    ADD COLUMN IF NOT EXISTS margem_nivel varchar(5)
        CHECK (margem_nivel IN ('ALTA', 'MEDIA', 'BAIXA'));

-- ---------------------------------------------------------------- permissão do painel
INSERT INTO permissoes (chave, modulo, descricao, ordem) VALUES
    ('cardapio.atencao', 'Portal de Clientes',
     'Ver o painel Atenção × Vendas do Cardápio Vivo (atenção, vendas e margem por prato)', 712)
ON CONFLICT (chave) DO UPDATE
    SET modulo = EXCLUDED.modulo, descricao = EXCLUDED.descricao, ordem = EXCLUDED.ordem;

-- ⚠️ Concedido AQUI, chave a chave (ver 091): a margem é dado de gestão — Salão fica de fora.
INSERT INTO papel_permissoes (id_papel, chave)
SELECT p.id, 'cardapio.atencao' FROM papeis p
 WHERE p.sistema AND p.nome IN ('Administrador', 'Gerente')
ON CONFLICT DO NOTHING;

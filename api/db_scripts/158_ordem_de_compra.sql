-- 158 — Ordem de compra: a lista do que precisa ser comprado, e do que já foi.
-- Idempotente. Só cria tabela e permissões: não reescreve dado nenhum.
--
-- 🔑 **Pedido do dono (23/11/2026):** *"o usuario adiciona itens que precisam ser comprar,
-- informa a quantidade e um observação opcional. E conforme estes pedidos vão sendo compras
-- estes podem ir saindo da lista e entram em outra como comprado."*
-- Estudo em `docs/ordem-de-compra-estudo.md`.
--
-- 🔑 **Comprado NÃO é recebido.** Nada aqui toca o razão: o estoque só anda quando a nota é
-- lançada. Marcar "comprado" é um aviso entre pessoas, e por isso desfazer é um clique.
--
-- 🔑 **Uma linha por item, sem cabeçalho de documento**: cada item sai da lista sozinho.

CREATE TABLE IF NOT EXISTS ordem_compra_itens (
    id                bigserial PRIMARY KEY,
    id_unidade        integer NOT NULL REFERENCES unidades(id),
    -- Nulo = fora do cadastro (o guardanapo que ninguém vai parar para cadastrar).
    id_produto        integer REFERENCES produtos(id),
    descricao_livre   varchar(160),
    quantidade        numeric(18,4) NOT NULL CHECK (quantidade > 0),
    -- ⚠️ Só quando se comprou MAIS do que o pedido: é o que "voltar à lista" restaura.
    quantidade_pedida numeric(18,4) CHECK (quantidade_pedida > 0),
    um                varchar(6) NOT NULL REFERENCES unidades_medida(sigla),
    observacao        varchar(300),
    status            varchar(12) NOT NULL DEFAULT 'A_COMPRAR'
                      CHECK (status IN ('A_COMPRAR', 'COMPRADO', 'CANCELADO')),
    -- A compra parcial: os 6 comprados apontam para a linha dos 4 que faltam.
    id_item_origem    bigint REFERENCES ordem_compra_itens(id),
    id_fornecedor     integer REFERENCES fornecedores(id),
    criado_em         timestamptz NOT NULL DEFAULT now(),
    criado_por        integer NOT NULL REFERENCES usuarios(id),
    comprado_em       timestamptz,
    comprado_por      integer REFERENCES usuarios(id),
    cancelado_em      timestamptz,
    cancelado_por     integer REFERENCES usuarios(id),
    CONSTRAINT ck_ordem_item_identificado CHECK (
        id_produto IS NOT NULL OR length(trim(coalesce(descricao_livre, ''))) > 0
    )
);
CREATE INDEX IF NOT EXISTS ix_ordem_a_comprar
    ON ordem_compra_itens (id_unidade, criado_em DESC) WHERE status = 'A_COMPRAR';
CREATE INDEX IF NOT EXISTS ix_ordem_comprados
    ON ordem_compra_itens (id_unidade, comprado_em DESC) WHERE status = 'COMPRADO';
CREATE INDEX IF NOT EXISTS ix_ordem_produto ON ordem_compra_itens (id_produto);
CREATE INDEX IF NOT EXISTS ix_ordem_origem
    ON ordem_compra_itens (id_item_origem) WHERE id_item_origem IS NOT NULL;

INSERT INTO permissoes (chave, modulo, descricao, ordem) VALUES
    ('compras.ordem_solicitar', 'Compras',
     'Ver a ordem de compra, pedir itens e corrigir ou cancelar o próprio pedido', 440),
    ('compras.ordem_comprar', 'Compras',
     'Marcar itens como comprados, voltá-los à lista e corrigir ou cancelar qualquer pedido', 450)
ON CONFLICT (chave) DO UPDATE
    SET modulo = EXCLUDED.modulo, descricao = EXCLUDED.descricao, ordem = EXCLUDED.ordem;

-- ⚠️ Concedido AQUI (ver 091). Toda a equipe pede; o Contador só lê notas e relatórios.
INSERT INTO papel_permissoes (id_papel, chave)
SELECT p.id, 'compras.ordem_solicitar'
  FROM papeis p
 WHERE p.sistema
   AND p.nome IN ('Administrador', 'Gerente', 'Cozinha', 'Conferente / Estoque', 'Salão')
ON CONFLICT DO NOTHING;

INSERT INTO papel_permissoes (id_papel, chave)
SELECT p.id, 'compras.ordem_comprar'
  FROM papeis p
 WHERE p.sistema AND p.nome IN ('Administrador', 'Gerente', 'Conferente / Estoque')
ON CONFLICT DO NOTHING;

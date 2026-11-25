-- 162 — Recebimento de notas: quem recebeu a nota X do fornecedor Y, em que data, com foto.
-- Idempotente. Só cria tabela e permissão: não reescreve dado nenhum.
--
-- 🔑 **Pedido do dono (24/11/2026):** *"um processo simples de recebimento, onde o usuário
-- pode informar que recebeu a nota X do fornecedor Y da data Z e anexar uma foto, como
-- opcional. Pois um usuário recebe a nota e produtos e acaba perdendo, e quem repassa ela para
-- o sistema acaba não recebendo; seria somente para registro."*
--
-- 🔑 **Só registro**: não mexe em estoque, custo nem na nota de entrada. Ver uma nota "já
-- lançada" é CONTA na leitura (número + fornecedor em `notas_entrada`), não coluna: a nota pode
-- chegar do Omie depois, e a situação muda sozinha.
-- 🔑 **A foto mora em `arquivos` (banco)**, porque o disco do App Platform é efêmero — e é
-- servida só por rota autenticada (`/recebimentos/{id}/foto`): `/arquivos/{nome}` é pública,
-- feita para a logo, e foto de nota fiscal não é para ficar aberta.

CREATE TABLE IF NOT EXISTS recebimentos (
    id               serial PRIMARY KEY,
    id_unidade       integer NOT NULL REFERENCES unidades(id),
    numero_nota      varchar(30) NOT NULL,
    id_fornecedor    integer REFERENCES fornecedores(id),
    -- O fornecedor que não está no cadastro: quem recebe não para a entrega para cadastrar.
    fornecedor_texto varchar(120),
    data_nota        date NOT NULL,
    observacao       varchar(300),
    foto             varchar(120),
    recebido_por     integer REFERENCES usuarios(id),
    registrado_em    timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_recebimento_fornecedor CHECK (id_fornecedor IS NOT NULL OR fornecedor_texto IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS ix_recebimentos_unidade_data ON recebimentos (id_unidade, data_nota DESC);

INSERT INTO permissoes (chave, modulo, descricao, ordem) VALUES
    ('compras.receber', 'Compras', 'Registrar que recebeu uma nota (número, fornecedor, data e foto)', 438)
ON CONFLICT (chave) DO UPDATE
    SET modulo = EXCLUDED.modulo, descricao = EXCLUDED.descricao, ordem = EXCLUDED.ordem;

-- A mesma equipe que pede na ordem de compra: quem está na porta quando o fornecedor chega.
INSERT INTO papel_permissoes (id_papel, chave)
SELECT p.id, 'compras.receber'
  FROM papeis p
 WHERE p.sistema AND p.nome IN ('Administrador', 'Gerente', 'Cozinha', 'Conferente / Estoque', 'Salão')
ON CONFLICT DO NOTHING;

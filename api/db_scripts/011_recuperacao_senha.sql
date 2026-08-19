-- Botané 011 — recuperação de senha por e-mail. Idempotente.

-- O token NUNCA é guardado em claro, pela mesma razão do refresh: quem
-- conseguir ler a tabela não consegue entrar na conta de ninguém. O que fica é
-- o sha256; a comparação é feita pelo hash do que chegou.
CREATE TABLE IF NOT EXISTS senha_tokens (
    id          bigserial PRIMARY KEY,
    id_usuario  integer NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    token_hash  char(64) NOT NULL UNIQUE,
    criado_em   timestamptz NOT NULL DEFAULT now(),
    expira_em   timestamptz NOT NULL,
    usado_em    timestamptz,
    -- Quem pediu: o próprio usuário pela tela pública, ou um administrador
    -- gerando o link para entregar na mão.
    origem      varchar(10) NOT NULL DEFAULT 'PUBLICA',   -- PUBLICA | ADMIN
    ip          varchar(45)
);

-- Serve à trava de repetição: quantos pedidos este usuário fez na última hora.
CREATE INDEX IF NOT EXISTS ix_senha_token_usuario
    ON senha_tokens (id_usuario, criado_em DESC);

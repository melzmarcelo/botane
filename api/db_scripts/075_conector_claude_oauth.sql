-- Botané 075 — o conector do Claude pela URL: OAuth e a permissão de usá-lo.
-- Idempotente.
--
-- 🔑 **Pedido do dono (19/09/2026): cadastrar o Botané como conector no
-- claude.ai.** Lá o conector é uma URL (`/api/mcp`), e o claude.ai só entra num
-- conector com login por OAuth 2.1: registra-se sozinho (registro dinâmico),
-- manda a pessoa para a nossa página de login e recebe um código, que troca por
-- chave. Esta migração guarda as três coisas: quem se registrou, os códigos em
-- trânsito, e a chave que nasce no fim — que é uma linha de `tokens_api`, a
-- mesma da chave gerada à mão, para aparecer e ser revogada na mesma tela.

-- ---------------------------------------------------------------------------
-- Quem pode ligar o Claude à própria conta
-- ---------------------------------------------------------------------------
-- ⚠️ **Não é "todo mundo que tem login".** Conectar o Claude é levar o que a
-- pessoa enxerga para fora do sistema, para a conta dela num serviço de IA. É
-- decisão do dono, papel a papel. Nasce só com quem já administra usuários —
-- quem gera chave à mão pela tela —, e o resto se libera em Papéis.
INSERT INTO permissoes (chave, modulo, descricao, ordem) VALUES
    ('integracao.claude', 'Administração',
     'Conectar o Claude (MCP) à própria conta, só para leitura', 75)
ON CONFLICT (chave) DO NOTHING;

INSERT INTO papel_permissoes (id_papel, chave)
SELECT pp.id_papel, 'integracao.claude'
  FROM papel_permissoes pp
 WHERE pp.chave = 'admin.usuarios'
ON CONFLICT DO NOTHING;

-- ---------------------------------------------------------------------------
-- Clientes registrados (RFC 7591)
-- ---------------------------------------------------------------------------
-- ⚠️ O registro é ABERTO, como o protocolo pede: qualquer programa se registra.
-- Registrar-se não dá acesso a nada — só dá o direito de mandar alguém para a
-- página de login, onde a pessoa vê o nome e o endereço de volta ANTES de
-- digitar a senha. `redirect_uris` é conferido letra por letra no pedido.
CREATE TABLE IF NOT EXISTS oauth_clientes (
    id              serial PRIMARY KEY,
    client_id       varchar(64) NOT NULL UNIQUE,
    -- Só para quem pediu `client_secret_post`/`_basic`; o Claude é cliente
    -- público (PKCE, sem segredo) e fica nulo.
    segredo_hash    varchar(64),
    metodo_auth     varchar(30) NOT NULL DEFAULT 'none',
    nome            varchar(120) NOT NULL,
    redirect_uris   text[] NOT NULL,
    criado_em       timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- O código de autorização: uso único, minutos de vida, preso ao PKCE
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS oauth_codigos (
    id              serial PRIMARY KEY,
    codigo_hash     varchar(64) NOT NULL UNIQUE,
    id_cliente      integer NOT NULL REFERENCES oauth_clientes(id) ON DELETE CASCADE,
    id_usuario      integer NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    redirect_uri    text NOT NULL,
    code_challenge  varchar(128) NOT NULL,
    recurso         text,
    expira_em       timestamptz NOT NULL,
    usado_em        timestamptz
);

-- ---------------------------------------------------------------------------
-- A chave nascida do OAuth mora em `tokens_api`, com renovação
-- ---------------------------------------------------------------------------
-- 🔑 **Uma linha por CONEXÃO, rotacionada no lugar.** A chave de acesso vive uma
-- hora; a renovação troca `token_hash` e `refresh_hash` na MESMA linha. Criar
-- uma linha por renovação encheria a tela de 24 chaves revogadas por dia, e
-- revogar "a conexão do Claude" deixaria de ser um clique.
ALTER TABLE tokens_api ADD COLUMN IF NOT EXISTS origem varchar(10) NOT NULL DEFAULT 'manual';
ALTER TABLE tokens_api ADD COLUMN IF NOT EXISTS id_cliente_oauth integer
    REFERENCES oauth_clientes(id) ON DELETE SET NULL;
ALTER TABLE tokens_api ADD COLUMN IF NOT EXISTS refresh_hash varchar(64);
ALTER TABLE tokens_api ADD COLUMN IF NOT EXISTS refresh_expira_em timestamptz;

CREATE UNIQUE INDEX IF NOT EXISTS ux_tokens_api_refresh ON tokens_api (refresh_hash)
    WHERE refresh_hash IS NOT NULL;

COMMENT ON COLUMN tokens_api.origem IS
  'manual (gerada na tela) ou oauth (o proprio usuario conectou o Claude). Migracao 075.';

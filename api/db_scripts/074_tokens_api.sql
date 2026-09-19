-- Botané 074 — chave de acesso para MÁQUINA (o conector MCP do Claude).
-- Idempotente.
--
-- 🔑 **Pedido do dono (19/09/2026): usar o Botané pelo Claude, via MCP.** O
-- conector é um programa, não uma pessoa: não digita senha, não guarda cookie e
-- não sabe renovar sessão. A sessão da casa foi feita para o navegador — access
-- de minutos, refresh que ROTACIONA e morre com o `sessionStorage` —, e é isso
-- que ela deve continuar sendo.
--
-- 🔑 **A chave AGE COMO um usuário, nunca por cima dele.** Ela resolve para um
-- `id_usuario` e daí em diante é o `Contexto` de sempre: papel, loja e setor
-- valem igual. Usuário desativado leva as chaves junto, porque
-- `carregar_contexto` já recusa inativo — nenhuma linha daqui precisa lembrar.
--
-- ⚠️ **Só o HASH mora aqui**, como no refresh: vazamento da tabela não vira
-- acesso de ninguém. A chave em claro aparece UMA vez, na resposta da criação.
-- `prefixo` é o pedaço que a tela mostra para a pessoa reconhecer qual é qual.
--
-- ⚠️ **`somente_leitura` nasce VERDADEIRO e a fase 1 não oferece o contrário.**
-- Quem barra é `contexto_atual`, pelo MÉTODO da requisição: vale para toda rota
-- que existe e para toda que ainda vai existir, sem depender de cada router
-- lembrar. Escrever pelo Claude é a fase 2, e vai pedir decisão própria.

CREATE TABLE IF NOT EXISTS tokens_api (
    id              serial PRIMARY KEY,
    id_usuario      integer NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    nome            varchar(80) NOT NULL,
    prefixo         varchar(16) NOT NULL,
    token_hash      varchar(64) NOT NULL,
    somente_leitura boolean NOT NULL DEFAULT true,
    expira_em       timestamptz NOT NULL,
    criado_em       timestamptz NOT NULL DEFAULT now(),
    criado_por      integer REFERENCES usuarios(id),
    ultimo_uso_em   timestamptz,
    revogado_em     timestamptz,
    revogado_por    integer REFERENCES usuarios(id)
);

-- A pergunta de TODA requisição com chave é "de quem é este hash?".
CREATE UNIQUE INDEX IF NOT EXISTS ux_tokens_api_hash ON tokens_api (token_hash);
CREATE INDEX IF NOT EXISTS ix_tokens_api_usuario ON tokens_api (id_usuario, revogado_em);

COMMENT ON TABLE tokens_api IS
  'Chave de acesso de maquina (conector MCP). Age como o usuario dono; so o '
  'hash e guardado. Migracao 074.';

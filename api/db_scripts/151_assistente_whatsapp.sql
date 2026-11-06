-- 151 — O assistente pelo WhatsApp, etapa 1: o número do assistente (DA CASA) e o vínculo
-- telefone ↔ usuário.
--
-- 🔑 **Pedido do dono (06/11/2026):** *"no meu usuário vou vincular o meu número de telefone. Aí
-- pela manhã mando um áudio ou um texto para este número de WhatsApp que vamos integrar no
-- sistema, pedindo por exemplo quais as minhas pendências para hoje…"* Estudo em
-- `docs/assistente-whatsapp-estudo.md`. Esta etapa só prova o cano: o funcionário é reconhecido
-- pelo número e recebe um "olá"; consultar e gravar vêm depois.
--
-- 🔑 **E, antes do commit:** *"este número poderia ser compartilhado entre lojas. Pois eu posso
-- ter acesso às duas lojas, e quando pergunto o que tenho de pendência, poderia encontrar coisas
-- de duas lojas, e não precisar de dois números."* Por isso o número é UM, da casa toda: mora em
-- `integracoes` (serviço `WHATSAPP_ASSISTENTE`, `id_unidade` nulo, como a Tradução e o e-mail) e
-- se configura em Integrações. Quem decide o que cada pessoa vê é o usuário, não o número.
--
-- ⚠️ **O telefone é a senha.** O vínculo NÃO nasce do que a pessoa digita: o Botané dá um código,
-- a pessoa o manda do próprio WhatsApp para o número do assistente, e o que fica gravado é o
-- `from` que a Meta entregou (`wa_id`). Isso prova a posse e evita o nono dígito — a Meta às
-- vezes entrega celular brasileiro sem ele, e comparar com o digitado falharia.
-- Idempotente.

-- A primeira versão (nunca promovida) punha o número na loja. Limpa a base de quem a rodou.
ALTER TABLE unidade_whatsapps DROP COLUMN IF EXISTS assistente;

CREATE TABLE IF NOT EXISTS usuario_whatsapp (
    id_usuario       integer PRIMARY KEY REFERENCES usuarios(id) ON DELETE CASCADE,
    -- O número como a Meta o manda em `from` (só dígitos, com o 55). Nulo até verificar.
    wa_id            varchar(20),
    verificado_em    timestamptz,
    -- O código pendente, guardado só como hash (sha256); some quando é usado.
    codigo_hash      varchar(64),
    codigo_expira_em timestamptz,
    criado_em        timestamptz NOT NULL DEFAULT now(),
    atualizado_em    timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE usuario_whatsapp DROP COLUMN IF EXISTS id_whatsapp;
-- Um telefone, um usuário.
CREATE UNIQUE INDEX IF NOT EXISTS ux_usuario_whatsapp_wa
    ON usuario_whatsapp (wa_id) WHERE wa_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS ux_usuario_whatsapp_codigo
    ON usuario_whatsapp (codigo_hash) WHERE codigo_hash IS NOT NULL;

COMMENT ON TABLE usuario_whatsapp IS
    'O WhatsApp de cada usuário para o assistente (151). wa_id = o from da Meta, gravado só '
    'depois de a pessoa mandar o código do próprio aparelho.';

-- 🔑 **A fila das respostas do assistente — fora de `whatsapp_mensagens`, de propósito.** Aquela
-- é o histórico de UMA loja, que quem administra a loja lê; a conversa de um funcionário com o
-- assistente não é de loja nenhuma, e vai trazer receita, estoque e pendência dele.
CREATE TABLE IF NOT EXISTS assistente_mensagens (
    id            bigserial PRIMARY KEY,
    -- 🔑 A resposta não sai duas vezes: chave = id da mensagem da Meta que ela responde (a Meta
    -- reenvia o webhook se não recebe 200 a tempo).
    chave         varchar(120) NOT NULL UNIQUE,
    id_usuario    integer REFERENCES usuarios(id) ON DELETE SET NULL,
    telefone      varchar(20) NOT NULL,
    texto         text NOT NULL,
    status        varchar(12) NOT NULL DEFAULT 'FILA'
                  CHECK (status IN ('FILA', 'ENVIADA', 'ENTREGUE', 'LIDA', 'FALHOU', 'SIMULADA',
                                    'CANCELADA')),
    agendada_para timestamptz NOT NULL DEFAULT now(),
    enviada_em    timestamptz,
    id_meta       varchar(120),
    tentativas    integer NOT NULL DEFAULT 0,
    erro          text,
    criada_em     timestamptz NOT NULL DEFAULT now(),
    atualizada_em timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_assistente_fila
    ON assistente_mensagens (agendada_para) WHERE status = 'FILA';
CREATE INDEX IF NOT EXISTS ix_assistente_meta ON assistente_mensagens (id_meta);

-- ⚠️ **Não é "todo mundo que tem login"**, como o conector do Claude (075): falar com o sistema
-- pelo WhatsApp leva o que a pessoa enxerga para o celular dela. Nasce com quem já administra
-- usuários; o resto se libera em Papéis.
INSERT INTO permissoes (chave, modulo, descricao, ordem) VALUES
    ('integracao.whatsapp_assistente', 'Administração',
     'Usar o assistente pelo WhatsApp (vincular o próprio telefone)', 76)
ON CONFLICT (chave) DO NOTHING;

INSERT INTO papel_permissoes (id_papel, chave)
SELECT pp.id_papel, 'integracao.whatsapp_assistente'
  FROM papel_permissoes pp
 WHERE pp.chave = 'admin.usuarios'
ON CONFLICT DO NOTHING;

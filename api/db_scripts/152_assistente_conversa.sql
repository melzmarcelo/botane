-- 152 — O assistente pelo WhatsApp, etapa 2: a conversa (consultas por texto com o Claude).
--
-- 🔑 **Pedido do dono (06/11/2026):** *"pela manhã mando um texto pedindo quais as minhas
-- pendências para hoje. Aí ele retorna: para hoje precisa produzir 10 pães. Aí posso solicitar a
-- receita…"* Estudo em `docs/assistente-whatsapp-estudo.md`. Nesta etapa o assistente só
-- CONSULTA — com as ferramentas de leitura do conector do Claude, como o próprio usuário.
--
-- 🔑 **Uma linha por fala**, do funcionário ou do assistente. É daqui que sai o histórico curto
-- que vai junto de cada pergunta ("e a receita dele?" precisa saber de quem se falava).
-- ⚠️ **A pergunta é guardada no webhook e respondida DEPOIS** (`status` PENDENTE → RESPONDIDA):
-- a Meta quer o 200 em segundos, e o Claude consultando três lojas leva mais que isso.
-- ⚠️ É conversa do funcionário: fica só aqui, sai em 30 dias (`assistente_conversa.limpar`) e
-- NÃO entra no histórico de WhatsApp das lojas.
-- Idempotente.

CREATE TABLE IF NOT EXISTS assistente_conversa (
    id           bigserial PRIMARY KEY,
    id_usuario   integer NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    papel        varchar(12) NOT NULL CHECK (papel IN ('usuario', 'assistente')),
    texto        text NOT NULL,
    -- O id da mensagem na Meta (só na fala do funcionário): a Meta reenvia o webhook se não
    -- recebe 200 a tempo, e a mesma pergunta não entra duas vezes.
    id_meta      varchar(120) UNIQUE,
    -- Só na fala do funcionário: PENDENTE → PROCESSANDO → RESPONDIDA (ou ERRO).
    status       varchar(12) CHECK (status IS NULL OR status IN
                                    ('PENDENTE', 'PROCESSANDO', 'RESPONDIDA', 'ERRO')),
    tentativas   integer NOT NULL DEFAULT 0,
    tentar_apos  timestamptz,
    erro         text,
    -- Só na fala do assistente: o modelo e os tokens gastos (custo, e se o cache pegou).
    uso          jsonb,
    criada_em    timestamptz NOT NULL DEFAULT now(),
    atualizada_em timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_assistente_conversa_usuario
    ON assistente_conversa (id_usuario, criada_em DESC);
CREATE INDEX IF NOT EXISTS ix_assistente_conversa_pendente
    ON assistente_conversa (criada_em) WHERE status IN ('PENDENTE', 'PROCESSANDO');

COMMENT ON TABLE assistente_conversa IS
    'A conversa de cada funcionário com o assistente do WhatsApp (152). Pergunta guardada no '
    'webhook e respondida depois; some em 30 dias.';

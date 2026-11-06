-- 154 — O assistente pelo WhatsApp, etapa 4: LANÇAR produção, com confirmação por botão.
--
-- 🔑 **Pedido do dono (06/11/2026):** *"depois posso confirmar a produção e o sistema já lança
-- e coloca em estoque"*. Estudo em `docs/assistente-whatsapp-estudo.md`.
--
-- 🔑 **O Claude nunca grava.** Quando ele pede uma ferramenta de gravação, nada é chamado: nasce
-- uma AÇÃO pendente com a prévia exata (montada pelo sistema, não pelo Claude) e a pessoa recebe
-- dois botões. Só o toque em "Confirmar" — que volta pelo webhook com o id da ação — lança, com a
-- credencial da própria pessoa. "Sim" por escrito não confirma: botão tem id, conversa não.
-- ⚠️ Vale 10 minutos; uma nova proposta derruba a anterior (uma pendente por pessoa).
-- Idempotente.

CREATE TABLE IF NOT EXISTS assistente_acoes (
    id            bigserial PRIMARY KEY,
    id_usuario    integer NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    ferramenta    varchar(60) NOT NULL,
    argumentos    jsonb NOT NULL,
    -- A prévia que a pessoa viu e confirmou — o texto do botão, montado pelo sistema.
    resumo        text NOT NULL,
    -- PENDENTE → CONFIRMADA (tocou o botão; o lançamento roda logo depois) → EXECUTADA ou ERRO.
    status        varchar(12) NOT NULL DEFAULT 'PENDENTE'
                  CHECK (status IN ('PENDENTE', 'CONFIRMADA', 'EXECUTADA', 'CANCELADA',
                                    'EXPIRADA', 'ERRO')),
    expira_em     timestamptz NOT NULL,
    confirmada_em timestamptz,
    executada_em  timestamptz,
    resultado     jsonb,
    erro          text,
    criada_em     timestamptz NOT NULL DEFAULT now(),
    atualizada_em timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_assistente_acoes_usuario
    ON assistente_acoes (id_usuario) WHERE status = 'PENDENTE';
CREATE INDEX IF NOT EXISTS ix_assistente_acoes_confirmadas
    ON assistente_acoes (confirmada_em) WHERE status = 'CONFIRMADA';

COMMENT ON TABLE assistente_acoes IS
    'Lançamentos propostos pelo assistente do WhatsApp (154): só rodam quando a pessoa toca '
    'Confirmar. A prévia (resumo) é montada pelo sistema.';

-- 🔑 A resposta com botões (interactive da Meta): os botões vão junto da mensagem na fila.
ALTER TABLE assistente_mensagens ADD COLUMN IF NOT EXISTS botoes jsonb;

-- ⚠️ **Consultar não é lançar.** Quem tem o assistente (151) pergunta; lançar pelo WhatsApp é
-- outra chave — e, como sempre, a rota ainda confere a permissão de produção da pessoa.
-- Nasce com quem já administra usuários; o resto se libera em Papéis.
INSERT INTO permissoes (chave, modulo, descricao, ordem) VALUES
    ('integracao.whatsapp_lancar', 'Administração',
     'Lançar produção pelo assistente do WhatsApp (com confirmação por botão)', 77)
ON CONFLICT (chave) DO NOTHING;

INSERT INTO papel_permissoes (id_papel, chave)
SELECT pp.id_papel, 'integracao.whatsapp_lancar'
  FROM papel_permissoes pp
 WHERE pp.chave = 'admin.usuarios'
ON CONFLICT DO NOTHING;

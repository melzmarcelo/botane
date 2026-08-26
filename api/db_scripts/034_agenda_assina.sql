-- Botané 034 — a agenda registra QUEM a ligou. Idempotente.
--
-- A agenda do Omie só busca nota e grava em tabela de integração; a do PDV Legal
-- **grava venda**, e venda baixa estoque, mexe no razão e entra na auditoria.
-- Toda escrita dessas carrega `id_usuario`, e o agendador não tem sessão.
--
-- ⚠️ **Inventar um "usuário do sistema" seria pior.** Ele apareceria na
-- auditoria como o autor de mil vendas, sem ninguém a quem perguntar, e teria de
-- existir como linha em `usuarios` com senha, permissões e a possibilidade de
-- alguém entrar com ele. Quem liga a agenda é uma pessoa que decidiu aquilo —
-- é ela que assina o que a agenda faz, exatamente como se tivesse clicado.
--
-- ⚠️ **NULO é o estado normal** de quem nunca configurou agenda, e de toda
-- integração cuja agenda é MANUAL. O agendador do PDV recusa rodar sem este
-- campo e diz por quê, em vez de gravar venda sem dono.
--
-- ⚠️ `ON DELETE SET NULL`: apagar o usuário não pode derrubar a integração da
-- casa. A agenda para e a tela pede para ligar de novo — que é a informação
-- certa, porque quem autorizou não trabalha mais aqui.

ALTER TABLE integracoes
    ADD COLUMN IF NOT EXISTS agenda_id_usuario integer;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_integracao_agenda_usuario') THEN
        ALTER TABLE integracoes ADD CONSTRAINT fk_integracao_agenda_usuario
            FOREIGN KEY (agenda_id_usuario) REFERENCES usuarios (id) ON DELETE SET NULL;
    END IF;
END $$;

-- 112 — O erro que acontece no ar fica guardado no banco. Idempotente.
--
-- 🔑 **Nasceu do incidente de 09 a 11/10/2026.** A busca das vendas do PDV
-- falhou três dias, e o diagnóstico dependeu de o dono colar a mensagem da tela
-- de Integrações: o log do App Platform não é lido por ninguém, e quem investiga
-- não tem acesso a ele. Aqui fica todo erro 500 da API e toda falha inesperada
-- dos agendadores, com o traceback, para a tela de Auditoria mostrar.
--
-- ⚠️ **Não é auditoria.** A auditoria registra o que alguém DECIDIU fazer; isto
-- registra o que o sistema NÃO conseguiu fazer. Misturar faria o histórico de
-- alterações encher de ruído técnico, e o erro sumir no meio de 40 mil linhas.
-- ⚠️ **Erro esperado não entra**: 4xx é resposta (permissão, validação, não
-- encontrado), não defeito. Só o que estourou sem ninguém tratar.

CREATE TABLE IF NOT EXISTS erros_sistema (
    id          bigserial PRIMARY KEY,
    quando      timestamptz NOT NULL DEFAULT now(),
    -- api | agenda_pdv | agenda_omie | whatsapp — de onde veio, em texto livre:
    -- origem nova não pede migração.
    origem      text NOT NULL,
    metodo      text,
    rota        text,
    id_usuario  integer REFERENCES usuarios(id) ON DELETE SET NULL,
    id_unidade  integer REFERENCES unidades(id) ON DELETE SET NULL,
    tipo        text NOT NULL,
    mensagem    text NOT NULL,
    -- O traceback, cortado: o que importa está no fim, e um erro em laço não
    -- pode encher o banco.
    detalhe     text,
    versao      text
);

-- ⚠️ `text` em tudo, e é de propósito: o registro do erro não pode ele mesmo
-- falhar por tamanho — foi um `varchar(20)` que começou a história (ver 111).

CREATE INDEX IF NOT EXISTS ix_erros_sistema_quando ON erros_sistema (quando DESC);

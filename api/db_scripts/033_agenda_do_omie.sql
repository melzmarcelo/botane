-- Botané 033 — a busca das notas no Omie pode rodar sozinha. Idempotente.
--
-- Até aqui alguém tinha de abrir Compras e clicar em "Buscar no Omie". Nota que
-- chega na sexta e ninguém busca até segunda é nota que não entrou no estoque —
-- e o CMV do fim de semana sai com compra a menos.
--
-- Três ritmos, escolhidos por loja:
--
--   MANUAL   nada roda sozinho (o padrão, e o comportamento de sempre)
--   HORARIA  a cada hora
--   DIARIA   uma vez por dia, na hora escolhida
--
-- ⚠️ **O padrão é MANUAL, e tem de continuar sendo.** Cada busca consome cota da
-- conta do cliente, e o Omie BLOQUEIA quem consome demais — o bloqueio pega a
-- integração inteira, não só a chamada. Ligar o agendamento é uma decisão de
-- quem paga a conta, não um padrão que aparece sozinho depois de uma migração.

ALTER TABLE integracoes
    ADD COLUMN IF NOT EXISTS agenda_frequencia varchar(12) NOT NULL DEFAULT 'MANUAL';

-- Hora do dia (0–23) para a frequência DIÁRIA. Três da manhã por padrão: é
-- quando a casa está fechada e o Omie está vazio.
ALTER TABLE integracoes
    ADD COLUMN IF NOT EXISTS agenda_hora smallint NOT NULL DEFAULT 3;

-- ⚠️ Quantos dias para trás cada busca varre. **Nulo é o certo para quase todo
-- mundo**: a janela automática vai desde a última sincronização com 7 dias de
-- folga, e a folga existe porque nota emitida antes e lançada no Omie depois
-- cairia fora se a janela começasse onde a anterior parou. Preencher só faz
-- sentido para quem quer varrer um mês inteiro a cada rodada — e aí custa mais
-- cota.
ALTER TABLE integracoes
    ADD COLUMN IF NOT EXISTS agenda_janela_dias smallint;

-- ⚠️ Quando a agenda RODOU, e não quando trouxe nota. `ultima_sincronizacao` só
-- avança quando algo chega; usá-la como relógio faria o agendador tentar de
-- novo a cada minuto numa casa sem nota nova — que é a casa normal de domingo.
ALTER TABLE integracoes
    ADD COLUMN IF NOT EXISTS agenda_rodou_em timestamptz;

ALTER TABLE integracoes
    ADD COLUMN IF NOT EXISTS agenda_ultimo_erro text;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_integracao_agenda') THEN
        ALTER TABLE integracoes ADD CONSTRAINT ck_integracao_agenda
            CHECK (agenda_frequencia IN ('MANUAL', 'HORARIA', 'DIARIA')
                   AND agenda_hora BETWEEN 0 AND 23
                   AND (agenda_janela_dias IS NULL
                        OR agenda_janela_dias BETWEEN 1 AND 365));
    END IF;
END $$;

-- Responde "que integração está devendo rodar?" sem varrer a tabela inteira.
-- São poucas linhas hoje, mas é uma consulta por minuto, para sempre.
CREATE INDEX IF NOT EXISTS ix_integracao_agendada
    ON integracoes (servico, agenda_frequencia) WHERE agenda_frequencia <> 'MANUAL';

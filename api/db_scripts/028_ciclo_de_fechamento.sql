-- Botané 028 — o fechamento do CMV deixa de ser sempre mensal. Idempotente.
--
-- A casa que apresentou o sistema fecha o CMV toda SEMANA. O sistema só sabia
-- fechar mês, e mês é o ritmo do contador, não o de quem conta a despensa: uma
-- variância que só aparece no dia 30 chega tarde demais para virar decisão.
--
-- Três ritmos, um parâmetro por loja:
--
--   DIARIO   o período é o dia
--   SEMANAL  o período é a semana que termina no dia escolhido
--   MENSAL   o período é o mês (é o de hoje, e continua sendo o padrão)
--
-- ⚠️ `competencia` continua sendo o PRIMEIRO DIA do período — o que muda é o
-- tamanho dele. Para MENSAL com o dia 1 (o padrão), `competencia` continua
-- sendo o primeiro dia do mês e nada do que já foi fechado muda de sentido.

ALTER TABLE parametros
    ADD COLUMN IF NOT EXISTS ciclo_fechamento varchar(10) NOT NULL DEFAULT 'MENSAL';

-- ⚠️ Dia da semana em que a semana FECHA, no padrão ISO: 1 = segunda,
-- 7 = domingo. Não é o `weekday()` do Python (0 = segunda) nem o `dow` do
-- Postgres (0 = domingo) — é o `isodow`, que é o único dos três em que
-- "1 = segunda" e "7 = domingo" ao mesmo tempo. Padrão domingo, que é como a
-- semana da casa termina.
ALTER TABLE parametros
    ADD COLUMN IF NOT EXISTS fechamento_dia_semana smallint NOT NULL DEFAULT 7;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_parametros_ciclo') THEN
        ALTER TABLE parametros ADD CONSTRAINT ck_parametros_ciclo
            CHECK (ciclo_fechamento IN ('DIARIO', 'SEMANAL', 'MENSAL'));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_parametros_dia_semana') THEN
        ALTER TABLE parametros ADD CONSTRAINT ck_parametros_dia_semana
            CHECK (fechamento_dia_semana BETWEEN 1 AND 7);
    END IF;
END $$;

-- O fechamento guarda o ritmo com que foi feito. Sem isto, uma casa que troca
-- de mensal para semanal fica com uma lista em que não dá para saber se a linha
-- "01/08" é o mês de agosto ou a semana que começou nele.
ALTER TABLE cmv_fechamentos
    ADD COLUMN IF NOT EXISTS ciclo varchar(10) NOT NULL DEFAULT 'MENSAL';

-- ⚠️ A unicidade passa a incluir o ciclo. Com `(id_unidade, competencia)` só, a
-- semana que começa no dia 1 colidiria com o mês que começa no dia 1 — e o
-- `ON CONFLICT` do fechamento sobrescreveria um com o outro em silêncio.
DO $$
DECLARE
    antigo text;
BEGIN
    SELECT conname INTO antigo
      FROM pg_constraint
     WHERE conrelid = 'cmv_fechamentos'::regclass
       AND contype = 'u'
       AND pg_get_constraintdef(oid) = 'UNIQUE (id_unidade, competencia)';
    IF antigo IS NOT NULL THEN
        EXECUTE format('ALTER TABLE cmv_fechamentos DROP CONSTRAINT %I', antigo);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ux_fechamento_ciclo') THEN
        ALTER TABLE cmv_fechamentos ADD CONSTRAINT ux_fechamento_ciclo
            UNIQUE (id_unidade, ciclo, competencia);
    END IF;
END $$;

-- Quem responde "esta data está dentro de um período fechado?" — a pergunta que
-- o razão faz a cada lançamento. Com fechamento diário são 30 linhas por mês em
-- vez de uma, e a varredura sequencial deixa de servir.
CREATE INDEX IF NOT EXISTS ix_fechamento_intervalo
    ON cmv_fechamentos (id_unidade, inicio, fim) WHERE status = 'FECHADO';

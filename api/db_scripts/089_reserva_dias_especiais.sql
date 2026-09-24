-- O dia que abre FORA do padrão da semana, com o horário dele.
--
-- 🔑 **Pedido do dono (24/09/2026):** *"dia 12 de outubro é feriado e segunda-feira,
-- que não atende, mas nesta segunda vamos abrir … colocamos horário de sábado."*
-- O padrão da semana (`reserva_horarios`) vale toda semana; isto vale UMA data.
--
-- ⚠️ **O outro lado da exceção — "neste dia não abrimos, motivo X" — já existia:**
-- é `reserva_bloqueios` (070). Esta tabela só guarda o dia que ABRE; o fechado
-- continua sendo bloqueio, e o bloqueio vence quando os dois existem.
-- ⚠️ Mesmas regras da janela da semana: abrir antes de fechar, a última reserva
-- dentro da janela.
-- Idempotente.

CREATE TABLE IF NOT EXISTS reserva_dias_especiais (
    id_unidade     integer NOT NULL REFERENCES unidades(id) ON DELETE CASCADE,
    data           date    NOT NULL,
    abre           time    NOT NULL,
    fecha          time    NOT NULL,
    ultima_reserva time    NOT NULL,
    motivo         varchar(120),
    criado_em      timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (id_unidade, data),
    CONSTRAINT ck_especial_janela
        CHECK (abre < fecha AND ultima_reserva <= fecha AND ultima_reserva >= abre)
);

-- Botané 069 — o salão da casa: salões, mesas e quantos lugares cada uma tem.
-- Idempotente.
--
-- 🔑 **Pedido do dono (14/09/2026):** *"para controle interno, ter o cadastro de
-- salões, cadastro de mesas, lugares por mesas."* É o segundo passo do módulo,
-- e a peça que a regra de disponibilidade vai consumir.
--
-- ⚠️ **O salão entra ENTRE a loja e a mesa**, e não é hierarquia decorativa:
-- Salão principal, Varanda, Mezanino. Desligar o salão tira as mesas dele da
-- disponibilidade sem apagar cadastro nenhum — é a Varanda no inverno, o
-- Mezanino que só abre no fim de semana. Sem ele, a casa teria de desligar mesa
-- por mesa e lembrar de religar todas.

CREATE TABLE IF NOT EXISTS saloes (
    id         serial PRIMARY KEY,
    id_unidade integer     NOT NULL REFERENCES unidades(id) ON DELETE CASCADE,
    nome       varchar(60) NOT NULL,
    ativo      boolean     NOT NULL DEFAULT true,
    ordem      smallint    NOT NULL DEFAULT 0,
    criado_em  timestamptz NOT NULL DEFAULT now(),
    -- 🔑 **Chave composta para a `mesas` se pendurar.** Sem ela, nada impediria
    -- uma mesa da loja A de apontar para um salão da loja B — e o erro só
    -- apareceria no dia em que a filial mostrasse uma mesa que não é dela.
    CONSTRAINT ux_salao_por_unidade UNIQUE (id, id_unidade)
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_salao_nome ON saloes (id_unidade, lower(nome));

CREATE TABLE IF NOT EXISTS mesas (
    id         serial PRIMARY KEY,
    id_unidade integer     NOT NULL REFERENCES unidades(id) ON DELETE CASCADE,
    id_salao   integer     NOT NULL,
    nome       varchar(20) NOT NULL,
    -- 🔑 **`lugares` e `capacidade_max` são DOIS números, e é deliberado.**
    -- `lugares` é o confortável; `capacidade_max` é com a cadeira extra. A
    -- alocação usa o máximo, o relatório de ocupação usa os lugares. Um campo só
    -- obrigaria a escolher entre mentir para o cliente (dizendo que cabe sempre)
    -- e recusar mesa que caberia.
    lugares        smallint NOT NULL DEFAULT 2,
    capacidade_max smallint NOT NULL DEFAULT 2,
    -- 🔑 **A mesa vizinha que encosta nesta.** É assim que um grupo de 8 senta
    -- em duas mesas de 4, sem ninguém ter de cadastrar uma "mesa 7+8" que não
    -- existe no salão. ⚠️ **Vale nos DOIS sentidos** — gravar de um lado só
    -- deixaria a alocação achando um par que a outra mesa não conhece. Quem
    -- mantém a simetria é o serviço; aqui o `ON DELETE SET NULL` garante que
    -- apagar uma mesa não deixe a outra apontando para o vazio.
    junta_com  integer REFERENCES mesas(id) ON DELETE SET NULL,
    ativo      boolean NOT NULL DEFAULT true,
    -- ⚠️ Previstos para o mapa do salão, que NÃO entra agora: a recepção precisa
    -- saber *se cabe às 20h*, e isso a regra de disponibilidade responde sem
    -- desenho nenhum. As colunas ficam para não precisar de migração no dia.
    pos_x      smallint,
    pos_y      smallint,
    criado_em  timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT fk_mesa_salao FOREIGN KEY (id_salao, id_unidade)
        REFERENCES saloes (id, id_unidade) ON DELETE CASCADE,
    CONSTRAINT ck_mesa_lugares CHECK (lugares BETWEEN 1 AND 40),
    -- O máximo nunca é menor que o confortável: seria dizer que a cadeira extra
    -- tira lugar.
    CONSTRAINT ck_mesa_maximo  CHECK (capacidade_max >= lugares
                                      AND capacidade_max <= 60),
    CONSTRAINT ck_mesa_nao_junta_consigo CHECK (junta_com IS NULL OR junta_com <> id)
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_mesa_nome ON mesas (id_unidade, lower(nome));
CREATE INDEX IF NOT EXISTS ix_mesa_salao ON mesas (id_salao);

COMMENT ON COLUMN mesas.lugares IS
    'Quantos sentam com conforto. É o número dos relatórios de ocupação.';
COMMENT ON COLUMN mesas.capacidade_max IS
    'Quantos sentam com a cadeira extra. É o número que a ALOCAÇÃO usa.';
COMMENT ON COLUMN mesas.junta_com IS
    'A mesa vizinha que encosta nesta. Vale nos dois sentidos — quem mantém a '
    'simetria é services/reservas.py.';

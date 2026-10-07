-- 109 — Salão: a junta vira CONJUNTO, e o salão diz quando abre. Idempotente.
--
-- 🔑 **Terceira entrega do estudo `docs/salao-estudo.md`** (07/10/2026). As duas
-- mudanças que mexem na regra que responde "tem mesa?".
--
-- 1. **Conjunto de mesas.** A junta era só em PAR (`mesas.junta_com`): o maior
--    grupo possível era o de duas mesas, três de 4 em fila não viravam uma de
--    12, e a capacidade era sempre a soma — juntar duas de 4 "dava 8" mesmo
--    quando na prática dá 6. O conjunto tem de 2 a 4 mesas e capacidade PRÓPRIA.
--    🔑 Decisão do dono (07/10/2026): vale o número que a casa informou, mesmo
--    abaixo da soma dos máximos — a casa sabe quantos cabem.
-- 2. **Os dias do salão e o site.** O salão só sabia "ligado/desligado": o
--    mezanino de sexta a domingo dependia de alguém lembrar de ligar na sexta.
--    🔑 Decisão do dono: por dia da semana basta (sem horário, por ora).

-- ---------------------------------------------------------------- o salão

ALTER TABLE saloes
    ADD COLUMN IF NOT EXISTS dias_semana smallint[] NOT NULL DEFAULT '{1,2,3,4,5,6,7}',
    ADD COLUMN IF NOT EXISTS aceita_site boolean NOT NULL DEFAULT true;

-- ⚠️ ISO, como `reserva_horarios.dia_semana`: 1 = segunda … 7 = domingo.
-- ⚠️ **Nunca vazio**: salão que não abre dia nenhum é salão DESLIGADO, e para
-- isso já existe o `ativo` — duas formas de dizer a mesma coisa divergiriam.
ALTER TABLE saloes DROP CONSTRAINT IF EXISTS ck_salao_dias;
ALTER TABLE saloes ADD CONSTRAINT ck_salao_dias CHECK (
    cardinality(dias_semana) >= 1
    AND dias_semana <@ ARRAY[1, 2, 3, 4, 5, 6, 7]::smallint[]
);

COMMENT ON COLUMN saloes.dias_semana IS
    'Os dias da semana (ISO, 1 = segunda) em que este salão atende. A disponibilidade '
    'só enxerga as mesas dele nesses dias.';
COMMENT ON COLUMN saloes.aceita_site IS
    'Falso = a recepção usa, mas o site do cliente não oferece as mesas deste salão.';
-- ⚠️ O estudo previa também um texto do salão para o cliente. Ficou FORA: o site
-- não deixa escolher salão, e campo que ninguém lê é cadastro que envelhece.

-- ------------------------------------------------------------ os conjuntos

CREATE TABLE IF NOT EXISTS mesa_conjuntos (
    id         serial PRIMARY KEY,
    id_unidade integer     NOT NULL REFERENCES unidades(id) ON DELETE CASCADE,
    -- 🔑 Capacidade PRÓPRIA, não a soma: é o número que a alocação usa.
    capacidade smallint    NOT NULL CHECK (capacidade BETWEEN 1 AND 99),
    criado_em  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_mesa_conjunto_unidade ON mesa_conjuntos (id_unidade);

-- ⚠️ Uma mesa pode estar em MAIS de um conjunto (05+06 e 05+06+07): por isso
-- tabela de itens, e não uma coluna na mesa — que era exatamente o limite do par.
-- ⚠️ `ON DELETE CASCADE` dos dois lados; quem apaga o conjunto que perdeu uma mesa
-- é a rota de excluir mesa (um conjunto sem uma das mesas não é o mesmo conjunto).
CREATE TABLE IF NOT EXISTS mesa_conjunto_itens (
    id_conjunto integer NOT NULL REFERENCES mesa_conjuntos(id) ON DELETE CASCADE,
    id_mesa     integer NOT NULL REFERENCES mesas(id) ON DELETE CASCADE,
    PRIMARY KEY (id_conjunto, id_mesa)
);
CREATE INDEX IF NOT EXISTS ix_mesa_conjunto_item_mesa ON mesa_conjunto_itens (id_mesa);

-- 🔑 **Cada par de hoje vira um conjunto de duas**, com a capacidade que ele já
-- tinha (a soma dos máximos) — nada muda na disponibilidade no dia da migração.
-- ⚠️ **Idempotente pelo próprio dado**: o par é desfeito na mesma migração, então
-- a segunda rodada não encontra par nenhum para converter. `m.id < m.junta_com`
-- pega cada par uma vez (a junta era gravada dos dois lados).
DO $$
DECLARE
    par record;
    novo integer;
BEGIN
    FOR par IN
        SELECT m.id AS a, v.id AS b, m.id_unidade,
               m.capacidade_max + v.capacidade_max AS capacidade
          FROM mesas m JOIN mesas v ON v.id = m.junta_com
         WHERE m.id < v.id AND v.id_unidade = m.id_unidade
    LOOP
        INSERT INTO mesa_conjuntos (id_unidade, capacidade)
        VALUES (par.id_unidade, LEAST(par.capacidade, 99)) RETURNING id INTO novo;
        INSERT INTO mesa_conjunto_itens (id_conjunto, id_mesa) VALUES (novo, par.a), (novo, par.b);
    END LOOP;
    UPDATE mesas SET junta_com = NULL WHERE junta_com IS NOT NULL;
END $$;

-- ⚠️ A coluna FICA, vazia: tirá-la é outra migração, depois de esta ter rodado
-- em todo lugar. Nenhum código a lê mais.
COMMENT ON COLUMN mesas.junta_com IS
    'DESCONTINUADA na 109: a junta virou conjunto (mesa_conjuntos). Sempre nula.';

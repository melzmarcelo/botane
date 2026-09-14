-- Botané 070 — a reserva em si, as mesas que ela ocupa e os bloqueios do dia.
-- Idempotente.
--
-- 🔑 **É a peça que tudo o mais consome, e a única do módulo que não se refaz
-- depois.** O estudo (`docs/reservas-esboco.md`) já dizia isso, e o protótipo em
-- `apresentacao/reservas-prototipo.html` implementa a regra inteira — ele serve
-- de especificação executável para o que está aqui.
--
-- ⚠️ **A reserva NÃO se apaga: muda de status.** É a mesma disciplina do razão
-- de estoque. "Cancelada" é um fato, e apagar a linha levaria junto a resposta
-- para "por que a mesa ficou vazia naquele sábado" — que é exatamente o número
-- que a casa vai querer olhar no fim do mês.

CREATE TABLE IF NOT EXISTS reservas (
    id          bigserial PRIMARY KEY,
    id_unidade  integer NOT NULL REFERENCES unidades(id) ON DELETE CASCADE,
    data        date NOT NULL,
    hora        time NOT NULL,
    pessoas     smallint NOT NULL,
    status      varchar(16) NOT NULL DEFAULT 'CONFIRMADA',
    -- De onde veio: o balcão (telefone, presencial) ou o site do cliente. Muda
    -- o que se pode exigir: o teto de grupo e a antecedência valem para o SITE,
    -- não para quem liga e fala com a casa.
    origem      varchar(10) NOT NULL DEFAULT 'BALCAO',

    -- 🔑 **Nome e telefone são DA RESERVA**, e `id_pessoa` é opcional.
    -- Quem liga para reservar não tem cadastro, e exigir um transformaria uma
    -- ligação de trinta segundos num cadastro completo — a recepção deixaria de
    -- usar o sistema. O vínculo com a agenda de pessoas (`fornecedores`, que é a
    -- tabela de gente desta casa) entra quando a casa quiser histórico.
    -- ⚠️ `ON DELETE SET NULL`: a pessoa sair da agenda não pode apagar a
    -- reserva de sábado nem mudar quem estava esperado.
    id_pessoa   integer REFERENCES fornecedores(id) ON DELETE SET NULL,
    nome        varchar(120) NOT NULL,
    telefone    varchar(30),

    objetivo            varchar(40),
    observacao_cliente  text,
    observacao_interna  text,
    criado_por  integer REFERENCES usuarios(id),
    criado_em   timestamptz NOT NULL DEFAULT now(),
    -- Quando o status mudou pela última vez: é o que a agenda do dia ordena
    -- quando alguém quer ver "o que mexeu agora".
    status_em   timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT ck_reserva_status CHECK (status IN
        ('PENDENTE', 'CONFIRMADA', 'CHEGOU', 'ENCERRADA', 'CANCELADA', 'NAO_COMPARECEU')),
    CONSTRAINT ck_reserva_origem CHECK (origem IN ('BALCAO', 'SITE')),
    CONSTRAINT ck_reserva_pessoas CHECK (pessoas BETWEEN 1 AND 99)
);
CREATE INDEX IF NOT EXISTS ix_reserva_dia ON reservas (id_unidade, data, hora);
CREATE INDEX IF NOT EXISTS ix_reserva_pessoa ON reservas (id_pessoa)
    WHERE id_pessoa IS NOT NULL;

-- Que mesas esta reserva ocupa.
--
-- ⚠️ **Tabela separada porque JUNTAR MESAS é requisito desde o começo**: um
-- `id_mesa` na reserva obrigaria a inventar uma "mesa 3+4" como cadastro, que
-- não existe no salão.
--
-- 🔑 **`ON DELETE RESTRICT` na mesa, e é ele que fecha a promessa feita na
-- migração 069**: lá a rota de excluir mesa diz que "quem vai barrar isto é o
-- BANCO, quando `reserva_mesas` nascer". É esta linha. Mesa que já hospedou
-- reserva não se apaga, e ninguém precisou acrescentar regra nenhuma no código.
CREATE TABLE IF NOT EXISTS reserva_mesas (
    id_reserva bigint  NOT NULL REFERENCES reservas(id) ON DELETE CASCADE,
    id_mesa    integer NOT NULL REFERENCES mesas(id) ON DELETE RESTRICT,
    PRIMARY KEY (id_reserva, id_mesa)
);
CREATE INDEX IF NOT EXISTS ix_reserva_mesas_mesa ON reserva_mesas (id_mesa);

-- Dia ou faixa em que a casa não recebe: feriado, evento fechado, manutenção.
--
-- ⚠️ **É diferente de `reserva_horarios.aberto`**, e as duas coisas precisam
-- existir: o horário diz o que vale toda semana ("domingo não abrimos"), o
-- bloqueio diz o que vale uma vez ("dia 25 é Natal"). Resolver feriado
-- desmarcando o dia da semana faria a casa fechar todas as quartas do ano.
CREATE TABLE IF NOT EXISTS reserva_bloqueios (
    id         serial PRIMARY KEY,
    id_unidade integer NOT NULL REFERENCES unidades(id) ON DELETE CASCADE,
    de         date NOT NULL,
    ate        date NOT NULL,
    motivo     varchar(120) NOT NULL,
    criado_em  timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_bloqueio_periodo CHECK (de <= ate)
);
CREATE INDEX IF NOT EXISTS ix_bloqueio_periodo ON reserva_bloqueios (id_unidade, de, ate);

-- Botané 068 — o módulo de Reservas nasce DESLIGADO, por loja. Idempotente.
--
-- 🔑 **Pedido do dono (14/09/2026):** *"isto tudo vai ser habilitado via
-- parâmetro na loja, podemos iniciar criando este parâmetro e colocando no
-- menu, caso habilitado a opção de Reservas. E a primeira tela que é as
-- configurações, e também, caso tenha habilitado, disponibilizar nas permissões
-- dos usuários os itens de Reserva que vamos criando."*
--
-- O estudo que originou o módulo está em `docs/reservas-esboco.md`, e o
-- protótipo navegável em `apresentacao/reservas-prototipo.html`.
--
-- ⚠️ **O interruptor mora em `parametros`, e não em `reserva_config`.** É de lá
-- que a tela de Lojas já lê e escreve (`_CAMPOS_PARAM` sai do próprio modelo
-- Pydantic), e é de lá que o `/auth/me` responde para o menu sem uma consulta
-- a mais. `reserva_config` guarda COMO o módulo se comporta; `parametros` diz
-- SE ele existe nesta loja.
--
-- ⚠️ **E ele precisa fazer alguma coisa desde o primeiro dia.** O commit
-- anterior (b3c21b5) tirou da tela de Lojas dois interruptores que ninguém lia
-- — configuração que não muda nada ensina que a tela mente. Este muda três
-- coisas ao mesmo tempo: o menu, o acesso à tela e a oferta das permissões.

ALTER TABLE parametros
    ADD COLUMN IF NOT EXISTS reservas_ligado boolean NOT NULL DEFAULT false;

COMMENT ON COLUMN parametros.reservas_ligado IS
    'Liga o módulo de Reservas NESTA loja: menu, telas e a oferta das '
    'permissões reservas.* no catálogo. Nasce desligado.';


-- ---------------------------------------------------------------- permissões
--
-- A faixa 650+ é depois de Integrações (610-620), o fim da lista de hoje.
INSERT INTO permissoes (chave, modulo, descricao, ordem) VALUES
    ('reservas.ver',        'Reservas', 'Ver a agenda e as reservas do dia', 650),
    ('reservas.editar',     'Reservas', 'Criar, alterar, confirmar e cancelar reservas', 660),
    ('reservas.configurar', 'Reservas', 'Configurar horários, permanência, salões e mesas', 670)
ON CONFLICT (chave) DO UPDATE
    SET modulo = EXCLUDED.modulo, descricao = EXCLUDED.descricao, ordem = EXCLUDED.ordem;

-- ⚠️ **As chaves precisam ser concedidas AQUI, e não é redundância.** A
-- migração 002 re-semeia os papéis de sistema a cada start ("Administrador:
-- tudo", via `CROSS JOIN permissoes`) — só que ela roda ANTES desta. Na
-- primeira subida depois do deploy, o catálogo dela ainda não tem `reservas.*`,
-- e o administrador ficaria sem as chaves até o restart SEGUINTE. Um módulo que
-- só funciona na segunda vez que o servidor sobe é exatamente o tipo de coisa
-- que ninguém relaciona à causa.
--
-- 🔑 **Quem recebe o quê**: Administrador e Gerente por regra (é o que a 002 já
-- faria — Reservas não é módulo de Administração), e **Salão** ganha ver e
-- editar, porque garçom e recepção são quem atende o telefone. Configurar o
-- horário da casa não é deles.
--
-- ⚠️ **Conceder não liga nada.** O módulo continua desligado em toda loja até
-- alguém marcar o parâmetro; até lá estas chaves nem aparecem no catálogo.
INSERT INTO papel_permissoes (id_papel, chave)
SELECT p.id, x.chave
  FROM papeis p CROSS JOIN permissoes x
 WHERE p.sistema AND x.modulo = 'Reservas'
   AND (p.nome IN ('Administrador', 'Gerente')
        OR (p.nome = 'Salão' AND x.chave IN ('reservas.ver', 'reservas.editar')))
ON CONFLICT DO NOTHING;


-- ---------------------------------------------------------------- configuração

-- Como o módulo se comporta NESTA loja. Uma linha por unidade, criada na
-- primeira visita à tela — o mesmo desenho preguiçoso de `parametros`, que
-- evita ter de semear toda loja nova em dois lugares.
CREATE TABLE IF NOT EXISTS reserva_config (
    id_unidade             integer PRIMARY KEY REFERENCES unidades(id) ON DELETE CASCADE,
    -- Aceitar reserva pelo site do cliente. Separado de `reservas_ligado`: a
    -- casa pode operar a agenda no balcão muito antes de abrir a porta de fora.
    aceita_online          boolean NOT NULL DEFAULT false,
    -- 🔑 **A pergunta que muda o fluxo inteiro do cliente**, e a única das cinco
    -- do esboço que o site de hoje não deixa ver de fora: a reserva nasce
    -- CONFIRMADA ou PENDENTE esperando a casa? Fica configurável porque as duas
    -- respostas são legítimas e mudam só o passo final.
    confirmacao            varchar(10) NOT NULL DEFAULT 'AUTOMATICA',
    -- Maior grupo que o site aceita sozinho. Acima disso, fala-se com a casa.
    teto_online            smallint NOT NULL DEFAULT 8,
    -- Atraso aceito antes de a mesa voltar a ficar livre.
    tolerancia_min         smallint NOT NULL DEFAULT 15,
    -- Tempo de arrumar a mesa entre uma reserva e a seguinte.
    folga_min              smallint NOT NULL DEFAULT 15,
    -- De quanto em quanto tempo os horários são oferecidos.
    passo_min              smallint NOT NULL DEFAULT 30,
    antecedencia_min_horas smallint NOT NULL DEFAULT 2,
    antecedencia_max_dias  smallint NOT NULL DEFAULT 30,
    -- O que o site pede de quem ainda não tem cadastro. Ligado = nome, data de
    -- nascimento, gênero e cidade; desligado = só o nome.
    -- ⚠️ Data de nascimento é dado pessoal: só vale guardar se a casa for usar.
    cadastro_completo      boolean NOT NULL DEFAULT true,
    atualizado_em          timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_reserva_confirmacao CHECK (confirmacao IN ('AUTOMATICA', 'MANUAL')),
    CONSTRAINT ck_reserva_teto        CHECK (teto_online BETWEEN 1 AND 99),
    CONSTRAINT ck_reserva_passo       CHECK (passo_min BETWEEN 5 AND 240)
);

-- O horário de funcionamento, um dia da semana por linha.
--
-- 🔑 **São TRÊS horas, não uma.** `abre` e `fecha` são a loja; `ultima_reserva`
-- é até quando a agenda aceita marcar. O site que a casa usa hoje diz
-- "Ter-Sex 09h30-17h00" — e 17h00 ali é a última reserva, não o fechamento. A
-- diferença entre as duas é exatamente a permanência: quem senta às 17h ainda
-- vai ficar mais uma hora e meia.
--
-- 🔑 **E é TABELA, não campo.** Sábado abre 9h e fecha 18h30; terça a sexta
-- abrem 9h30 e fecham 18h. Um par `abertura`/`fechamento` na configuração não
-- teria como dizer isso, e `dias_fechados` como lista só responderia metade.
--
-- ⚠️ **`dia_semana` é ISO: 1 = segunda … 7 = domingo**, igual a
-- `parametros.fechamento_dia_semana`, que já existia. Postgres responde nesse
-- mesmo formato com `extract(isodow from data)`. ⚠️ NÃO é o `dow` (0=domingo)
-- nem o `Date.getDay()` do JavaScript — a tela converte. Duas convenções de dia
-- da semana no mesmo sistema é erro que não dá mensagem nenhuma: só marca no
-- dia errado.
CREATE TABLE IF NOT EXISTS reserva_horarios (
    id_unidade     integer  NOT NULL REFERENCES unidades(id) ON DELETE CASCADE,
    dia_semana     smallint NOT NULL,
    aberto         boolean  NOT NULL DEFAULT false,
    abre           time     NOT NULL DEFAULT '09:00',
    fecha          time     NOT NULL DEFAULT '18:00',
    ultima_reserva time     NOT NULL DEFAULT '17:00',
    PRIMARY KEY (id_unidade, dia_semana),
    CONSTRAINT ck_reserva_dia CHECK (dia_semana BETWEEN 1 AND 7),
    -- A última reserva não pode ser depois do fechamento: seria prometer mesa
    -- para depois de a casa fechar.
    CONSTRAINT ck_reserva_janela CHECK (abre < fecha AND ultima_reserva <= fecha)
);

-- Quanto tempo a mesa fica ocupada — e isso MUDA com a hora do dia.
--
-- 🔑 **Um número só para o dia inteiro erra nas duas pontas**: café da manhã não
-- segura a mesa como um almoço. É esta coluna que decide quando a mesa volta a
-- aparecer como livre, então errá-la é vender mesa que não existe (curto demais)
-- ou recusar mesa vazia (longo demais).
CREATE TABLE IF NOT EXISTS reserva_permanencias (
    id         serial PRIMARY KEY,
    id_unidade integer     NOT NULL REFERENCES unidades(id) ON DELETE CASCADE,
    nome       varchar(40) NOT NULL,
    de         time        NOT NULL,
    ate        time        NOT NULL,
    minutos    smallint    NOT NULL,
    CONSTRAINT ck_permanencia_faixa   CHECK (de < ate),
    CONSTRAINT ck_permanencia_minutos CHECK (minutos BETWEEN 5 AND 720)
);
CREATE INDEX IF NOT EXISTS ix_reserva_permanencias_unidade
    ON reserva_permanencias (id_unidade, de);

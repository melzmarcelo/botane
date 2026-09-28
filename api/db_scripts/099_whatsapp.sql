-- Mensagens por WhatsApp (API oficial da Meta), configuráveis por LOJA.
--
-- 🔑 **Pedido do dono (28/09/2026):** *"envio de mensagens via WhatsApp para clientes, como
-- reservas, confirmação de reserva, prêmios e outros assuntos, de forma configurável; e a
-- confirmação de presença via WhatsApp, recebendo a opção selecionada pelo cliente."* E:
-- *"API da Meta direto, com o número atual. Tudo configurável, numa aba nova dentro da loja:
-- a loja faz toda a validação com a Meta e só informa como vamos usar — fica configurável
-- para outros clientes."* Estudo em `docs/whatsapp-estudo.md`.
--
-- As CREDENCIAIS (token, segredo do app) ficam na `integracoes` que já existe, `servico =
-- 'whatsapp'`, cifradas como as do Omie e do PDV. Aqui: os avisos, a fila e o que o
-- cliente respondeu.
-- Idempotente.

-- Cada aviso que a loja pode ligar. ⚠️ Mensagem que a casa inicia é SEMPRE um modelo
-- aprovado pela Meta: `modelo` é o NOME dele lá, e `idioma` o código (pt_BR).
CREATE TABLE IF NOT EXISTS whatsapp_avisos (
    id_unidade    integer NOT NULL REFERENCES unidades(id) ON DELETE CASCADE,
    evento        varchar(30) NOT NULL,
    ativo         boolean NOT NULL DEFAULT false,
    modelo        varchar(120),
    idioma        varchar(10) NOT NULL DEFAULT 'pt_BR',
    -- Horas antes (lembrete) ou dias antes (prêmio vencendo). Nulo onde não se aplica.
    antecedencia  integer,
    atualizado_em timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (id_unidade, evento)
);

-- A fila E o histórico: cada aviso vira uma linha, e ela registra o que aconteceu.
CREATE TABLE IF NOT EXISTS whatsapp_mensagens (
    id            bigserial PRIMARY KEY,
    id_unidade    integer NOT NULL REFERENCES unidades(id) ON DELETE CASCADE,
    evento        varchar(30) NOT NULL,
    -- 🔑 **A mesma mensagem não sai duas vezes** (regra 8): `chave` identifica o fato
    -- (a reserva naquele dia e hora; o prêmio). Remarcar muda a chave e gera outra.
    chave         varchar(120) NOT NULL,
    id_reserva    integer REFERENCES reservas(id) ON DELETE SET NULL,
    id_cliente    integer REFERENCES reserva_clientes(id) ON DELETE SET NULL,
    telefone      varchar(20) NOT NULL,
    nome          varchar(120),
    variaveis     jsonb NOT NULL DEFAULT '[]',
    -- O texto já montado, para o histórico dizer O QUE foi enviado.
    texto         text,
    status        varchar(12) NOT NULL DEFAULT 'FILA'
                  CHECK (status IN ('FILA', 'ENVIADA', 'ENTREGUE', 'LIDA', 'RESPONDIDA',
                                    'FALHOU', 'SIMULADA', 'CANCELADA')),
    agendada_para timestamptz NOT NULL DEFAULT now(),
    enviada_em    timestamptz,
    id_meta       varchar(120),
    tentativas    integer NOT NULL DEFAULT 0,
    erro          text,
    resposta      varchar(40),
    respondida_em timestamptz,
    criada_em     timestamptz NOT NULL DEFAULT now(),
    atualizada_em timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_whatsapp_mensagem_fato
    ON whatsapp_mensagens (id_unidade, evento, chave);
CREATE INDEX IF NOT EXISTS ix_whatsapp_fila
    ON whatsapp_mensagens (agendada_para) WHERE status = 'FILA';
CREATE INDEX IF NOT EXISTS ix_whatsapp_meta ON whatsapp_mensagens (id_meta);
CREATE INDEX IF NOT EXISTS ix_whatsapp_loja ON whatsapp_mensagens (id_unidade, criada_em DESC);

-- 🔑 **A presença que o cliente confirmou pelo WhatsApp** — o ✓ da agenda. Não é status:
-- a reserva continua CONFIRMADA; isto é o que o cliente respondeu ao lembrete.
ALTER TABLE reservas ADD COLUMN IF NOT EXISTS presenca varchar(12);
ALTER TABLE reservas ADD COLUMN IF NOT EXISTS presenca_em timestamptz;
DO $$ BEGIN
    ALTER TABLE reservas ADD CONSTRAINT ck_reserva_presenca
        CHECK (presenca IS NULL OR presenca IN ('CONFIRMADA', 'CANCELOU'));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- Quem pediu para não receber avisos de MARKETING (aniversário). Os da própria reserva
-- continuam: são o serviço que o cliente pediu.
ALTER TABLE reserva_clientes ADD COLUMN IF NOT EXISTS whatsapp_optout_em timestamptz;

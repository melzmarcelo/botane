-- 163 — Módulo Financeiro, etapa 1: contas a pagar.
-- Idempotente. Cria tabelas, categorias iniciais, permissões e a chave Pix no cadastro de Pessoas.
-- Não reescreve dado nenhum.
--
-- 🔑 **Pedido do dono (24/11/2026):** *"vamos criar um novo módulo financeiro… um contas a
-- pagar, onde poderemos realizar lançamentos a serem pagos. Neste primeiro momento a ideia é
-- suprir a organização de pagamentos e agendamentos de funcionários freelancer, mas a ideia é
-- englobar tudo."* Estudo em `docs/financeiro-estudo.md`.
--
-- 🔑 **Quatro situações**: A_PAGAR → AGENDADO → PAGO, e CANCELADO. O agendado com baixa
-- automática vira PAGO sozinho na data (`baixado_automaticamente`), e estornar a baixa volta ao
-- que era antes (`agendado_para` preenchido = AGENDADO, senão A_PAGAR).
-- ⚠️ Não entra no CMV nem no estoque: é despesa operacional.

-- A chave Pix: o dado que mais se procura no dia de pagar o freelancer. (O CPF entra no campo de
-- documento que já existe, `cnpj`, que guarda só os dígitos.)
ALTER TABLE fornecedores ADD COLUMN IF NOT EXISTS chave_pix varchar(140);

CREATE TABLE IF NOT EXISTS financeiro_categorias (
    id     serial PRIMARY KEY,
    nome   varchar(60) NOT NULL,
    ativo  boolean NOT NULL DEFAULT true,
    ordem  smallint NOT NULL DEFAULT 0
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_financeiro_categorias_nome
    ON financeiro_categorias (lower(nome));

INSERT INTO financeiro_categorias (nome, ordem) VALUES
    ('Freelancer', 10), ('Fornecedor', 20), ('Aluguel', 30), ('Contas de consumo', 40),
    ('Impostos e taxas', 50), ('Serviços', 60), ('Manutenção', 70), ('Outros', 90)
ON CONFLICT DO NOTHING;

CREATE TABLE IF NOT EXISTS contas_pagar (
    id                      serial PRIMARY KEY,
    id_unidade              integer NOT NULL REFERENCES unidades(id),
    id_pessoa               integer NOT NULL REFERENCES fornecedores(id),
    id_categoria            integer REFERENCES financeiro_categorias(id),
    descricao               varchar(200) NOT NULL,
    -- O freelancer: a função do dia ("garçom", "cozinha"). Livre, para não virar cadastro.
    funcao                  varchar(60),
    competencia             date NOT NULL,
    vencimento              date NOT NULL,
    valor                   numeric(14,2) NOT NULL CHECK (valor > 0),
    observacao              varchar(300),
    status                  varchar(10) NOT NULL DEFAULT 'A_PAGAR'
                            CHECK (status IN ('A_PAGAR', 'AGENDADO', 'PAGO', 'CANCELADO')),
    agendado_para           date,
    forma                   varchar(15)
                            CHECK (forma IN ('PIX', 'TRANSFERENCIA', 'BOLETO', 'DINHEIRO', 'CARTAO', 'OUTRO')),
    baixa_automatica        boolean NOT NULL DEFAULT true,
    pago_em                 date,
    valor_pago              numeric(14,2) CHECK (valor_pago >= 0),
    baixado_automaticamente boolean NOT NULL DEFAULT false,
    comprovante             varchar(120),
    -- As contas lançadas juntas na "equipe do dia".
    lote                    varchar(20),
    criado_por              integer REFERENCES usuarios(id),
    criado_em               timestamptz NOT NULL DEFAULT now(),
    agendado_por            integer REFERENCES usuarios(id),
    pago_por                integer REFERENCES usuarios(id),
    cancelado_por           integer REFERENCES usuarios(id),
    cancelado_em            timestamptz,
    CONSTRAINT ck_conta_agendada CHECK (status <> 'AGENDADO' OR agendado_para IS NOT NULL),
    CONSTRAINT ck_conta_paga CHECK (status <> 'PAGO' OR (pago_em IS NOT NULL AND valor_pago IS NOT NULL))
);

CREATE INDEX IF NOT EXISTS ix_contas_pagar_unidade_status ON contas_pagar (id_unidade, status, vencimento);
CREATE INDEX IF NOT EXISTS ix_contas_pagar_pessoa ON contas_pagar (id_pessoa);
-- O agendador da baixa automática procura por aqui.
CREATE INDEX IF NOT EXISTS ix_contas_pagar_agendadas ON contas_pagar (agendado_para)
    WHERE status = 'AGENDADO';

INSERT INTO permissoes (chave, modulo, descricao, ordem) VALUES
    ('financeiro.pagar_ver',    'Financeiro', 'Ver as contas a pagar e o que se paga a cada pessoa', 900),
    ('financeiro.pagar_lancar', 'Financeiro', 'Lançar, corrigir, agendar e cancelar contas a pagar', 905),
    ('financeiro.pagar_baixar', 'Financeiro', 'Dar baixa (pagar), anexar comprovante e estornar a baixa', 910)
ON CONFLICT (chave) DO UPDATE
    SET modulo = EXCLUDED.modulo, descricao = EXCLUDED.descricao, ordem = EXCLUDED.ordem;

INSERT INTO papel_permissoes (id_papel, chave)
SELECT p.id, x.chave
  FROM papeis p CROSS JOIN permissoes x
 WHERE p.sistema AND x.chave LIKE 'financeiro.pagar_%'
   AND p.nome IN ('Administrador', 'Gerente')
ON CONFLICT DO NOTHING;

-- 167 — Módulo Financeiro, etapa 3: contas fixas (recorrência mensal) e parcelas.
-- Idempotente. Cria a tabela das contas fixas e três colunas em `contas_pagar`. Não reescreve dado.
--
-- 🔑 Estudo em `docs/financeiro-estudo.md`, etapa 3: "Aluguel e contas mensais gerados sozinhos;
-- parcelar uma compra". Pedido do dono (25/11/2026): "pode seguir com a etapa 3 do financeiro".
--
-- 🔑 **Conta fixa** = o molde do mês (pessoa, categoria, o que é, valor, dia do vencimento).
-- O sistema gera a conta de cada mês sozinho, `antecedencia_dias` antes do vencimento, a partir
-- do mês de `inicio` e até o de `fim` (nulo = sem fim). A conta gerada é uma conta a pagar como
-- outra qualquer: corrige, agenda, paga, cancela.
-- 🔑 **Idempotência é do BANCO** (regra 8): uma conta por conta fixa e por mês, pelo índice único
-- `(id_conta_fixa, competencia)`. A competência da gerada é o dia 1º do mês de referência.
-- ⚠️ A cancelada continua ocupando o mês: cancelar a conta de dezembro NÃO a faz nascer de novo.
--
-- 🔑 **Parcelas**: uma compra em N vezes vira N contas, `parcela`/`parcelas` (2/3) e o mesmo
-- `lote`. O valor total é rateado em centavos, a sobra nas primeiras (100/3 = 33,34 + 33,33 + 33,33).

CREATE TABLE IF NOT EXISTS contas_fixas (
    id                serial PRIMARY KEY,
    id_unidade        integer NOT NULL REFERENCES unidades(id),
    id_pessoa         integer NOT NULL REFERENCES fornecedores(id),
    id_categoria      integer REFERENCES financeiro_categorias(id),
    descricao         varchar(200) NOT NULL,
    valor             numeric(14,2) NOT NULL CHECK (valor > 0),
    -- Luz, água, gás: o valor é uma previsão, e a conta gerada avisa para corrigir.
    valor_variavel    boolean NOT NULL DEFAULT false,
    -- 31 em fevereiro vence no último dia do mês.
    dia_vencimento    smallint NOT NULL CHECK (dia_vencimento BETWEEN 1 AND 31),
    -- Sempre o dia 1º: o mês da primeira e o da última conta.
    inicio            date NOT NULL CHECK (extract(day FROM inicio) = 1),
    fim               date CHECK (fim IS NULL OR (extract(day FROM fim) = 1 AND fim >= inicio)),
    antecedencia_dias smallint NOT NULL DEFAULT 10 CHECK (antecedencia_dias BETWEEN 0 AND 60),
    -- Débito automático: a conta já nasce AGENDADA para o vencimento, com baixa automática.
    agendar           boolean NOT NULL DEFAULT false,
    forma             varchar(15)
                      CHECK (forma IN ('PIX', 'TRANSFERENCIA', 'BOLETO', 'DINHEIRO', 'CARTAO', 'OUTRO')),
    observacao        varchar(300),
    ativo             boolean NOT NULL DEFAULT true,
    criado_por        integer REFERENCES usuarios(id),
    criado_em         timestamptz NOT NULL DEFAULT now(),
    encerrado_por     integer REFERENCES usuarios(id),
    encerrado_em      timestamptz,
    CONSTRAINT ck_fixa_agendar_forma CHECK (NOT agendar OR forma IS NOT NULL)
);
CREATE INDEX IF NOT EXISTS ix_contas_fixas_unidade ON contas_fixas (id_unidade) WHERE ativo;

ALTER TABLE contas_pagar ADD COLUMN IF NOT EXISTS id_conta_fixa integer REFERENCES contas_fixas(id);
ALTER TABLE contas_pagar ADD COLUMN IF NOT EXISTS parcela  smallint;
ALTER TABLE contas_pagar ADD COLUMN IF NOT EXISTS parcelas smallint;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_conta_parcela') THEN
        ALTER TABLE contas_pagar ADD CONSTRAINT ck_conta_parcela CHECK (
            (parcela IS NULL AND parcelas IS NULL)
            OR (parcelas BETWEEN 2 AND 60 AND parcela BETWEEN 1 AND parcelas));
    END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS ux_contas_pagar_fixa_mes
    ON contas_pagar (id_conta_fixa, competencia) WHERE id_conta_fixa IS NOT NULL;

-- Contas a receber do consumo: o lote de cobrança substitui o período.
--
-- 🔑 **Pedido do dono (22/10/2026):** "tirar esta questão de períodos, ter que
-- abrir e fechar períodos de consumo [...] o usuário possa lançar os documentos
-- para a data que for necessário. Ai ter uma espécie de contas a receber [...]
-- gerar um lote, e quando receber, fazer a baixa destes documentos." Decidido com
-- ele: UM lote por pessoa (gerados de várias de uma vez), baixa só do lote
-- inteiro, permuta como forma de pagamento, relatório baixado e mandado por fora.
--
-- ⚠️ **"Em aberto" passa a ser a venda com pessoa e SEM lote** (`id_consumo_lote`).
-- É a mesma ideia do carimbo da 057 — um fato, não uma conta de datas —, só que
-- agora o carimbo é o lote, e o lote é de uma pessoa só.
-- ⚠️ **Nada do período se apaga.** `consumo_periodos`, `consumo_periodo_pessoas`
-- e `vendas.id_consumo_periodo` ficam como estão, como histórico; o que já foi
-- fechado vira lote RECEBIDO (abaixo), com o mesmo valor do recibo.

CREATE TABLE IF NOT EXISTS consumo_lotes (
    id                  serial PRIMARY KEY,
    id_unidade          integer NOT NULL REFERENCES unidades(id),
    id_pessoa           integer NOT NULL REFERENCES fornecedores(id),
    -- A data de corte escolhida: entra o que estava em aberto ATÉ ela.
    ate                 date NOT NULL,
    -- O documento mais antigo do lote (informativo).
    desde               date,
    status              varchar(10) NOT NULL DEFAULT 'ABERTO'
                        CHECK (status IN ('ABERTO', 'RECEBIDO', 'CANCELADO')),
    -- 🔑 O valor do lote, CONGELADO: é o que foi mandado à pessoa. Só muda
    -- quando um documento sai do lote, e aí o lote ainda não foi pago.
    cupons              integer NOT NULL DEFAULT 0,
    itens               integer NOT NULL DEFAULT 0,
    total_cheio         numeric(18,2) NOT NULL DEFAULT 0,
    desconto            numeric(18,2) NOT NULL DEFAULT 0,
    total               numeric(18,2) NOT NULL DEFAULT 0,
    criado_em           timestamptz NOT NULL DEFAULT now(),
    id_usuario_criou    integer REFERENCES usuarios(id),
    -- A baixa: quando o dinheiro (ou a permuta) entrou, e como.
    recebido_em         date,
    forma_pagamento     varchar(15)
                        CHECK (forma_pagamento IN ('PIX', 'DINHEIRO', 'CARTAO',
                               'TRANSFERENCIA', 'FOLHA', 'PERMUTA', 'OUTRO')),
    baixado_em          timestamptz,
    id_usuario_baixou   integer REFERENCES usuarios(id),
    observacao          text,
    observacao_baixa    text,
    cancelado_em        timestamptz,
    id_usuario_cancelou integer REFERENCES usuarios(id),
    -- De onde veio, quando o lote nasceu de um período fechado antes dos lotes.
    id_consumo_periodo  integer REFERENCES consumo_periodos(id),
    CONSTRAINT ck_consumo_lote_baixa
        CHECK (status <> 'RECEBIDO' OR (recebido_em IS NOT NULL AND forma_pagamento IS NOT NULL))
);

CREATE INDEX IF NOT EXISTS ix_consumo_lote_unidade
    ON consumo_lotes (id_unidade, status, criado_em DESC);
CREATE INDEX IF NOT EXISTS ix_consumo_lote_pessoa
    ON consumo_lotes (id_pessoa, criado_em DESC);

-- ⚠️ É o que torna a conversão abaixo idempotente: um período fechado vira UM
-- lote por pessoa, e rodar de novo não cria o segundo.
CREATE UNIQUE INDEX IF NOT EXISTS ux_consumo_lote_do_periodo
    ON consumo_lotes (id_consumo_periodo, id_pessoa)
    WHERE id_consumo_periodo IS NOT NULL;

-- 🔑 **Um documento está em UM lote só, e quem garante é a COLUNA.** Dois
-- cliques gerando lote para a mesma pessoa disputam as mesmas linhas, e o
-- segundo UPDATE reavalia `id_consumo_lote IS NULL` depois do primeiro — não
-- acha nada e não cobra duas vezes.
ALTER TABLE vendas
    ADD COLUMN IF NOT EXISTS id_consumo_lote integer REFERENCES consumo_lotes(id);

COMMENT ON COLUMN vendas.id_consumo_lote IS
    'Lote de cobrança em que este consumo está. NULL = em aberto (ainda não cobrado).';

CREATE INDEX IF NOT EXISTS ix_venda_a_receber
    ON vendas (id_unidade, id_pessoa, data)
    WHERE id_pessoa IS NOT NULL AND id_consumo_lote IS NULL;
CREATE INDEX IF NOT EXISTS ix_venda_do_lote
    ON vendas (id_consumo_lote) WHERE id_consumo_lote IS NOT NULL;

-- 🔑 **O que já foi fechado vira lote RECEBIDO**, um por pessoa de cada período,
-- com o valor do RECIBO congelado (não um recálculo: o que foi cobrado naquele
-- dia é um fato). A baixa fica na data do fechamento, que é quando a casa deu
-- o consumo por pago; a forma não foi registrada na época, então é OUTRO.
INSERT INTO consumo_lotes
       (id_unidade, id_pessoa, ate, desde, status, cupons, itens, total_cheio,
        desconto, total, criado_em, id_usuario_criou, recebido_em, forma_pagamento,
        baixado_em, id_usuario_baixou, observacao, id_consumo_periodo)
SELECT p.id_unidade, v.id_pessoa, p.fim, min(v.data), 'RECEBIDO',
       coalesce(max(c.cupons), count(DISTINCT v.id) FILTER (WHERE NOT v.cancelada)),
       coalesce(max(c.itens), 0), coalesce(max(c.total_cheio), 0),
       coalesce(max(c.desconto), 0), coalesce(max(c.total), 0),
       coalesce(p.fechado_em, now()), p.id_usuario_fechou,
       (coalesce(p.fechado_em, now()) AT TIME ZONE 'America/Sao_Paulo')::date, 'OUTRO',
       coalesce(p.fechado_em, now()), p.id_usuario_fechou,
       'Fechado no período ' || coalesce(p.nome, to_char(p.inicio, 'DD/MM/YYYY') || ' a '
                                                 || to_char(p.fim, 'DD/MM/YYYY'))
           || ', antes dos lotes de cobrança',
       p.id
  FROM consumo_periodos p
  JOIN vendas v ON v.id_consumo_periodo = p.id AND v.id_pessoa IS NOT NULL
  LEFT JOIN consumo_periodo_pessoas c ON c.id_periodo = p.id AND c.id_pessoa = v.id_pessoa
 WHERE p.status = 'FECHADO'
 GROUP BY p.id, p.id_unidade, p.fim, p.nome, p.inicio, p.fechado_em, p.id_usuario_fechou,
          v.id_pessoa
ON CONFLICT (id_consumo_periodo, id_pessoa) WHERE id_consumo_periodo IS NOT NULL DO NOTHING;

UPDATE vendas v
   SET id_consumo_lote = l.id
  FROM consumo_lotes l
 WHERE l.id_consumo_periodo = v.id_consumo_periodo
   AND l.id_pessoa = v.id_pessoa
   AND v.id_consumo_lote IS NULL;

-- ⚠️ A chave continua a mesma — quem abria e fechava período é quem gera lote e
-- dá baixa. Trocar de chave tiraria o acesso de quem já usa, sem ninguém saber.
UPDATE permissoes
   SET descricao = 'Contas a receber do consumo: gerar lotes de cobrança e dar baixa'
 WHERE chave = 'consumo.periodos';

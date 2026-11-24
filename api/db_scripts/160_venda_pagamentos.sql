-- 160 — Como cada venda foi paga: as finalizadoras do cupom do PDV Legal.
-- Idempotente. Só cria tabela e índices: não reescreve dado nenhum. As vendas já gravadas
-- ganham pagamentos quando o dia é relido (`POST /pdv/pagamentos/completar`).
--
-- 🔑 **Pedido do dono (24/11/2026):** *"conseguimos a finalizadora da compra, se foi dinheiro,
-- debito, credito, pix ..."*. Estudo em `docs/pdv-finalizadoras-estudo.md`. O cupom sempre
-- trouxe `formaPgtos`; o mapeador lia itens e total e jogava a lista fora.
--
-- 🔑 **Uma linha por pagamento, como veio.** O TROCO é uma linha à parte e positiva
-- (DINHEIRO 200 + TROCO 36,50 num cupom de 163,50): guardar já descontado perderia o que a
-- gaveta recebeu, que é o número da conferência de caixa. Dinheiro líquido = DINHEIRO − TROCO.
-- 🔑 **O grupo sai da CLASSIFICAÇÃO do PDV, não do nome**: o nome é texto que o cliente edita
-- lá; o nome original fica em `nome_pdv` ("PIX WEB" no grupo PIX).

CREATE TABLE IF NOT EXISTS venda_pagamentos (
    id             bigserial PRIMARY KEY,
    id_venda       bigint NOT NULL REFERENCES vendas(id) ON DELETE CASCADE,
    id_unidade     integer NOT NULL REFERENCES unidades(id),
    grupo          varchar(12) NOT NULL
                   CHECK (grupo IN ('DINHEIRO', 'CREDITO', 'DEBITO', 'PIX', 'VALE', 'TROCO',
                                    'OUTRO')),
    nome_pdv       varchar(60),
    cod_forma_pdv  bigint,
    valor          numeric(14,2) NOT NULL CHECK (valor >= 0)
);

CREATE INDEX IF NOT EXISTS ix_venda_pagamentos_venda ON venda_pagamentos (id_venda);
CREATE INDEX IF NOT EXISTS ix_venda_pagamentos_unidade ON venda_pagamentos (id_unidade, grupo);

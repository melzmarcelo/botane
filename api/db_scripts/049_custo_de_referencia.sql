-- O custo de REFERÊNCIA do produto — o último degrau da cascata de custo.
--
-- 🔑 O problema medido em 01/09/2026: **2.323 produtos ativos que controlam
-- estoque estavam sem custo nenhum** — nem médio do razão (nunca entrou nota
-- aqui), nem último preço de fornecedor. Sem custo não há ficha, não há CMV
-- teórico, não há margem: o prato entra na conta valendo zero e o food cost
-- sai bom demais, sem nada denunciando.
--
-- O Omie já sabe esse número (o CMC da posição de estoque), e trazê-lo destrava
-- a conta para todos eles de uma vez.
--
-- ⚠️ **É REFERÊNCIA, não movimento.** Nada aqui cria saldo nem entra no razão:
-- o CMV real continua saindo do que a casa de fato comprou e contou. Este campo
-- só responde "quanto custa uma unidade disto" quando ninguém mais sabe — e por
-- isso é o ÚLTIMO degrau, depois do médio do estoque e do preço do fornecedor.
-- Fosse movimento, uma carga errada não se apagaria: o razão é append-only.
--
-- ⚠️ `origem` guarda de onde veio (hoje: OMIE). Sem ela, daqui a seis meses
-- ninguém sabe se aquele número foi importado ou digitado por alguém — e a
-- diferença decide se ele pode ser sobrescrito sem perguntar.
--
-- ⚠️ Seis casas, como todo custo unitário deste banco.

ALTER TABLE produtos
    ADD COLUMN IF NOT EXISTS custo_referencia        numeric(18,6),
    ADD COLUMN IF NOT EXISTS custo_referencia_em     timestamptz,
    ADD COLUMN IF NOT EXISTS custo_referencia_origem varchar(20);

COMMENT ON COLUMN produtos.custo_referencia IS
    'Custo de uma unidade de estoque quando não há médio no razão nem preço de '
    'fornecedor. Último degrau de custos.custo_do_insumo. Não cria saldo.';

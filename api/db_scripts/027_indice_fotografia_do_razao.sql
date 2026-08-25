-- O índice que serve à FOTOGRAFIA do estoque numa data passada.
--
-- `valor_do_estoque` e `movimentacao_por_produto` perguntam a mesma coisa: qual
-- foi o ÚLTIMO movimento de cada produto e local antes de tal dia, e com que
-- saldo e custo médio ele ficou. Em SQL isso é um `DISTINCT ON (id_produto,
-- id_local) ... ORDER BY id DESC`, e sem índice o banco varre o razão inteiro e
-- ordena tudo. Medido com 400.000 movimentos: 837 ms para o valor do estoque e
-- 1.262 ms para o relatório de movimentação do mês.
--
-- Este índice dá a ordem que a consulta pede e ainda carrega os dois valores no
-- próprio índice (`INCLUDE`), então o banco não precisa voltar à tabela:
-- 391 ms e 680 ms. Data de HOJE nem chega aqui — responde pelo `estoque_saldos`.
--
-- ⚠️ Índice em tabela append-only custa escrita: cada movimento novo o atualiza.
-- É o preço de responder "quanto eu tinha em 31 de julho" sem varrer três anos.

CREATE INDEX IF NOT EXISTS ix_mov_fotografia
    ON estoque_movimentos (id_unidade, id_produto, id_local, id DESC)
 INCLUDE (saldo_apos, custo_medio_apos, data_movimento);

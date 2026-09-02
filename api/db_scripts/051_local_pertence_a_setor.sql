-- Botané 051 — o local de estoque pertence a um SETOR. Idempotente.
--
-- 🔑 **O processo real da casa, descrito pelo dono em 01/09/2026:** o açúcar
-- entra no Estoque Central, e de manhã cada setor leva um pacote para o seu
-- canto — Bar, Confeitaria, Cozinha, Cafeteria. Durante a semana cada um gasta
-- do que pegou, e no fim cada setor conta o SEU estoque.
--
-- 🔑 **O que ele chama de "setor" nesse fluxo é, no vocabulário do sistema, um
-- LOCAL** — o teste é o comportamento: guarda mercadoria, recebe transferência
-- e é contado num inventário próprio. Isso é a definição de local aqui. Modelar
-- assim faz a transferência da manhã, o inventário por setor e o saldo por
-- setor funcionarem com o que já existe, e resolve sozinho o "um produto pode
-- ter mais de um setor": ele não precisa de vários setores, ele tem SALDO em
-- vários locais.
--
-- Esta coluna é a ponte que faltava entre os dois eixos. Sem ela, "local" e
-- "setor" eram universos separados — e é por isso que o CMV por setor sai do
-- `produtos.id_setor`, o setor do PRODUTO, um só. Com açúcar em quatro setores,
-- todo o consumo de açúcar é atribuído a um deles.
--
-- ⚠️ **NULO é resposta legítima, e é o padrão.** O Estoque Central não pertence
-- a setor nenhum — ele serve a todos. Exigir setor em todo local obrigaria a
-- inventar um para a despensa, e um setor inventado suja o relatório que a
-- coluna existe para melhorar.
--
-- ⚠️ **`ON DELETE SET NULL`, não `CASCADE`**: apagar um setor não pode levar
-- junto o local — ele guarda saldo e razão. Perder a classificação é o custo
-- certo; perder a prateleira, não.
--
-- ⚠️ Esta migração NÃO muda número nenhum: `relatorios.cmv_por_grupo` continua
-- agrupando por `produtos.id_setor`. Passar o CMV a somar pelo setor do LOCAL
-- do movimento é a peça seguinte, e é uma entrega própria — ela reescreve um
-- relatório cuja identidade ("a soma dos grupos fecha com o CMV do período") a
-- bateria cobra.

ALTER TABLE locais_estoque
    ADD COLUMN IF NOT EXISTS id_setor integer REFERENCES setores(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS ix_local_setor ON locais_estoque (id_setor)
    WHERE id_setor IS NOT NULL;

COMMENT ON COLUMN locais_estoque.id_setor IS
    'A que setor esta prateleira pertence. NULO para o estoque central, que '
    'serve a todos. É a ponte entre onde a mercadoria está e quem a consome.';

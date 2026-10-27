-- 137 — Quem PRODUZ não é, por força, a quem o produto pertence. Idempotente.
--
-- 🔑 **Pedido do dono (27/10/2026):** *"Podemos ter produção de ficha técnica que é
-- realizada por um setor, onde este não é seu local de estoque. Exemplo: a
-- Confeitaria produz bolachas que vão junto com o café. A produção é
-- responsabilidade da Confeitaria. Mas após pronto, este produto vai direto para o
-- estoque da Cafeteria."*
--
-- ⚠️ **`produtos.id_setor` fazia dois papéis**: a quem o produto PERTENCE (o CMV por
-- setor, os relatórios) e quem o PRODUZ (a agenda da tela inicial de cada um). A
-- bolacha da Cafeteria aparecia para a Cafeteria produzir; a da Confeitaria pesava
-- no CMV da Confeitaria. Esta coluna separa o segundo papel.
--
-- Nulo = quem produz é o setor do produto, como sempre foi — é o que faz a migração
-- não mudar nada para os produtos de hoje.
-- 🔑 Com ela, os INSUMOS saem primeiro dos locais desse setor (`locais_estoque.id_setor`,
-- 051): a farinha da bolacha sai do estoque da Confeitaria, que é onde ela está.
-- O produzido continua entrando no local do PRODUTO (o estoque da Cafeteria).
ALTER TABLE produtos
    ADD COLUMN IF NOT EXISTS id_setor_producao integer REFERENCES setores(id) ON DELETE SET NULL;

COMMENT ON COLUMN produtos.id_setor_producao IS
    'Setor que PRODUZ (agenda, insumos). Nulo = o próprio id_setor. O produto continua pertencendo ao id_setor.';

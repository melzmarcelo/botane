-- 132 — Trocar o produto de um item SÓ NESTA NOTA. Idempotente.
--
-- 🔑 **Pedido do dono (23/10/2026):** *"ao selecionar o produto correto para dar
-- entrada, acaba já vinculando os produtos, mas gostaria de ter a opção de alterar o
-- produto somente para esta nota, e não vincular os produtos"*.
--
-- O servidor já sabia trocar sem aprender (`aprender=false` não grava o de-para em
-- `codigos_externos`), mas a tela mandava sempre `true`. E faltava o ITEM lembrar que
-- a escolha foi só dele: o botão "vincular fornecedores" deduz o código do produto no
-- fornecedor a partir dos itens de nota (`importador.vincular_fornecedores`) — e esse
-- código é o degrau 4 da conciliação. Sem a marca, a troca "só nesta nota" viraria
-- vínculo pela porta dos fundos no dia em que alguém apertasse o botão.
ALTER TABLE nota_itens
    ADD COLUMN IF NOT EXISTS so_nesta_nota boolean NOT NULL DEFAULT false;

COMMENT ON COLUMN nota_itens.so_nesta_nota IS
    'O produto deste item foi escolhido só para esta nota, sem ensinar o de-para do '
    'fornecedor (migração 132). Não alimenta codigo_no_fornecedor.';

-- Produto INCLUÍDO numa contagem aberta — achado na prateleira, fora da lista.
--
-- 🔑 **Pedido do dono (26/09/2026):** *"ao realizar um inventário de um setor, e for
-- encontrado um produto que não estava no inventário ou não estava naquele setor, como
-- proceder? … pode incluir."* A lista nasce na abertura (o recorte do momento); o que
-- aparece na prateleira depois entra por aqui, marcado, para quem fechar saber que
-- aquela linha não veio do recorte — e é justamente a que mais explica diferença.
-- Idempotente.

ALTER TABLE inventario_itens ADD COLUMN IF NOT EXISTS incluido boolean NOT NULL DEFAULT false;

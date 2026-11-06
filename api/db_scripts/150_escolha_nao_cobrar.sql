-- 150 — Item de escolha que NÃO cobra a opção escolhida (a embalagem da cesta). Idempotente.
--
-- 🔑 **Pedido do dono (06/11/2026):** "Monte sua cesta" com Cesta Grande e Cesta Média —
-- *"gostaria de ter a opção de Não cobrar o item, aí este preço não é apresentado … a embalagem
-- selecionada já vir marcada, não podendo desmarcar, e este item não contabiliza no mínimo e
-- máximo"*; e, perguntado, *"não cobra, a embalagem sai de graça"*.
-- Com a marca, a opção entra no pedido a R$ 0 (a linha continua indo, para o PDV lançar a
-- embalagem) e o cliente paga só os itens escolhidos.

ALTER TABLE catalogo_itens ADD COLUMN IF NOT EXISTS nao_cobrar boolean NOT NULL DEFAULT false;

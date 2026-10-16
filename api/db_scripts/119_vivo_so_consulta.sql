-- 119 — Cardápio Vivo "só consulta": a vitrine SEM a "minha seleção".
--
-- 🔑 Pedido do dono (16/10/2026): "no modo da mesa, ter uma opção vitrine só consulta, sem
-- minha seleção". A vitrine (113) deixava o cliente montar uma lista para mostrar ao garçom;
-- há casa que quer só o cardápio, sem botão de adicionar nem a estrela no topo.
-- ⚠️ É uma chave do Cardápio Vivo, e não um terceiro `modo`: o modo continua VITRINE (os
-- eventos, os testes A/B e as exceções por mesa/salão seguem iguais). No modo PEDIDO a
-- seleção É o carrinho e a chave não vale.
-- Idempotente; ⚠️ não editar depois de promovida (o db_updater roda de novo se o checksum mudar).

ALTER TABLE cardapio_vivos ADD COLUMN IF NOT EXISTS selecao boolean NOT NULL DEFAULT true;

COMMENT ON COLUMN cardapio_vivos.selecao IS
  'Na vitrine, o cliente monta a "minha seleção" (true) ou só consulta (false). Sem efeito no modo PEDIDO.';

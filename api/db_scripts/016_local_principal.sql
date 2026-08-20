-- Botané 016 — toda loja tem um local principal. Idempotente.
--
-- As telas de estoque, produção e inventário usam o local principal como
-- padrão. Quem cadastrou o primeiro local sem marcar a caixinha ficava com
-- loja nenhuma marcada: o seletor mostrava o nome do local (era o único da
-- lista) e o pedido saía sem local, devolvendo "Local não encontrado" com o
-- local à vista na tela.
--
-- Daqui em diante o primeiro local de cada loja já nasce principal
-- (routers/cadastros.py). Este script arruma quem entrou antes disso: elege o
-- local mais antigo de cada loja que ainda não tem principal.
UPDATE locais_estoque l
   SET principal = true
 WHERE l.ativo
   AND l.id = (SELECT min(x.id) FROM locais_estoque x
                WHERE x.id_unidade = l.id_unidade AND x.ativo)
   AND NOT EXISTS (SELECT 1 FROM locais_estoque p
                    WHERE p.id_unidade = l.id_unidade AND p.principal);

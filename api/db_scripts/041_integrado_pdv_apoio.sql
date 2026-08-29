-- Botané 041 — a marca de "integrado com PDV" também em setor e categoria.
-- Idempotente. Continua sem enviar nada.
--
-- O produto no cardápio do PDV carrega **grupo** (`nomeGrupo`) e **impressora**
-- (`nomeImpressora`) — que são a categoria e o setor daqui. Mandar um produto
-- cujo grupo ainda não existe lá tende a falhar, então a fila de envio é por
-- tipo e em ordem: categorias → setores → produtos. Sem a marca nos dois, a
-- fila teria de mandar as 73 categorias e os 40 setores inteiros, incluindo os
-- que só classificam insumo de compra e não têm o que fazer num PDV.

ALTER TABLE categorias
    ADD COLUMN IF NOT EXISTS integrado_pdv boolean NOT NULL DEFAULT false;

ALTER TABLE setores
    ADD COLUMN IF NOT EXISTS integrado_pdv boolean NOT NULL DEFAULT false;

-- ---------------------------------------------------------------------------
-- A carga: por FATO, nunca por semelhança de nome
-- ---------------------------------------------------------------------------
-- ⚠️ A tentação é casar pelo nome com os grupos que o cardápio trouxe — e é
-- exatamente o palpite que este projeto já removeu uma vez, quando a cascata
-- por semelhança ligou REDBULL a LIMÃO TAITY. O fato disponível é outro e não
-- depende de texto: **esta categoria classifica ao menos um produto que já
-- existe no PDV**. Se ela classifica, ela precisa existir lá.
--
-- ⚠️ `AND NOT integrado_pdv` mantém o script barato ao repetir e **não desfaz o
-- desmarque de ninguém** — mesma regra da 040.

UPDATE categorias c
   SET integrado_pdv = true
 WHERE NOT c.integrado_pdv
   AND EXISTS (SELECT 1 FROM produtos p
                WHERE p.id_categoria = c.id AND p.codigo_pdv IS NOT NULL);

UPDATE setores s
   SET integrado_pdv = true
 WHERE NOT s.integrado_pdv
   AND EXISTS (SELECT 1 FROM produtos p
                WHERE p.id_setor = s.id AND p.codigo_pdv IS NOT NULL);

-- ⚠️ **Sem gatilho aqui, e a ausência tem razão.** Na 040 o gatilho existe
-- porque `produtos.codigo_pdv` é escrito em quatro lugares e "ganhar o código"
-- é um evento observável. Categoria e setor **não têm coluna de código do PDV**
-- — o de-para com `grupoprodutos` e `impressoras` ainda não existe. Quando ele
-- nascer, esta marca vai precisar do mesmo cuidado.

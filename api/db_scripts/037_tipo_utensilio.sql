-- Botané 037 — tipo de produto "Utensílios". Idempotente.
--
-- Pedido da casa: prato, talher, taça, panela e avental entravam como INSUMO ou
-- REVENDA e sumiam dentro do custo da comida.
--
-- ⚠️ O que separa este tipo de EMBALAGEM e MATERIAL_LIMPEZA não é ser "não
-- comida" — os três são. É que utensílio **não é consumido**: ele quebra, some,
-- é levado por engano, e é REPOSTO. Marmita sai com o pedido e não volta;
-- detergente acaba. Uma taça vive meses e some num sábado. Por isso a linha é
-- própria e não um apêndice do grupo de limpeza: a pergunta que ela responde
-- ("quanto se quebrou e se repôs no mês?") não é a mesma.
--
-- ⚠️ Nasce FORA do CMV real, pelo mesmo motivo do grupo de limpeza (032): taça
-- quebrada não é custo do prato, e o food cost é o percentual que vira decisão
-- de cardápio. Como nenhum produto existe com este tipo ainda, nada no passado
-- muda — a apuração de todo mês já fechado continua idêntica.

COMMENT ON COLUMN produtos.tipo IS
    'INSUMO|REVENDA|PRODUZIDO|KIT|EMBALAGEM|MATERIAL_LIMPEZA|UTENSILIO. '
    'A lista viva é TIPOS, em api/models/produtos.py — não há CHECK aqui de '
    'propósito: tipo novo é migração de dado, não alteração de tabela.';

COMMENT ON COLUMN categorias.tipo IS
    'INSUMO|REVENDA|PRODUZIDO|EMBALAGEM|MATERIAL_LIMPEZA|UTENSILIO. '
    'A lista viva é TIPOS_CATEGORIA, em api/models/cadastros.py.';

-- ------------------------------------------------------- grupo do CMV
-- ⚠️ Mesma restrição do 029: o grupo aparece para a funcionalidade não nascer
-- invisível, mas **não ressuscita** se a casa o apagar — a migração roda uma vez
-- só (o db_updater guarda o checksum), e a guarda abaixo respeita quem já
-- decidiu onde este tipo entra.
INSERT INTO cmv_grupos (nome, ordem, considerar_no_cmv)
SELECT 'Utensílios', 20, false
 WHERE NOT EXISTS (SELECT 1 FROM cmv_grupos WHERE lower(nome) = 'utensílios')
   AND NOT EXISTS (SELECT 1 FROM cmv_grupo_tipos WHERE tipo = 'UTENSILIO');

-- ⚠️ `ON CONFLICT (tipo) DO NOTHING` porque `tipo` é a chave primária de
-- cmv_grupo_tipos: se alguém já pôs UTENSILIO noutro grupo, a decisão fica.
INSERT INTO cmv_grupo_tipos (tipo, id_grupo)
SELECT 'UTENSILIO', g.id
  FROM cmv_grupos g
 WHERE lower(g.nome) = 'utensílios'
ON CONFLICT (tipo) DO NOTHING;

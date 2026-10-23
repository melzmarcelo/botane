-- Botané 131 — os tipos de produto reestruturados. Idempotente.
--
-- 🔑 Pedido do dono (23/10/2026), pelo documento "Tabelas tipo, categoria, setor" da
-- casa: "Tipo identifica como o item é tratado na operação"; "Tipo, Categoria e Setor
-- são campos independentes".
--
--   MATERIAL_LIMPEZA → MATERIAL_OPERACIONAL   o consumível da rotina: limpeza, mas
--                                             também descartável, escritório, a copa
--   + PATRIMONIO                              bem durável, controle patrimonial
--   + SERVICO                                 não físico (taxa de entrega); sem estoque
--
-- ⚠️ **Renomear, não criar e migrar.** O tipo é a chave do grupo do CMV
-- (`cmv_grupo_tipos`), e o grupo reclassifica o passado inteiro: trocando a chave no
-- mesmo lugar, todo mês já apurado continua idêntico — o material de limpeza de
-- setembro continua no grupo em que estava, agora com o nome novo.

UPDATE produtos   SET tipo = 'MATERIAL_OPERACIONAL' WHERE tipo = 'MATERIAL_LIMPEZA';
UPDATE categorias SET tipo = 'MATERIAL_OPERACIONAL' WHERE tipo = 'MATERIAL_LIMPEZA';
-- `tipo` é a chave primária: só renomeia se o novo ainda não estiver em grupo nenhum.
UPDATE cmv_grupo_tipos SET tipo = 'MATERIAL_OPERACIONAL'
 WHERE tipo = 'MATERIAL_LIMPEZA'
   AND NOT EXISTS (SELECT 1 FROM cmv_grupo_tipos WHERE tipo = 'MATERIAL_OPERACIONAL');
DELETE FROM cmv_grupo_tipos WHERE tipo = 'MATERIAL_LIMPEZA';
-- O inventário guarda o recorte com que foi aberto; o de ontem continua legível.
UPDATE inventarios
   SET filtro_tipos = array_replace(filtro_tipos, 'MATERIAL_LIMPEZA', 'MATERIAL_OPERACIONAL')
 WHERE 'MATERIAL_LIMPEZA' = ANY(filtro_tipos);

-- ⚠️ Serviço não movimenta estoque físico (nenhum existe ainda; a guarda é para
-- quem rodar isto depois de criar algum por fora da tela).
UPDATE produtos SET controla_estoque = false WHERE tipo = 'SERVICO' AND controla_estoque;

-- ------------------------------------------------------- grupo do CMV
-- 🔑 **Patrimônio e serviço nascem FORA do CMV real**, como utensílio e material de
-- limpeza: batedeira nova e taxa de entrega não são custo do prato, e o food cost é
-- o percentual que vira decisão de cardápio. Nenhum produto tem estes tipos ainda,
-- então nada no passado muda.
-- ⚠️ A mesma guarda da 037: o grupo não ressuscita se a casa o apagar, e o tipo que
-- alguém já pôs noutro grupo fica onde está.
INSERT INTO cmv_grupos (nome, ordem, considerar_no_cmv)
SELECT 'Patrimônio e serviços', 30, false
 WHERE NOT EXISTS (SELECT 1 FROM cmv_grupos WHERE lower(nome) = 'patrimônio e serviços')
   AND NOT EXISTS (SELECT 1 FROM cmv_grupo_tipos WHERE tipo IN ('PATRIMONIO', 'SERVICO'));

INSERT INTO cmv_grupo_tipos (tipo, id_grupo)
SELECT t.tipo, g.id
  FROM cmv_grupos g
  CROSS JOIN (VALUES ('PATRIMONIO'), ('SERVICO')) AS t(tipo)
 WHERE lower(g.nome) = 'patrimônio e serviços'
ON CONFLICT (tipo) DO NOTHING;

-- ------------------------------------------------------- categoria
-- 🔑 **O tipo da categoria passa a ser opcional.** Nunca filtrou nada — era rótulo —,
-- e a lista nova da casa tem categoria que serve a vários tipos (KITS E CESTAS, OUTROS).
ALTER TABLE categorias ALTER COLUMN tipo DROP NOT NULL;
ALTER TABLE categorias ALTER COLUMN tipo DROP DEFAULT;

COMMENT ON COLUMN produtos.tipo IS
    'INSUMO|REVENDA|PRODUZIDO|KIT|EMBALAGEM|MATERIAL_OPERACIONAL|UTENSILIO|PATRIMONIO|SERVICO. '
    'A lista viva é TIPOS, em api/models/produtos.py — não há CHECK aqui de '
    'propósito: tipo novo é migração de dado, não alteração de tabela.';

COMMENT ON COLUMN categorias.tipo IS
    'Opcional (131). Quando preenchido, um dos TIPOS de api/models/produtos.py.';

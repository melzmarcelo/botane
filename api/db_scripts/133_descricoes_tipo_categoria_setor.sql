-- 133 — Descrição de tipo, categoria e setor (pedido do dono, 25/10/2026).
--
-- No cadastro do produto, passar o mouse no Tipo, na Categoria e no Setor mostra o que
-- cada um quer dizer: o USO OPERACIONAL do tipo, os EXEMPLOS / ABRANGÊNCIA da categoria e
-- o USO PREVISTO do setor — as três colunas do documento "Tabelas tipo/categoria/setor".
-- O texto é editado em Tabelas de apoio ▸ Descrições.
--
-- ⚠️ O TIPO é fixo do sistema (models/produtos.py), mas a explicação dele é da casa:
-- por isso uma tabela só de descrição, chaveada pelo código do tipo, e não uma tabela
-- de tipos — quem manda na lista continua sendo o código.
-- ⚠️ Idempotente: a carga inicial só preenche o que está EM BRANCO, então rodar de novo
-- não desfaz o que alguém editou na tela.

ALTER TABLE categorias ADD COLUMN IF NOT EXISTS descricao text;
ALTER TABLE setores    ADD COLUMN IF NOT EXISTS descricao text;

CREATE TABLE IF NOT EXISTS tipos_produto_descricao (
    tipo          varchar(30) PRIMARY KEY,
    descricao     text,
    atualizado_em timestamptz NOT NULL DEFAULT now()
);

-- Tipos: a coluna "Uso operacional" do documento.
INSERT INTO tipos_produto_descricao (tipo, descricao) VALUES
    ('INSUMO', 'Ingrediente ou matéria-prima utilizada na produção de alimentos e bebidas.'),
    ('PRODUZIDO', 'Produto preparado ou fabricado internamente, vendido ou utilizado em outra preparação.'),
    ('REVENDA', 'Produto adquirido pronto para comercialização.'),
    ('KIT', 'Conjunto comercializado como uma única oferta, com componentes identificáveis.'),
    ('EMBALAGEM', 'Embalagem usada para acondicionar, transportar ou apresentar produtos.'),
    ('MATERIAL_OPERACIONAL', 'Material consumível utilizado na rotina da empresa. Fica fora do custo dos produtos.'),
    ('UTENSILIO', 'Item reutilizável utilizado no preparo, armazenamento ou serviço.'),
    ('PATRIMONIO', 'Bem durável sujeito a controle patrimonial, conforme política da empresa. Ex.: processadores, batedeiras.'),
    ('SERVICO', 'Serviço ou item não físico cadastrado para controle, quando aplicável. Não movimenta estoque físico.')
ON CONFLICT (tipo) DO NOTHING;

-- Categorias: a coluna "Exemplos / abrangência", casada pelo nome (sem caixa).
UPDATE categorias c
   SET descricao = d.descricao
  FROM (VALUES
    ('HORTIFRÚTI', 'Abacate, abacaxi, brócolis, limão, maracujá e ervas frescas (somente itens frescos).'),
    ('FRUTAS CONGELADAS E POLPAS', 'Frutas vermelhas congeladas, manga congelada, açaí e polpas de fruta.'),
    ('CARNES, AVES E PEIXES', 'Filé mignon, costela, salmão, pato e demais carnes e pescados.'),
    ('FRIOS E EMBUTIDOS', 'Bacon, salame, pastrami, copa lombo e embutidos.'),
    ('LATICÍNIOS E QUEIJOS', 'Cream cheese, burrata, nata, leite, manteiga e queijos.'),
    ('MERCEARIA SECA E INGREDIENTES', 'Farinhas, açúcares, amido, aveia, grãos e conservas.'),
    ('CHOCOLATES E CONFEITARIA', 'Cacau, chocolate em gotas, corantes, glucose e confeitos.'),
    ('TEMPEROS E CONDIMENTOS', 'Canela, açafrão, pimentas, especiarias e condimentos.'),
    ('OVOS', 'Ovos, gemas e claras, inclusive quando comprados separadamente.'),
    ('ÓLEOS E GORDURAS', 'Azeites, óleos e gorduras culinárias.'),
    ('INSUMOS DE BAR E BEBIDAS', 'Aperol, bitters, xaropes, gelo e ingredientes para drinks.'),
    ('CAFÉS E CHÁS — INSUMOS', 'Café e folhas de chá utilizados no preparo.'),
    ('BASES E PRÉ-PREPAROS', 'Caldo de legumes, molho de tomate, base de gnocchi e outras preparações intermediárias.'),
    ('PRODUTOS DE PANIFICAÇÃO', 'Pães, croissants e outros produtos de panificação.'),
    ('DOCES, BOLOS E SOBREMESAS', 'Brownies, cookies, schneckes, bolos, tortas e sobremesas.'),
    ('SALGADOS', 'Brezel, quiches, folhados e salgados assados.'),
    ('PRATOS PREPARADOS', 'Egg Benedict, tostas, strogonoff, gnocchi e outras refeições.'),
    ('BEBIDAS PREPARADAS', 'Cafés, chás servidos, sucos naturais, drinks e bebidas feitas na casa.'),
    ('BEBIDAS PRONTAS PARA REVENDA', 'Águas, refrigerantes, kombuchas e sucos na embalagem original.'),
    ('VINHOS E ESPUMANTES', 'Vinhos e espumantes vendidos em garrafa ou taça.'),
    ('CERVEJAS E DESTILADOS', 'Cervejas, destilados e outras bebidas alcoólicas vendidas em garrafa ou dose.'),
    ('ALIMENTOS EMBALADOS PARA REVENDA', 'Granola, geleias, conservas e outros alimentos prontos para levar.'),
    ('CAFÉS E CHÁS PARA REVENDA', 'Cafés embalados e chás para consumo doméstico.'),
    ('PRESENTES, LOUÇAS E ACESSÓRIOS', 'Canecas, bules, buquês, sacolas e artigos vendidos na loja.'),
    ('KITS E CESTAS', 'Cestas de café e conjuntos comercializados como uma única oferta.'),
    ('EMBALAGENS', 'Caixas, sacolas, saquinhos, etiquetas e lacres.'),
    ('DESCARTÁVEIS E MATERIAL DE CONSUMO', 'Copos, canudos, guardanapos, filme PVC, papel alumínio, papel manteiga, sacos de confeitar e outros itens de uso único.'),
    ('LIMPEZA E HIGIENE', 'Água sanitária, detergentes, desinfetantes, álcool 70% e papel-toalha.'),
    ('UNIFORMES E EPIS', 'Dólmãs, aventais, toucas, calçados ocupacionais e equipamentos de proteção.'),
    ('MATERIAL DE ESCRITÓRIO E TI', 'Bobinas térmicas, papel A4, cabos, pilhas e suprimentos de informática.'),
    ('UTENSÍLIOS', 'Espátulas, aros, bicos de inox e recipientes reutilizáveis.'),
    ('GASES E COMBUSTÍVEIS', 'Gás de cozinha (GLP), cilindro de CO₂ para água com gás, cápsulas de N₂O para sifão, gás de maçarico e gel combustível para rechaud.'),
    ('EQUIPAMENTOS', 'Adegas, cervejeiras, vitrines refrigeradas, batedeiras e máquinas.'),
    ('MOBILIÁRIO', 'Mesas, bancos, cadeiras, estantes e móveis.'),
    ('SERVIÇOS', 'Taxas de entrega e serviços cadastrados, quando aplicável.'),
    ('OUTROS', 'Categoria temporária para exceções, com revisão periódica.')
  ) AS d(nome, descricao)
 WHERE upper(c.nome) = upper(d.nome)
   AND (c.descricao IS NULL OR c.descricao = '');

-- Setores: a coluna "Uso previsto".
UPDATE setores s
   SET descricao = d.descricao
  FROM (VALUES
    ('BAR', 'Bebidas, insumos de bar e preparo de cafés, chás, sucos e drinks.'),
    ('COZINHA', 'Ingredientes, pré-preparos e pratos da cozinha.'),
    ('CONFEITARIA', 'Ingredientes, bases e produtos da confeitaria e panificação.'),
    ('SALÃO / ATENDIMENTO / MERCEARIA', 'Vitrine, produtos de revenda, presentes, kits, utensílios e descartáveis de serviço.'),
    ('ALMOXARIFADO', 'Recebimento de mercadorias e guarda central: embalagens, descartáveis, limpeza, uniformes e EPIs.'),
    ('ADMINISTRATIVO', 'Material de escritório, bobinas e suprimentos de informática.')
  ) AS d(nome, descricao)
 WHERE upper(s.nome) = upper(d.nome)
   AND (s.descricao IS NULL OR s.descricao = '');

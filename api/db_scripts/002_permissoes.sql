-- Botane 002 — chaves de permissão e papéis de fábrica.
-- Idempotente. Os papéis de fábrica (sistema = true) são REDEFINIDOS a cada
-- execução: eles não são editáveis na tela, quem quiser variação copia o papel.

INSERT INTO permissoes (chave, modulo, descricao, ordem) VALUES
    ('admin.empresa',            'Administração', 'Editar os dados da empresa', 10),
    ('admin.unidades',           'Administração', 'Cadastrar lojas e seus parâmetros', 20),
    ('admin.usuarios',           'Administração', 'Criar e editar usuários', 30),
    ('admin.papeis',             'Administração', 'Criar papéis e definir permissões', 40),
    ('admin.auditoria',          'Administração', 'Ver o histórico de alterações', 50),
    ('admin.integracoes',        'Administração', 'Configurar credenciais de integração', 60),

    ('cadastros.produtos',       'Cadastros',     'Produtos e insumos', 110),
    ('cadastros.categorias',     'Cadastros',     'Categorias', 120),
    ('cadastros.setores',        'Cadastros',     'Setores', 130),
    ('cadastros.locais',         'Cadastros',     'Locais de estoque', 140),
    ('cadastros.fornecedores',   'Cadastros',     'Fornecedores', 150),
    ('cadastros.unidades_medida','Cadastros',     'Unidades de medida e conversões', 160),

    ('fichas.visualizar',        'Fichas',        'Ver fichas técnicas', 210),
    ('fichas.editar',            'Fichas',        'Criar e alterar fichas', 220),
    ('fichas.homologar',         'Fichas',        'Homologar uma versão de ficha', 230),
    ('fichas.custos',            'Fichas',        'Ver o custo dentro da ficha', 240),

    ('estoque.saldos',           'Estoque',       'Consultar saldos e movimentos', 310),
    ('estoque.entradas',         'Estoque',       'Lançar entrada', 320),
    ('estoque.saidas',           'Estoque',       'Lançar saída e produção', 330),
    ('estoque.perdas',           'Estoque',       'Apontar perda, quebra e cortesia', 340),
    ('estoque.transferencias',   'Estoque',       'Transferir entre locais', 350),
    ('estoque.inventario',       'Estoque',       'Contar e fechar inventário', 360),
    ('estoque.ajuste',           'Estoque',       'Ajustar saldo fora do inventário', 370),
    ('estoque.retroativo',       'Estoque',       'Lançar em data já fechada', 380),

    ('compras.notas',            'Compras',       'Ver notas de entrada', 410),
    ('compras.conciliar',        'Compras',       'Vincular item da nota a produto', 420),
    ('compras.lancar',           'Compras',       'Lançar a nota no estoque', 430),

    ('cmv.painel',               'CMV',           'Ver o painel de CMV', 510),
    ('cmv.relatorios',           'CMV',           'Ver relatórios e exportar', 520),
    ('cmv.fechamento',           'CMV',           'Fechar o período', 530),
    ('cmv.reabrir',              'CMV',           'Reabrir período fechado', 540),

    ('integracao.omie',          'Integrações',   'Sincronizar e conciliar o Omie', 610),
    ('integracao.pdv',           'Integrações',   'Sincronizar as vendas do PDV', 620)
ON CONFLICT (chave) DO UPDATE
    SET modulo = EXCLUDED.modulo,
        descricao = EXCLUDED.descricao,
        ordem = EXCLUDED.ordem;

-- ---------------------------------------------------------------- papéis

INSERT INTO papeis (nome, descricao, sistema) VALUES
    ('Administrador',        'O dono. Acesso a tudo, inclusive empresa, usuários e reabertura de período.', true),
    ('Gerente',              'Toca a loja inteira; não mexe em usuários nem reabre período fechado.', true),
    ('Cozinha',              'Cozinheiras: fichas técnicas sem ver custo, produção e apontamento de perda.', true),
    ('Conferente / Estoque', 'Recebimento, entradas, inventário e conciliação de notas.', true),
    ('Salão',                'Garçons: consulta a ficha e aponta cortesia e quebra do salão.', true),
    ('Contador',             'Escritório contábil: leitura do CMV, das notas e dos relatórios.', true)
ON CONFLICT (nome) DO UPDATE
    SET descricao = EXCLUDED.descricao, sistema = EXCLUDED.sistema;

-- Redefine o conjunto dos papéis de fábrica (só deles).
DELETE FROM papel_permissoes
 WHERE id_papel IN (SELECT id FROM papeis WHERE sistema);

-- Administrador: tudo.
INSERT INTO papel_permissoes (id_papel, chave)
SELECT p.id, x.chave FROM papeis p CROSS JOIN permissoes x
 WHERE p.nome = 'Administrador';

-- Gerente: tudo menos administração e reabrir período.
INSERT INTO papel_permissoes (id_papel, chave)
SELECT p.id, x.chave FROM papeis p CROSS JOIN permissoes x
 WHERE p.nome = 'Gerente'
   AND x.modulo <> 'Administração'
   AND x.chave <> 'cmv.reabrir';

INSERT INTO papel_permissoes (id_papel, chave)
SELECT p.id, x.chave FROM papeis p CROSS JOIN permissoes x
 WHERE p.nome = 'Cozinha'
   AND x.chave IN ('fichas.visualizar','fichas.editar',
                   'estoque.saldos','estoque.saidas','estoque.perdas');

INSERT INTO papel_permissoes (id_papel, chave)
SELECT p.id, x.chave FROM papeis p CROSS JOIN permissoes x
 WHERE p.nome = 'Conferente / Estoque'
   AND x.chave IN ('cadastros.produtos','cadastros.fornecedores','fichas.visualizar',
                   'estoque.saldos','estoque.entradas','estoque.saidas','estoque.perdas',
                   'estoque.transferencias','estoque.inventario',
                   'compras.notas','compras.conciliar','compras.lancar',
                   'integracao.omie');

INSERT INTO papel_permissoes (id_papel, chave)
SELECT p.id, x.chave FROM papeis p CROSS JOIN permissoes x
 WHERE p.nome = 'Salão'
   AND x.chave IN ('fichas.visualizar','estoque.saldos','estoque.perdas');

-- Contador vê o custo (é o trabalho dele) mas não lança nada.
INSERT INTO papel_permissoes (id_papel, chave)
SELECT p.id, x.chave FROM papeis p CROSS JOIN permissoes x
 WHERE p.nome = 'Contador'
   AND x.chave IN ('cmv.painel','cmv.relatorios','compras.notas',
                   'estoque.saldos','fichas.visualizar','fichas.custos');

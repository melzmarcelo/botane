-- 149 — O Estúdio BI: os relatórios personalizados e quem os vê. Idempotente.
--
-- 🔑 **Pedido do dono (05/11/2026), fase 4 do layout novo:** *"um menu estilo BI, onde o usuário
-- administrador pode criar relatórios personalizados com suas ligações configuráveis"*.
-- Protótipo aprovado em `apresentacao/novo-layout/`.
--
-- ⚠️ **A definição guarda ESCOLHAS, nunca SQL.** `definicao` tem as fontes, as ligações, a
-- dimensão, as medidas e os filtros pelos NOMES da lista branca de `services/bi.py`; quem monta
-- a consulta é sempre o servidor, na hora de rodar. Um relatório salvo com uma fonte que deixou
-- de existir simplesmente deixa de rodar — não executa nada que não esteja na lista.
-- ⚠️ Quem vê: `visibilidade` = EU (só quem criou), TODOS (quem tem `relatorios.personalizados`)
-- ou PAPEIS (os papéis de `papeis_vistos`). Quem tem `bi.estudio` vê e edita todos.

CREATE TABLE IF NOT EXISTS bi_relatorios (
    id             serial PRIMARY KEY,
    nome           varchar(120) NOT NULL,
    definicao      jsonb        NOT NULL,
    visibilidade   varchar(10)  NOT NULL DEFAULT 'EU'
                   CHECK (visibilidade IN ('EU', 'TODOS', 'PAPEIS')),
    papeis_vistos  integer[]    NOT NULL DEFAULT '{}',
    no_menu        boolean      NOT NULL DEFAULT true,
    criado_por     integer      REFERENCES usuarios(id) ON DELETE SET NULL,
    criado_em      timestamptz  NOT NULL DEFAULT now(),
    atualizado_em  timestamptz  NOT NULL DEFAULT now(),
    ativo          boolean      NOT NULL DEFAULT true
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_bi_relatorios_nome
    ON bi_relatorios (lower(nome)) WHERE ativo;

COMMENT ON TABLE bi_relatorios IS
    'Relatórios personalizados do Estúdio BI (149). A definição guarda as escolhas pelos nomes da '
    'lista branca de services/bi.py; o SQL é montado pelo servidor a cada execução.';

INSERT INTO permissoes (chave, modulo, descricao, ordem) VALUES
    ('bi.estudio', 'Relatórios',
     'Criar, editar e publicar relatórios personalizados no Estúdio BI (fontes, ligações e campos)', 905),
    ('relatorios.personalizados', 'Relatórios',
     'Ver os relatórios personalizados publicados para todos', 906)
ON CONFLICT (chave) DO UPDATE
    SET modulo = EXCLUDED.modulo, descricao = EXCLUDED.descricao, ordem = EXCLUDED.ordem;

-- ⚠️ Concedido AQUI (ver 091). Criar é do Administrador (o pedido diz "o usuário administrador");
-- ver os publicados para todos, também da gerência.
INSERT INTO papel_permissoes (id_papel, chave)
SELECT p.id, 'bi.estudio' FROM papeis p WHERE p.sistema AND p.nome = 'Administrador'
ON CONFLICT DO NOTHING;
INSERT INTO papel_permissoes (id_papel, chave)
SELECT p.id, 'relatorios.personalizados' FROM papeis p WHERE p.sistema AND p.nome IN ('Administrador', 'Gerente')
ON CONFLICT DO NOTHING;

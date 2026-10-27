-- 139 — Patrimônio: o cadastro dos BENS (um registro por item físico) e a manutenção.
-- Idempotente.
--
-- 🔑 **Pedido do dono (27/10/2026):** *"Agora que temos o tipo de produto Patrimônio,
-- gostaria de um processo para inventariar o patrimônio"*, com a planilha da casa
-- `Inventario_Equipamentos_Botane.xlsx` (uma aba por setor: código, equipamento, local,
-- marca, modelo, série, tensão, compra, garantia, assistência, criticidade, situação e a
-- preventiva). Da proposta, *"pode seguir com as etapas 1 e 2"*: cadastro com plaqueta e
-- importação da planilha (1) e a manutenção com plano, histórico e alertas (2). A
-- conferência patrimonial pelo QR (3) e a ligação com as notas (4) ficaram para depois.
--
-- 🔑 **Patrimônio NÃO é estoque.** O produto do tipo PATRIMONIO conta QUANTIDADE por local
-- e custo médio; a batedeira tem série, garantia, estado e história PRÓPRIOS. Por isso um
-- registro por item, com o produto como "modelo" opcional. O razão não é tocado aqui.

CREATE SEQUENCE IF NOT EXISTS bens_codigo_seq;

CREATE TABLE IF NOT EXISTS bens (
    id                  serial PRIMARY KEY,
    -- 🔑 **O código da PLAQUETA é fixo e não diz o setor** (PAT-0001). A planilha usava
    -- ADM-01, BAR-02: quando o bem muda de setor, um código desses mente ou precisa
    -- mudar — e a plaqueta colada no equipamento perde o sentido.
    codigo              varchar(12) NOT NULL,
    -- O código que a casa já usava (o da planilha, BAR-02). É por ele que a importação
    -- reconhece a linha na segunda vez.
    apelido             varchar(20),
    id_unidade          integer NOT NULL REFERENCES unidades(id),
    descricao           varchar(120) NOT NULL,
    -- O "modelo": o produto do tipo Patrimônio, quando existir. Opcional.
    id_produto          integer REFERENCES produtos(id) ON DELETE SET NULL,
    id_setor            integer REFERENCES setores(id) ON DELETE SET NULL,
    -- 🔑 Onde está — e, na câmara fria, o PRÓPRIO local de estoque: o equipamento parado
    -- avisa quanto de estoque está dentro dele.
    id_local            integer REFERENCES locais_estoque(id) ON DELETE SET NULL,
    marca               varchar(60),
    modelo              varchar(60),
    numero_serie        varchar(60),
    tensao              varchar(5) CHECK (tensao IN ('110V', '220V', '380V', 'GAS', 'NA')),
    data_compra         date,
    valor_compra        numeric(14,2) CHECK (valor_compra >= 0),
    fornecedor          varchar(120),
    nota_fiscal         varchar(40),
    garantia_ate        date,
    assistencia         varchar(120),
    assistencia_contato varchar(80),
    criticidade         varchar(5) CHECK (criticidade IN ('ALTA', 'MEDIA', 'BAIXA')),
    -- ⚠️ `A_CONFIRMAR` é a "Sugestão" da planilha: o equipamento comum em cafeteria que
    -- ninguém conferiu ainda se existe. Não entra nos alertas.
    situacao            varchar(14) NOT NULL DEFAULT 'EM_USO'
                        CHECK (situacao IN ('A_CONFIRMAR', 'EM_USO', 'EM_MANUTENCAO', 'PARADO',
                                            'DESATIVADO', 'BAIXADO')),
    motivo_baixa        varchar(200),
    -- 🔑 A próxima preventiva é CALCULADA (última + intervalo), nunca gravada: gravada,
    -- ela mentiria no dia em que alguém corrigisse o intervalo.
    preventiva_meses    smallint CHECK (preventiva_meses BETWEEN 1 AND 120),
    ultima_preventiva   date,
    observacao          varchar(500),
    criado_em           timestamptz NOT NULL DEFAULT now(),
    criado_por          integer REFERENCES usuarios(id),
    atualizado_em       timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_bem_codigo ON bens (codigo);
CREATE UNIQUE INDEX IF NOT EXISTS ux_bem_apelido ON bens (id_unidade, lower(apelido))
    WHERE apelido IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_bem_unidade ON bens (id_unidade, situacao);

-- O histórico do bem: o que se fez nele, quando, por quem e quanto custou.
-- ⚠️ Não é razão (não há estoque aqui): um registro errado se apaga.
CREATE TABLE IF NOT EXISTS bem_manutencoes (
    id             serial PRIMARY KEY,
    id_bem         integer NOT NULL REFERENCES bens(id) ON DELETE CASCADE,
    tipo           varchar(10) NOT NULL CHECK (tipo IN ('PREVENTIVA', 'CORRETIVA')),
    data           date NOT NULL,
    executado_por  varchar(120),
    custo          numeric(14,2) CHECK (custo >= 0),
    descricao      varchar(500),
    id_usuario     integer REFERENCES usuarios(id),
    criado_em      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_bem_manutencao ON bem_manutencoes (id_bem, data DESC);

INSERT INTO permissoes (chave, modulo, descricao, ordem) VALUES
    ('patrimonio.ver',        'Patrimônio', 'Ver os bens, a manutenção e os relatórios', 740),
    ('patrimonio.cadastrar',  'Patrimônio', 'Cadastrar e importar bens, imprimir plaquetas e dar baixa', 745),
    ('patrimonio.manutencao', 'Patrimônio', 'Registrar preventiva e corretiva', 750)
ON CONFLICT (chave) DO UPDATE
    SET modulo = EXCLUDED.modulo, descricao = EXCLUDED.descricao, ordem = EXCLUDED.ordem;

-- ⚠️ Concedido AQUI (ver 091): a 002 redefine os papéis de sistema antes desta.
-- Quem toca a loja e quem confere o estoque cadastra; a cozinha e o salão, que são quem
-- vê o equipamento parar, consultam e registram a visita do técnico.
INSERT INTO papel_permissoes (id_papel, chave)
SELECT p.id, x.chave
  FROM papeis p CROSS JOIN permissoes x
 WHERE p.sistema AND x.chave LIKE 'patrimonio.%'
   AND (p.nome IN ('Administrador', 'Gerente', 'Conferente / Estoque')
        OR (p.nome IN ('Cozinha', 'Salão')
            AND x.chave IN ('patrimonio.ver', 'patrimonio.manutencao'))
        OR (p.nome = 'Contador' AND x.chave = 'patrimonio.ver'))
ON CONFLICT DO NOTHING;

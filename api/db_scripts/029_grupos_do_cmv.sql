-- Botané 029 — tipo "material de limpeza" e grupos do CMV por tipo. Idempotente.
--
-- O CMV já mostrava Perdas, Consumo interno e Ajustes de inventário como linhas
-- que EXPLICAM o número. Faltava a pergunta que o dono faz olhando a nota do mês:
-- quanto disto não é comida? Detergente, sacola e marmita entram no custo pela
-- mesma porta dos insumos e somem no total.
--
-- Agora a casa monta os próprios grupos, escolhendo os tipos de produto que
-- entram em cada um.
--
-- ⚠️ **Um tipo só pode estar em UM grupo**, e quem garante isso é o banco: o
-- `tipo` é a CHAVE PRIMÁRIA de `cmv_grupo_tipos`. Conferir na aplicação deixaria
-- passar duas telas gravando ao mesmo tempo — e o mesmo custo apareceria em dois
-- grupos, com a soma dos grupos deixando de fechar com o CMV.

CREATE TABLE IF NOT EXISTS cmv_grupos (
    id        serial PRIMARY KEY,
    nome      varchar(60) NOT NULL,
    ordem     smallint NOT NULL DEFAULT 0,
    ativo     boolean NOT NULL DEFAULT true,
    criado_em timestamptz NOT NULL DEFAULT now()
);
-- Nome repetido devolveria dois grupos iguais na tela do CMV.
CREATE UNIQUE INDEX IF NOT EXISTS ux_cmv_grupo_nome ON cmv_grupos (lower(nome));

CREATE TABLE IF NOT EXISTS cmv_grupo_tipos (
    tipo     varchar(20) PRIMARY KEY,
    id_grupo integer NOT NULL REFERENCES cmv_grupos(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_cmv_grupo_tipos_grupo ON cmv_grupo_tipos (id_grupo);

-- ⚠️ O grupo de exemplo é o que o dono descreveu, e nasce com os dois tipos
-- dele. Sem nenhum grupo a funcionalidade existiria sem aparecer — e ninguém
-- procura uma tela cujo efeito nunca viu. É editável e apagável como qualquer
-- outro; o `ON CONFLICT DO NOTHING` impede que reapareça depois de apagado.
INSERT INTO cmv_grupos (nome, ordem)
SELECT 'Material de limpeza e embalagem', 10
 WHERE NOT EXISTS (SELECT 1 FROM cmv_grupos);

INSERT INTO cmv_grupo_tipos (tipo, id_grupo)
SELECT t.tipo, g.id
  FROM cmv_grupos g
  CROSS JOIN (VALUES ('EMBALAGEM'), ('MATERIAL_LIMPEZA')) AS t(tipo)
 WHERE lower(g.nome) = 'material de limpeza e embalagem'
ON CONFLICT (tipo) DO NOTHING;

-- ---------------------------------------------------------------- permissão
-- Ver o CMV e decidir como ele se agrupa são coisas diferentes: o contador tem
-- `cmv.painel` e não deve remontar a apuração da casa.
INSERT INTO permissoes (chave, modulo, descricao, ordem)
VALUES ('cmv.grupos', 'CMV', 'Configurar os grupos do CMV', 550)
ON CONFLICT (chave) DO UPDATE
    SET modulo = EXCLUDED.modulo, descricao = EXCLUDED.descricao;

-- ⚠️ O script 002 já rodou e não roda de novo (o `db_updater` guarda o
-- checksum), então o papel de fábrica não recebe a chave nova sozinho. Aqui vai
-- a mesma regra que ele aplica: Administrador tem tudo, Gerente tem tudo menos
-- administração e reabrir período.
INSERT INTO papel_permissoes (id_papel, chave)
SELECT p.id, 'cmv.grupos' FROM papeis p
 WHERE p.sistema AND p.nome IN ('Administrador', 'Gerente')
ON CONFLICT DO NOTHING;

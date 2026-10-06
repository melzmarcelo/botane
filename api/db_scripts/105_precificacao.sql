-- 105 — Precificação: a configuração de cada loja. Idempotente.
--
-- 🔑 **Pedido do dono (05/10/2026)**, estudo em `docs/precificacao-estudo.md`. A
-- tela de Preços (só leitura) já existia; esta migração traz o que a
-- Configuração e a Precificação precisam guardar.
--
-- Decisões do dono que este desenho carrega:
--   1. A configuração é POR LOJA, e uma loja pode SEGUIR a de outra — aí, nela,
--      a tela é só de consulta.
--   2. Cada linha (imposto, cartão, custo operacional, o que a casa criar) vale
--      para TUDO, para uma CATEGORIA ou para um SETOR.
--   3. O preço aplicado vale na hora; se vai ao PDV, quem decide é o parâmetro
--      de envio que a loja já tem (`integracoes.enviar_ao_pdv`).

CREATE TABLE IF NOT EXISTS precificacao_config (
    id_unidade        integer PRIMARY KEY REFERENCES unidades(id) ON DELETE CASCADE,
    -- Nula: a configuração é DESTA loja. Preenchida: esta loja segue a de outra.
    id_unidade_origem integer REFERENCES unidades(id),
    -- Como o preço sugerido é arredondado — sempre PARA CIMA, senão a sugestão
    -- entrega a margem que acabou de calcular.
    arredondamento    varchar(10) NOT NULL DEFAULT 'NOVENTA'
                      CHECK (arredondamento IN ('NOVENTA', 'MEIO', 'NENHUM')),
    atualizado_por    integer REFERENCES usuarios(id),
    atualizado_em     timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_precificacao_nao_segue_a_si CHECK (id_unidade_origem IS DISTINCT FROM id_unidade)
);

-- ⚠️ **Uma tabela só para as três famílias de linha**, e não três tabelas:
--   PERCENTUAL — sai de cada real vendido (imposto, cartão, operacional…);
--   VALOR      — reais por unidade vendida (embalagem de viagem, sachê);
--   MARGEM     — o que a casa quer que sobre, também em % da venda.
-- As três têm o mesmo alcance (tudo, categoria, setor) e a mesma regra de
-- precedência: a linha MAIS ESPECÍFICA de mesmo nome substitui a geral. Três
-- tabelas seriam três cópias dessa regra.
CREATE TABLE IF NOT EXISTS precificacao_linhas (
    id           serial PRIMARY KEY,
    id_unidade   integer NOT NULL REFERENCES unidades(id) ON DELETE CASCADE,
    nome         varchar(80) NOT NULL,
    tipo         varchar(12) NOT NULL CHECK (tipo IN ('PERCENTUAL', 'VALOR', 'MARGEM')),
    -- Percentual (0 a 100) ou reais por unidade. Nunca float.
    valor        numeric(12,4) NOT NULL CHECK (valor >= 0),
    alcance      varchar(10) NOT NULL DEFAULT 'TUDO'
                 CHECK (alcance IN ('TUDO', 'CATEGORIA', 'SETOR')),
    id_categoria integer REFERENCES categorias(id) ON DELETE CASCADE,
    id_setor     integer REFERENCES setores(id) ON DELETE CASCADE,
    ordem        smallint NOT NULL DEFAULT 0,
    CONSTRAINT ck_precificacao_alcance CHECK (
        (alcance = 'TUDO'      AND id_categoria IS NULL     AND id_setor IS NULL) OR
        (alcance = 'CATEGORIA' AND id_categoria IS NOT NULL AND id_setor IS NULL) OR
        (alcance = 'SETOR'     AND id_setor IS NOT NULL     AND id_categoria IS NULL)),
    CONSTRAINT ck_precificacao_percentual CHECK (tipo = 'VALOR' OR valor < 100)
);

-- A mesma linha não se repete para o mesmo alcance: duas "Impostos" para tudo
-- seriam somadas sem ninguém ver por quê.
CREATE UNIQUE INDEX IF NOT EXISTS ux_precificacao_linha
    ON precificacao_linhas (id_unidade, tipo, lower(nome), alcance,
                            coalesce(id_categoria, 0), coalesce(id_setor, 0));

-- ---------------------------------------------------------------- permissões
-- 🔑 Três chaves, porque são três autoridades: quem enxerga a margem de cada
-- prato não é necessariamente quem muda o cardápio, e quem muda o cardápio não
-- é necessariamente quem decide o imposto e a margem da casa.
INSERT INTO permissoes (chave, modulo, descricao, ordem) VALUES
    ('precificacao.analisar',   'Precificação', 'Ver a análise de preços, margens e o preço × custo', 730),
    ('precificacao.aplicar',    'Precificação', 'Aplicar os preços sugeridos nos produtos', 735),
    ('precificacao.configurar', 'Precificação', 'Impostos, taxas, custo operacional e margem da loja', 740)
ON CONFLICT (chave) DO UPDATE
    SET modulo = EXCLUDED.modulo, descricao = EXCLUDED.descricao, ordem = EXCLUDED.ordem;

-- ⚠️ Concedido AQUI (ver 091/100): a 002 redefine os papéis de sistema antes desta.
-- Administrador e Gerente recebem as três. E **quem já via o painel de CMV
-- continua vendo o preço × custo**: a tela nasceu com essa chave, e tirá-la no
-- deploy faria o item sumir do menu de quem a usava ontem.
INSERT INTO papel_permissoes (id_papel, chave)
SELECT p.id, x.chave
  FROM papeis p CROSS JOIN permissoes x
 WHERE p.sistema AND x.chave LIKE 'precificacao.%'
   AND p.nome IN ('Administrador', 'Gerente')
ON CONFLICT DO NOTHING;

INSERT INTO papel_permissoes (id_papel, chave)
SELECT DISTINCT pp.id_papel, 'precificacao.analisar'
  FROM papel_permissoes pp
 WHERE pp.chave = 'cmv.painel'
ON CONFLICT DO NOTHING;

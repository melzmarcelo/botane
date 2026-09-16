-- Os MODOS de rendimento da ficha — e por que o rendimento por prateleira vira um deles.
--
-- 🔑 **Pedido do dono (16/09/2026):** *"no cadastro de ficha posso cadastrar o
-- padrão — o Cookies Flat rende 8,535 KG em 65 porções, a receita toda. E podemos
-- criar mais modos de rendimento para diferentes setores, com um nome, e este
-- será o modo selecionado ao agendar ou produzir. Modo padrão é produzir a
-- receita toda para estoque; podemos ter um Modo Consumo, com o setor Bar e 30
-- porções; ou outro modo onde as porções são menores."*
--
-- 🔑 **O que o modo muda de verdade não é ESCALA, é a PORÇÃO.** Produzir 30 em
-- vez de 65 já funcionava: a quantidade é livre e o consumo é proporcional. O
-- que não existia era a mesma massa render *outra coisa* — os mesmos 8,535 KG em
-- 130 unidades menores. Isso é outro custo unitário e outra contagem de estoque,
-- e por isso merece cadastro com nome.
--
-- ⚠️ **`ficha_locais` VIRA `ficha_modos` — não convive com ela.** A tabela da
-- migração 066 já era um modo sem nome, escolhido por adivinhação a partir da
-- prateleira de destino. Deixar as duas de pé seria duas réguas para a mesma
-- pergunta, e o rendimento DIVIDE o consumo: divergir aí custa ingrediente, não
-- estética. Renomear (em vez de criar tabela nova e copiar) preserva os ids, as
-- chaves estrangeiras e o CASCADE que a ficha já tinha.
--
-- ⚠️ **A ficha continua sendo o Modo padrão, e ele NÃO vira linha.** O
-- rendimento da própria ficha responde quando nenhum modo casa — é como sempre
-- foi, e materializá-lo custaria uma linha por ficha da base para não mudar
-- comportamento nenhum.
--
-- ⚠️ **A unidade do rendimento continua sendo a da FICHA.** Modo é a mesma
-- receita rendendo outra coisa, não outra receita: deixar cada modo declarar a
-- própria unidade abriria a porta para a ficha render em KG e o modo em UN, que
-- é exatamente a ponte que a produção acabou de pagar caro para atravessar.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'ficha_locais')
       AND NOT EXISTS (SELECT 1 FROM information_schema.tables
                        WHERE table_name = 'ficha_modos') THEN
        ALTER TABLE ficha_locais RENAME TO ficha_modos;
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS ficha_modos (
    id              serial PRIMARY KEY,
    id_ficha        integer NOT NULL REFERENCES fichas_tecnicas(id) ON DELETE CASCADE,
    id_local        integer REFERENCES locais_estoque(id),
    rendimento_qtd  numeric(18,4) NOT NULL,
    porcoes         numeric(10,2),
    porcao_qtd      numeric(18,4),
    observacao      varchar(160),
    criado_em       timestamptz NOT NULL DEFAULT now()
);

-- O nome é o que a cozinha escolhe na hora de produzir.
ALTER TABLE ficha_modos ADD COLUMN IF NOT EXISTS nome varchar(60);
-- ⚠️ O modo pode valer para um SETOR inteiro ("Consumo — Bar") em vez de uma
-- prateleira. Os dois são opcionais e os dois são só pré-seleção: quem decide
-- qual modo vale é quem produz, escolhendo na tela.
ALTER TABLE ficha_modos ADD COLUMN IF NOT EXISTS id_setor integer REFERENCES setores(id);
-- A quantidade que se costuma produzir neste modo. É SUGESTÃO: preenche o campo
-- e sai do caminho. Sem ela, escolher "Consumo — Bar" ainda obrigaria a digitar
-- o número toda vez, que é justamente o trabalho que o modo existe para poupar.
ALTER TABLE ficha_modos ADD COLUMN IF NOT EXISTS quantidade_sugerida numeric(18,4);
ALTER TABLE ficha_modos ADD COLUMN IF NOT EXISTS ordem integer NOT NULL DEFAULT 0;
ALTER TABLE ficha_modos ADD COLUMN IF NOT EXISTS ativo boolean NOT NULL DEFAULT true;

-- ⚠️ **Os modos que já existiam nascem com o nome da prateleira deles.** Eram
-- linhas de `ficha_locais`, onde o destino ERA o nome — sem isto a tela mostraria
-- uma lista de modos sem nome, e ninguém saberia qual escolher.
UPDATE ficha_modos m
   SET nome = coalesce(l.nome, 'Modo ' || m.id)
  FROM locais_estoque l
 WHERE l.id = m.id_local AND (m.nome IS NULL OR m.nome = '');
UPDATE ficha_modos SET nome = 'Modo ' || id WHERE nome IS NULL OR nome = '';

ALTER TABLE ficha_modos ALTER COLUMN nome SET NOT NULL;
-- ⚠️ `id_local` deixa de ser obrigatório: o modo por SETOR não tem prateleira, e
-- o modo geral não tem nenhum dos dois.
ALTER TABLE ficha_modos ALTER COLUMN id_local DROP NOT NULL;

-- ⚠️ **Some o índice único por (ficha, local)**: com modos, a mesma prateleira
-- pode ter "Padrão da vitrine" e "Mini da vitrine" — era o índice que impedia
-- exatamente o que o dono pediu. O que não se repete agora é o NOME, que é por
-- onde a pessoa escolhe: dois modos com o mesmo nome na mesma ficha são uma
-- escolha impossível de fazer certo.
DROP INDEX IF EXISTS ux_ficha_locais;
CREATE UNIQUE INDEX IF NOT EXISTS ux_ficha_modos_nome
    ON ficha_modos (id_ficha, lower(nome));
CREATE INDEX IF NOT EXISTS ix_ficha_modos_ficha ON ficha_modos (id_ficha, ordem, id);

ALTER TABLE ficha_modos DROP CONSTRAINT IF EXISTS ck_ficha_local_rendimento;
ALTER TABLE ficha_modos DROP CONSTRAINT IF EXISTS ck_ficha_local_porcoes;
ALTER TABLE ficha_modos DROP CONSTRAINT IF EXISTS ck_ficha_local_porcao;
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_ficha_modo_rendimento') THEN
        ALTER TABLE ficha_modos ADD CONSTRAINT ck_ficha_modo_rendimento
            CHECK (rendimento_qtd > 0);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_ficha_modo_porcoes') THEN
        ALTER TABLE ficha_modos ADD CONSTRAINT ck_ficha_modo_porcoes
            CHECK (porcoes IS NULL OR porcoes > 0);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_ficha_modo_porcao') THEN
        ALTER TABLE ficha_modos ADD CONSTRAINT ck_ficha_modo_porcao
            CHECK (porcao_qtd IS NULL OR porcao_qtd > 0);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_ficha_modo_sugerida') THEN
        ALTER TABLE ficha_modos ADD CONSTRAINT ck_ficha_modo_sugerida
            CHECK (quantidade_sugerida IS NULL OR quantidade_sugerida > 0);
    END IF;
END $$;

-- 🔑 **A agenda guarda QUAL modo foi planejado.** Sem isto, agendar "Modo mini"
-- e cumprir a linha três dias depois produziria pelo rendimento padrão — a
-- quantidade certa saindo da receita errada, e a diferença só aparecendo na
-- contagem. ⚠️ Nulo é o Modo padrão, que é o que toda linha já agendada quer
-- dizer.
ALTER TABLE producao_agenda ADD COLUMN IF NOT EXISTS id_modo integer
    REFERENCES ficha_modos(id) ON DELETE SET NULL;

-- 🔑 **E a produção guarda o modo que valeu.** `producoes` já congela a versão
-- da ficha pela mesma razão: o número tem de se reproduzir daqui a seis meses,
-- e o rendimento é o que divide o consumo.
ALTER TABLE producoes ADD COLUMN IF NOT EXISTS id_modo integer
    REFERENCES ficha_modos(id) ON DELETE SET NULL;

COMMENT ON TABLE ficha_modos IS
  'Modos de rendimento da ficha: nome, prateleira e/ou setor, quanto a receita '
  'rende naquele formato e em quantas porcoes. Sem modo, vale o rendimento da '
  'propria ficha (o Modo padrao). Migracao 072 — era ficha_locais (066).';
COMMENT ON COLUMN ficha_modos.nome IS
  'O que a cozinha escolhe na hora de produzir: "Padrao", "Consumo - Bar", "Mini".';
COMMENT ON COLUMN ficha_modos.quantidade_sugerida IS
  'Quanto se costuma produzir neste modo, na unidade de estoque do produto. '
  'Sugestao: preenche o campo e sai do caminho.';

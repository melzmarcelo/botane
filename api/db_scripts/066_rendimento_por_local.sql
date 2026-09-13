-- A mesma receita com destinos diferentes — e o local de onde a VENDA baixa.
--
-- 🔑 **Pedido do dono (12/09/2026):** *"a mesma ficha pode ter processos
-- diferentes. Vamos fazer a massa de pizza e estocar para servir como insumo
-- para pizza, mas podemos ter produção de massa de pizza que vai para a vitrine.
-- Podemos criar no produto mais de um local, qual seria o local que o PDV
-- consome. Aí dentro da ficha técnica podemos ter os locais e informar
-- rendimentos e porções por local, e ao programar a produção seleciona qual
-- local será produzido"*. E o rendimento muda de verdade: a da vitrine vai ao
-- forno.
--
-- 🔑 **`id_local_padrao` fazia TRÊS papéis**, e é essa a raiz do problema:
--   1. de onde a VENDA baixa (`routers/vendas.py`);
--   2. o fallback de onde os INSUMOS saem na produção (`_de_onde_sai`);
--   3. o destino padrão da produção e da agenda.
-- Com uma coluna só, pôr a Vitrine como "o local do produto" fazia a receita da
-- pizza comer a massa DA VITRINE. Separar o papel 1 resolve isso.
--
-- ⚠️ **NULO continua sendo a resposta normal**, e é o padrão: sem
-- `id_local_venda`, a venda segue no `id_local_padrao` exatamente como antes.
-- Nenhum dos produtos existentes muda de comportamento — e não há carga
-- retroativa de propósito: copiar o padrão para a coluna nova faria 3.226
-- produtos passarem a AFIRMAR um local de venda que ninguém escolheu.
ALTER TABLE produtos
  ADD COLUMN IF NOT EXISTS id_local_venda integer REFERENCES locais_estoque(id);

CREATE INDEX IF NOT EXISTS ix_produtos_local_venda ON produtos (id_local_venda)
  WHERE id_local_venda IS NOT NULL;

COMMENT ON COLUMN produtos.id_local_venda IS
  'Prateleira de onde a VENDA baixa este produto. Nulo = usa id_local_padrao, '
  'que continua sendo o destino da producao e o fallback do consumo de insumo. '
  'Migracao 066.';

-- 🔑 **O rendimento por prateleira: um OVERRIDE, não uma substituição.**
-- Sem linha aqui, vale o rendimento da própria ficha — que é o caso de todas as
-- 46 fichas de hoje. Com linha, produzir PARA aquele local usa estes números.
--
-- ⚠️ **Isso muda o CONSUMO por unidade produzida** (`lotes = quantidade ÷
-- rendimento`), que é exatamente o pedido: 10 KG de massa para a câmara e 10 KG
-- de massa assada para a vitrine não saem da mesma quantidade de farinha.
--
-- ⚠️ **Uma linha por (ficha, local)** — o índice único é o que impede dois
-- rendimentos para o mesmo destino, que seria a receita com duas verdades.
--
-- ⚠️ **`ON DELETE CASCADE` na ficha**: versão nova de ficha é outra linha em
-- `fichas_tecnicas`, e a cópia carrega os locais junto (`_copiar_ficha`). Ficha
-- que sai leva os destinos dela.
-- ⚠️ **No local, NÃO cascateia**: prateleira não se apaga neste sistema, se
-- inativa. Se um dia se apagar, o erro é melhor que o rendimento pendurado.
CREATE TABLE IF NOT EXISTS ficha_locais (
    id              serial PRIMARY KEY,
    id_ficha        integer NOT NULL REFERENCES fichas_tecnicas(id) ON DELETE CASCADE,
    id_local        integer NOT NULL REFERENCES locais_estoque(id),
    rendimento_qtd  numeric(18,4) NOT NULL,
    porcoes         numeric(10,2),
    porcao_qtd      numeric(18,4),
    observacao      varchar(160),
    criado_em       timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_ficha_local_rendimento CHECK (rendimento_qtd > 0),
    CONSTRAINT ck_ficha_local_porcoes CHECK (porcoes IS NULL OR porcoes > 0),
    CONSTRAINT ck_ficha_local_porcao CHECK (porcao_qtd IS NULL OR porcao_qtd > 0)
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_ficha_locais ON ficha_locais (id_ficha, id_local);

COMMENT ON TABLE ficha_locais IS
  'Rendimento e porcionamento POR prateleira de destino. Override do que esta '
  'na ficha: sem linha, vale a ficha. Migracao 066.';
COMMENT ON COLUMN ficha_locais.rendimento_qtd IS
  'Quanto a receita inteira rende quando produzida PARA este local, na unidade '
  'de estoque do produto. Divide o consumo: lotes = quantidade / rendimento.';

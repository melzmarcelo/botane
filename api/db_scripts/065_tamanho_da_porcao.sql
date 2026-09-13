-- Quanto pesa UMA porção — o que permite fazer a conta nos dois sentidos.
--
-- 🔑 **Pedido do dono (12/09/2026):** *"hoje temos somente a quantidade de
-- porções que rende, mas podemos ter ao contrário: informar os gramas/kg/un e
-- ele calcular quantas porções rende"*. Faltava exatamente este dado: `porcoes`
-- é uma contagem pura ("rende 8"), e de contagem não se deduz tamanho. Com o
-- tamanho, os dois caminhos existem — rendimento ÷ tamanho dá as porções, e
-- rendimento ÷ porções dá o tamanho.
--
-- ⚠️ **NULO é uma resposta**, e é o padrão: quem nunca informou o tamanho não
-- passa a afirmar que a porção tem 1. Nulo quer dizer "ninguém disse", e a tela
-- calcula o tamanho a partir das porções quando ele falta — sem gravar palpite.
--
-- ⚠️ **Na unidade do RENDIMENTO, não numa própria.** Uma ficha que rende 2 KG
-- com porção de 0,25 KG rende 8; a mesma em 2.000 G com porção de 250 G rende as
-- mesmas 8. Guardar uma unidade separada aqui abriria a porta para porção em G
-- numa ficha que rende em L, que é conta que ninguém fecha — e a unidade do
-- rendimento já está gravada ao lado, em `rendimento_um`.
--
-- ⚠️ **Não mexe em `porcoes`.** Ela continua sendo o que divide o custo, e
-- continua gravada: derivá-la em tempo de consulta mudaria o custo por porção de
-- toda ficha existente no instante em que alguém informasse um tamanho.
ALTER TABLE fichas_tecnicas
  ADD COLUMN IF NOT EXISTS porcao_qtd numeric(18,4);

ALTER TABLE fichas_tecnicas
  DROP CONSTRAINT IF EXISTS ck_ficha_porcao_positiva;
ALTER TABLE fichas_tecnicas
  ADD CONSTRAINT ck_ficha_porcao_positiva
  CHECK (porcao_qtd IS NULL OR porcao_qtd > 0);

COMMENT ON COLUMN fichas_tecnicas.porcao_qtd IS
  'Quanto vale UMA porcao, na unidade de rendimento_um. Nulo = ninguem '
  'informou, e a tela deriva de rendimento_qtd/porcoes sem gravar. Migracao 065.';

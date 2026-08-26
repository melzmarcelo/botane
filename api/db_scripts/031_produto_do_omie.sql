-- Botané 031 — o cadastro do produto aproveita mais do que o Omie já tem.
-- Idempotente.
--
-- A conta real do cliente tem 2.189 produtos importados. Todos com NCM, 1.149
-- com EAN — e **zero com categoria ou setor**, que é o que o CMV por grupo e a
-- curva ABC precisam para dizer alguma coisa. O que faltava não era o campo:
-- era trazer o que já está lá do outro lado.
--
-- ⚠️ **`produtos.codigo_omie` já é o "código interno" que sobrevive à troca do
-- código.** Ele guarda o `codigo_produto` do Omie (o id interno de lá, que
-- ninguém edita), tem índice único, e é o **nível 2 da cascata de conciliação**,
-- antes do EAN. `produtos.codigo` é o código da CASA: pode ser renomeado à
-- vontade que o vínculo não se perde. Esta migração só documenta isso na
-- coluna — não havia campo novo a criar.

COMMENT ON COLUMN produtos.codigo_omie IS
    'Código interno do produto no Omie (codigo_produto). É por ele que o '
    'vínculo se mantém quando alguém troca o código da casa. Não se edita.';

-- ---------------------------------------------------------------- o que vem

-- A marca separa "café 500g" de "café 500g": numa lista de 2.000 insumos, é o
-- que faz quem compra reconhecer o item.
ALTER TABLE produtos ADD COLUMN IF NOT EXISTS marca varchar(60);

-- ⚠️ **Peso é conversão, não é enfeite.** O pacote entra por UN e a ficha
-- consome em KG; sem o peso, alguém tem de descobrir e digitar o fator. O Omie
-- costuma ter os dois, e o líquido é o que interessa — o bruto inclui a
-- embalagem, e ninguém cozinha o papelão.
ALTER TABLE produtos ADD COLUMN IF NOT EXISTS peso_liquido numeric(18,6);
ALTER TABLE produtos ADD COLUMN IF NOT EXISTS peso_bruto numeric(18,6);

-- Classificação fiscal que acompanha o NCM. Não muda número nenhum aqui, mas é
-- o que o contador pede quando o produto sai numa nota.
ALTER TABLE produtos ADD COLUMN IF NOT EXISTS cest varchar(10);

-- De onde veio cada campo preenchido de fora. Sem isto, "quem escreveu este
-- peso, eu ou a importação?" não tem resposta — e a resposta decide se a
-- próxima sincronização pode sobrescrever.
ALTER TABLE produtos ADD COLUMN IF NOT EXISTS sincronizado_em timestamptz;

-- Índice para a completagem: ela procura o que está EM BRANCO nos produtos que
-- vieram de fora, e sem isto varre os 2.189 a cada sincronização.
CREATE INDEX IF NOT EXISTS ix_produto_omie_incompleto
    ON produtos (codigo_omie)
 WHERE codigo_omie IS NOT NULL
   AND (codigo_barras IS NULL OR marca IS NULL OR id_categoria IS NULL);

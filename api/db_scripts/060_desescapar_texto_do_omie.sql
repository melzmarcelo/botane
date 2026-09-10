-- O `&amp;` que virou `&AMP;` no meio da razão social.
--
-- 🔑 **Relatado pelo dono (09/09/2026):** *"no Omie está assim o fornecedor,
-- F & C - COMERCIO DE PRODUTOS ALIMENTICIOS LTDA, mas no Botané está assim
-- F &AMP; C - COMERCIO DE PRODUTOS ALIMENTICIOS LTDA"*.
--
-- O Omie devolve JSON, mas com o texto **escapado como se fosse XML**: o `&` da
-- razão social chega `&amp;`, o apóstrofo chega `&apos;`. O importador guardava
-- cru, e o gatilho que põe o nome em maiúsculas ainda escapava o disfarce —
-- `&AMP;` não se parece com nada, e aparece assim na tela, na nota e no
-- relatório. O código foi corrigido na fronteira (`mapeadores._texto`, por onde
-- TODO texto do Omie passa); esta migração repara o que já entrou.
--
-- Na conta real: 10 fornecedores, 8 nomes de fantasia, 10 produtos e 1 item de
-- nota.
--
-- ⚠️ **`&amp;` sai por ÚLTIMO, e a ordem não é estética.** Desescapando-o antes
-- dos outros, um `&amp;lt;` viraria `&lt;` e depois `<` — duas voltas onde só
-- cabia uma. É a regra de qualquer desescape: a entidade do próprio `&` fecha
-- a fila.
--
-- ⚠️ **Sem distinguir maiúscula de minúscula** (`flags 'gi'`): o gatilho de
-- normalização já passou por cima, e o que está gravado é `&AMP;`. Procurar só
-- por `&amp;` não acharia nenhum dos dez.
--
-- ⚠️ **Idempotente por construção**: texto sem entidade nenhuma não casa com os
-- padrões e fica exatamente como está. Rodar de novo não muda nada.

CREATE OR REPLACE FUNCTION _desescapar(t text) RETURNS text AS $$
    SELECT CASE WHEN $1 IS NULL THEN NULL ELSE
        regexp_replace(
        regexp_replace(
        regexp_replace(
        regexp_replace(
        regexp_replace(
        regexp_replace($1,
            '&apos;', '''', 'gi'),
            '&#39;',  '''', 'gi'),
            '&quot;', '"',  'gi'),
            '&lt;',   '<',  'gi'),
            '&gt;',   '>',  'gi'),
            -- por último, sempre
            '&amp;',  '&',  'gi')
    END;
$$ LANGUAGE sql IMMUTABLE;

-- ⚠️ O `WHERE` não é otimização: sem ele, o UPDATE tocaria TODA linha da tabela
-- e dispararia o gatilho de normalização em 3.183 produtos e 951 fornecedores
-- sem necessidade — e um `updated_at` inteiro mudaria de valor num dia em que
-- ninguém mexeu em nada.
UPDATE fornecedores SET nome = _desescapar(nome)
 WHERE nome ~* '&(amp|quot|apos|lt|gt|#39);';
UPDATE fornecedores SET nome_fantasia = _desescapar(nome_fantasia)
 WHERE nome_fantasia ~* '&(amp|quot|apos|lt|gt|#39);';

UPDATE produtos SET nome = _desescapar(nome)
 WHERE nome ~* '&(amp|quot|apos|lt|gt|#39);';
UPDATE produtos SET nome_curto = _desescapar(nome_curto)
 WHERE nome_curto ~* '&(amp|quot|apos|lt|gt|#39);';
UPDATE produtos SET marca = _desescapar(marca)
 WHERE marca ~* '&(amp|quot|apos|lt|gt|#39);';

UPDATE nota_itens SET descricao_fornecedor = _desescapar(descricao_fornecedor)
 WHERE descricao_fornecedor ~* '&(amp|quot|apos|lt|gt|#39);';

UPDATE notas_entrada SET nome_emitente = _desescapar(nome_emitente)
 WHERE nome_emitente ~* '&(amp|quot|apos|lt|gt|#39);';

-- A função era só para esta reparação: o código já não deixa entrar texto
-- escapado, e deixá-la de pé convidaria alguém a usá-la como se fosse a regra.
DROP FUNCTION _desescapar(text);

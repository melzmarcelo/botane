-- Tira do NOME do produto o rodapé de tributos aproximados do DANFE.
--
-- A Lei 12.741 manda imprimir o valor aproximado dos tributos na nota, e muitos
-- emitentes grudam esse texto na descrição do item. Ele viaja pela NF-e até o
-- catálogo do Omie e daí para cá: numa conta real, 59 produtos se chamavam
--
--     MAMÃO FORMOSA Trib. Aprox. (Fed: R$ 3,63. Est: R$ 3,24. ). Fonte:
--     IBPT/empresometro.com.br/25.2.E.
--
-- Nome assim não cabe em tela nenhuma, empurra o resto da linha para fora e faz
-- a busca por "mamão formosa" devolver um nome que ninguém reconhece. Não é
-- parte do nome de nada — é texto fiscal.
--
-- Só mexe no que veio de fora (`origem = 'OMIE'`): nome digitado aqui é de quem
-- digitou. O mapeador já corta na entrada; isto é para o que entrou antes.

UPDATE produtos
   SET nome = btrim(regexp_replace(
           nome, '\s*(trib(\.|\s)*aprox|val(or)?\s*aprox|fonte:\s*ibpt).*$', '', 'i'))
 WHERE origem = 'OMIE'
   AND nome ~* '(trib(\.|\s)*aprox|val(or)?\s*aprox|fonte:\s*ibpt)'
   AND btrim(regexp_replace(
           nome, '\s*(trib(\.|\s)*aprox|val(or)?\s*aprox|fonte:\s*ibpt).*$', '', 'i')) <> '';

UPDATE nota_itens i
   SET descricao_fornecedor = btrim(regexp_replace(
           descricao_fornecedor,
           '\s*(trib(\.|\s)*aprox|val(or)?\s*aprox|fonte:\s*ibpt).*$', '', 'i'))
 WHERE descricao_fornecedor ~* '(trib(\.|\s)*aprox|val(or)?\s*aprox|fonte:\s*ibpt)'
   AND btrim(regexp_replace(
           descricao_fornecedor,
           '\s*(trib(\.|\s)*aprox|val(or)?\s*aprox|fonte:\s*ibpt).*$', '', 'i')) <> '';

-- Botané 054 — a conversão do código de fora, dita por gente. Idempotente.
--
-- 🔑 **O caso do AÇÚCAR DE CONFEITEIRO** (pedido do dono, 04/09/2026). O
-- fornecedor manda o pacote de 1 kg e o de 500 g como PRODUTOS DIFERENTES, com
-- códigos diferentes — e aqui os dois são o mesmo produto. Feita a fusão, o
-- código do de 500 g vira apelido do sobrevivente e a nota dele passa a entrar
-- como **1 kg por unidade**: o estoque dobra, calado, e a diferença só aparece
-- na primeira contagem como "ajuste de inventário".
--
-- A conversão por código já existe e é o PRIMEIRO degrau de `_fator_do_item` —
-- ganha da unidade, do fornecedor e do fator de compra. O que faltava era
-- alguém poder informá-la.
--
-- ⚠️ **Por que uma coluna nova e não só usar o `fator`.** A cascata IGNORA o
-- fator 1 de propósito: `codigos_externos` nasce com 1 e o lançamento da nota
-- cria a linha só para guardar o último preço — aceitar esse 1 como informação
-- fazia o vínculo recém-criado encobrir o `fator_compra` do produto, e o azeite
-- de 5 L entrou certo na primeira nota e virou 1 L na segunda. Essa regra
-- continua valendo para o 1 AUTOMÁTICO.
--
-- 🔑 Mas "por padrão 1" é justamente o que o dono pediu para poder digitar: o
-- pacote de 1 kg é 1, e isso é uma AFIRMAÇÃO, não a ausência de uma. Esta
-- coluna separa as duas: marcado, o fator vale qualquer que seja o número.

ALTER TABLE codigos_externos
    ADD COLUMN IF NOT EXISTS fator_confirmado boolean NOT NULL DEFAULT false;

COMMENT ON COLUMN codigos_externos.fator_confirmado IS
    'Alguém digitou esta conversão na tela do produto. Marcado, o fator vale '
    'mesmo sendo 1 — sem a marca, 1 é o padrão da coluna e a cascata segue adiante.';

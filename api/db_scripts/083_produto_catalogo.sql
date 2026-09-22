-- A foto do produto e o que contar sobre ele no catálogo.
--
-- 🔑 **Pedido do dono (22/09/2026):** *"no cadastro de produtos, quando
-- utilizando Reservas, criar uma nova aba chamada Catálogo. Nesta aba teremos
-- Foto e um campo para Informação Adicional."*
--
-- 🔑 **Os nomes são GENÉRICOS, a aba é que é do catálogo.** Foto de produto é
-- atributo do produto: no dia em que a ficha técnica, o PDV ou um cardápio
-- impresso quiserem a mesma imagem, ela já está aqui — e `catalogo_foto_url`
-- teria de ser lida como "a foto que por acaso mora no catálogo". A aba agrupa;
-- a coluna descreve.
--
-- ⚠️ **`informacao_adicional` NÃO é `observacao`, e a diferença é quem lê.**
-- `observacao` é recado interno, escrito para quem trabalha na casa;
-- `informacao_adicional` é para o CLIENTE — vai ao lado do produto no catálogo.
-- Misturar as duas publicaria "conferir com o fornecedor, veio errado da
-- última vez" no site.

ALTER TABLE produtos ADD COLUMN IF NOT EXISTS foto_url   varchar(255);
ALTER TABLE produtos ADD COLUMN IF NOT EXISTS foto_nome  varchar(255);
ALTER TABLE produtos ADD COLUMN IF NOT EXISTS foto_bytes integer;
ALTER TABLE produtos ADD COLUMN IF NOT EXISTS foto_em    timestamptz;

-- ⚠️ **Com teto, e o teto é o da TELA que vai mostrar.** Texto livre sem limite
-- em campo que o cliente lê é convite para alguém colar uma receita inteira e
-- descobrir no site que ela não cabe em lugar nenhum.
ALTER TABLE produtos ADD COLUMN IF NOT EXISTS informacao_adicional varchar(500);

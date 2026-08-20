-- Botané 017 — o local de estoque é do PRODUTO, não da nota. Idempotente.
--
-- Uma nota traz congelado e seco na mesma folha: pedir "o local da nota" faz a
-- pessoa lançar duas vezes, ou aceitar que o sorvete entre no estoque seco.
-- Quem sabe onde cada coisa mora é o cadastro do produto.
--
-- Continua havendo um local na nota: ele é a RESERVA, para o produto que ainda
-- não tem um definido. Assim nada deixa de entrar por falta de cadastro.
ALTER TABLE produtos ADD COLUMN IF NOT EXISTS id_local_padrao integer
    REFERENCES locais_estoque(id);
CREATE INDEX IF NOT EXISTS ix_produto_local_padrao ON produtos (id_local_padrao);

COMMENT ON COLUMN produtos.id_local_padrao IS
    'Onde este produto entra quando chega numa nota. NULL = usa o local da nota.';

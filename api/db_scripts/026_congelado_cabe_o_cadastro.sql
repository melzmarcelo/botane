-- A cópia congelada tem de caber o que o cadastro guarda.
--
-- `cmv_movimentacao` grava nome, código, categoria e setor do produto junto com
-- os números — é isso que impede renomear um produto de reescrever um mês já
-- fechado. Só que `codigo` nasceu `varchar(20)` enquanto `produtos.codigo` é
-- `varchar(40)`: **fechar o mês estourava com 500** assim que a base tinha um
-- código de verdade. Numa conta real havia três acima de 20 caracteres, o maior
-- com 40 ("Impermeabilizante 300g Veda Tudo Milagro" — o fornecedor pôs a
-- descrição no lugar do código).
--
-- É a terceira vez que o mundo real não respeita largura de coluna aqui (o
-- catálogo do Omie e o NCM foram as outras duas). A regra que sai disso: cópia
-- congelada acompanha a largura da ORIGEM, não um palpite.

ALTER TABLE cmv_movimentacao ALTER COLUMN codigo TYPE varchar(40);

DO $$
BEGIN
    -- `produto` já é maior que `produtos.nome` (200 contra 160), e as duas de
    -- grupo já cabem os 80 de `categorias.nome`/`setores.nome`. Ficam como
    -- estão; o ALTER acima é o único que faltava.
    IF (SELECT character_maximum_length FROM information_schema.columns
         WHERE table_name = 'cmv_movimentacao' AND column_name = 'codigo') < 40 THEN
        RAISE EXCEPTION 'cmv_movimentacao.codigo continua estreito demais';
    END IF;
END $$;

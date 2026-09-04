-- Botané 055 — o fornecedor vira PESSOA, e a pessoa tem política de cupom.
-- Idempotente.
--
-- 🔑 **Pedido do dono (04/09/2026):** "hoje temos somente o cadastro de
-- fornecedores, podemos tratar ele como pessoa — visualmente no menu e no
-- cadastro; na base podemos manter a mesma estrutura". É o que este script faz:
-- **nenhuma tabela é renomeada**. `fornecedores` continua sendo `fornecedores`,
-- e quem aponta para ela (`notas_entrada`, `produto_fornecedor`,
-- `codigos_externos`) não muda uma linha.
--
-- Renomear a tabela custaria migração em três chaves estrangeiras, em todo
-- SELECT do sistema e em toda suíte — para o usuário ver exatamente a mesma
-- tela. O nome que importa é o que está escrito no menu.
--
-- ⚠️ **`fornecedor` nasce TRUE, e isso é o ponto.** Hoje toda linha da tabela é
-- oferecida no seletor de fornecedor da nota e do produto. Se a pessoa nova
-- entrasse sem marca, o seletor da nota viraria uma lista de funcionários. Com
-- o padrão verdadeiro, **nada muda para quem já está cadastrado** e só o que
-- nascer sem a marca fica de fora daqueles seletores.
--
-- 🔑 **A política do cupom** (`cupom_base`, `cupom_desconto_pct`): a venda
-- lançada à mão sempre puxa o PREÇO DE VENDA; informando uma pessoa, ela passa
-- a valer o CUSTO, ou o preço com desconto. É o desconto de funcionário e o
-- consumo do proprietário, com a mesma mecânica e políticas diferentes.
-- ⚠️ O padrão é `VENDA` com desconto zero: pessoa sem política configurada não
-- muda nada, que é o que faz esta coluna nascer inofensiva.

ALTER TABLE fornecedores
    ADD COLUMN IF NOT EXISTS fornecedor boolean NOT NULL DEFAULT true;

ALTER TABLE fornecedores
    ADD COLUMN IF NOT EXISTS cupom_base varchar(10) NOT NULL DEFAULT 'VENDA';

ALTER TABLE fornecedores
    ADD COLUMN IF NOT EXISTS cupom_desconto_pct numeric(5,2) NOT NULL DEFAULT 0;

-- ⚠️ A trava é do BANCO, não só da tela: um `cupom_base` fora dos dois valores
-- faria a venda cair no `else` e sair pelo preço sem ninguém saber por quê.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_cupom_base') THEN
        ALTER TABLE fornecedores
            ADD CONSTRAINT ck_cupom_base CHECK (cupom_base IN ('VENDA', 'CUSTO'));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_cupom_desconto') THEN
        ALTER TABLE fornecedores
            ADD CONSTRAINT ck_cupom_desconto
            CHECK (cupom_desconto_pct >= 0 AND cupom_desconto_pct <= 100);
    END IF;
END $$;

-- 🔑 **O vínculo entre quem ENTRA no sistema e quem a pessoa É.** O usuário é a
-- credencial; a pessoa é o cadastro. Sem isto, o funcionário que compra com
-- desconto e o usuário que abre o sistema são dois registros que ninguém liga.
-- ⚠️ `ON DELETE SET NULL`: apagar a pessoa não pode derrubar o login de
-- ninguém. E a pessoa quase nunca é apagada — vira inativa.
ALTER TABLE usuarios
    ADD COLUMN IF NOT EXISTS id_pessoa integer REFERENCES fornecedores(id) ON DELETE SET NULL;

-- A pergunta é "quem é a pessoa deste usuário?", feita a cada carregamento de
-- perfil e da lista de usuários.
CREATE INDEX IF NOT EXISTS ix_usuarios_pessoa ON usuarios (id_pessoa)
    WHERE id_pessoa IS NOT NULL;

-- O seletor de fornecedor filtra por esta coluna em toda tela de compra.
CREATE INDEX IF NOT EXISTS ix_fornecedores_fornecedor ON fornecedores (fornecedor)
    WHERE fornecedor;

-- 🔑 **A venda guarda PARA QUEM foi.** Sem isto, o desconto de funcionário
-- acontece e não deixa rastro: o cupom sai mais barato e ninguém sabe de quem
-- foi a política que o barateou. É também o que permite responder "quanto a
-- equipe consumiu no mês" sem adivinhar pelo valor.
-- ⚠️ `ON DELETE SET NULL`: apagar a pessoa não pode apagar a venda.
ALTER TABLE vendas
    ADD COLUMN IF NOT EXISTS id_pessoa integer REFERENCES fornecedores(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS ix_vendas_pessoa ON vendas (id_pessoa)
    WHERE id_pessoa IS NOT NULL;

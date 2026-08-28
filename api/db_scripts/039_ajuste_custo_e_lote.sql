-- Botané 039 — ajuste de custo e ajuste em lote. Idempotente.
--
-- Duas faltas que a operação cobrou:
--
-- 1. **Ajustar um produto de cada vez.** Quem confere a despensa acha cinco
--    diferenças e precisa lançar cinco vezes, saindo e voltando na tela. Pior:
--    as cinco viram cinco lançamentos sem relação nenhuma entre si, e quem
--    olhar o razão depois não sabe que vieram da mesma conferência.
--
-- 2. **Não havia como corrigir um custo médio errado.** E o sistema PRODUZ
--    esse caso sozinho: saída com saldo negativo sai por custo provisório,
--    produto criado a partir do item da nota nasce sem custo, e nota digitada
--    com o valor errado contamina o médio dali para frente. Até aqui a única
--    saída era uma entrada e uma saída falsas de mesma quantidade — que mente
--    no razão e some com a rastreabilidade.

-- ------------------------------------------------- 1 · o movimento de VALOR
-- 🔑 **A trava de quantidade precisa abrir só para o tipo novo.** Ajuste de
-- custo não move mercadoria: ele muda quanto vale o que já está lá. Quantidade
-- zero, valor diferente de zero.
--
-- ⚠️ Manter o `<> 0` para todos os outros tipos é o que impede o movimento
-- vazio de virar um jeito de "lançar nada" e sujar o razão.
ALTER TABLE estoque_movimentos DROP CONSTRAINT IF EXISTS ck_mov_qtd;
ALTER TABLE estoque_movimentos
    ADD CONSTRAINT ck_mov_qtd CHECK (quantidade <> 0 OR tipo = 'AJUSTE_CUSTO');

COMMENT ON CONSTRAINT ck_mov_qtd ON estoque_movimentos IS
    'Movimento vazio não existe — exceto AJUSTE_CUSTO, que é o único que mexe '
    'no valor sem mexer na quantidade.';

-- ------------------------------------------------------------ 2 · o lote
-- Um cabeçalho para o conjunto. Sem ele, cinco ajustes da mesma conferência
-- ficam indistinguíveis de cinco ajustes avulsos feitos em dias diferentes —
-- e a pergunta "de onde veio isto?" não tem resposta.
CREATE TABLE IF NOT EXISTS ajuste_lotes (
    id          bigserial PRIMARY KEY,
    id_unidade  integer NOT NULL REFERENCES unidades(id),
    -- ESTOQUE (quantidade) ou CUSTO (valor). São processos diferentes na tela
    -- e exigem permissões diferentes.
    natureza    varchar(10) NOT NULL,
    -- O que a pessoa escreveu ao lançar: "conferência da câmara fria, 28/08".
    -- É o que explica o lote inteiro quando alguém o encontrar meses depois.
    observacao  text,
    documento   varchar(60),
    id_usuario  integer REFERENCES usuarios(id),
    criado_em   timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_ajuste_lote_natureza CHECK (natureza IN ('ESTOQUE', 'CUSTO'))
);
CREATE INDEX IF NOT EXISTS ix_ajuste_lote_unidade
    ON ajuste_lotes (id_unidade, criado_em DESC);

COMMENT ON TABLE ajuste_lotes IS
    'Cabeçalho de um conjunto de ajustes lançados juntos. Os movimentos '
    'apontam para cá por origem_tipo = ''AJUSTE_LOTE'' e origem_id.';

-- ------------------------------------------------------- 3 · a permissão
-- 🔑 **Ajuste de custo é permissão SEPARADA de ajuste de estoque**, e não é
-- preciosismo: mexer na quantidade é dizer que a prateleira tem outra coisa;
-- mexer no custo é dizer que o dinheiro é outro. O segundo altera o CMV do
-- período sem que nada tenha entrado ou saído — quem confere a despensa não
-- precisa desse poder.
INSERT INTO permissoes (chave, modulo, descricao, ordem)
VALUES ('estoque.custo', 'Estoque', 'Ajustar o custo médio do estoque', 275)
ON CONFLICT (chave) DO UPDATE
    SET modulo = EXCLUDED.modulo, descricao = EXCLUDED.descricao;

-- ⚠️ O script 002 já rodou e não roda de novo (o db_updater guarda o
-- checksum), então o papel de fábrica não recebe a chave nova sozinho.
-- Administrador e Gerente, pela mesma regra de lá. **Conferente NÃO entra**:
-- ele conta prateleira, não decide valor.
INSERT INTO papel_permissoes (id_papel, chave)
SELECT p.id, 'estoque.custo' FROM papeis p
 WHERE p.sistema AND p.nome IN ('Administrador', 'Gerente')
ON CONFLICT DO NOTHING;

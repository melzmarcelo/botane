-- Botané 036 — a descrição do produto é MAIÚSCULA, sempre. Idempotente.
--
-- A base tinha 752 de 3.226 produtos em caixa mista: "Matcha Culinario 500g" ao
-- lado de "CAFE EXPRESSO", "BIOMA - Microverde Rucula" ao lado de "MANTEIGA
-- S/SAL BL 5KG". Não é feiura: é lista que não se lê. Numa tela de conferência
-- de compra, o olho percorre a coluna procurando um item, e caixa alternada
-- quebra o ritmo da varredura — some-se a isso que os nomes vêm de três lugares
-- (Omie, cardápio do PDV e a mão de quem cadastra), cada um com sua convenção.
--
-- ⚠️ **É um GATILHO, e é o primeiro do projeto — a escolha tem razão.** O nome
-- do produto é escrito em CINCO lugares hoje: o formulário, a importação do
-- catálogo do Omie, a do cardápio do PDV, a criação a partir do item da nota, e
-- a fusão de cadastros. Um helper na aplicação teria de ser chamado nos cinco, e
-- o sexto — que vai existir — nasceria sem ele, trazendo a caixa mista de volta
-- sem ninguém notar. "Por padrão" é regra de DADO; quem garante regra de dado
-- sem depender de memória é o banco.
--
-- ⚠️ O `upper()` do Postgres foi conferido contra o do Python acento a acento:
-- "Café" → "CAFÉ", "Ação" → "AÇÃO", "Filé mignon à moda" → "FILÉ MIGNON À MODA".
--
-- ⚠️ **Só nome e nome curto.** `observacao` é texto corrido que alguém escreveu
-- para ser lido; em maiúsculas vira grito e fica pior. `codigo` já é tratado
-- como sensível a caixa pela unicidade (`lower(codigo)`), e mexer nele mudaria
-- o de-para com o Omie.

CREATE OR REPLACE FUNCTION produto_nome_maiusculo() RETURNS trigger AS $$
BEGIN
    IF NEW.nome IS NOT NULL THEN
        NEW.nome := upper(btrim(NEW.nome));
    END IF;
    IF NEW.nome_curto IS NOT NULL THEN
        NEW.nome_curto := upper(btrim(NEW.nome_curto));
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS tg_produto_nome_maiusculo ON produtos;
CREATE TRIGGER tg_produto_nome_maiusculo
    BEFORE INSERT OR UPDATE OF nome, nome_curto ON produtos
    FOR EACH ROW EXECUTE FUNCTION produto_nome_maiusculo();

-- O que já está gravado. ⚠️ A condição existe para o script ser barato quando
-- roda de novo: sem ela, todo deploy reescreveria a tabela inteira.
UPDATE produtos
   SET nome = upper(btrim(nome))
 WHERE nome IS NOT NULL AND nome <> upper(btrim(nome));

UPDATE produtos
   SET nome_curto = upper(btrim(nome_curto))
 WHERE nome_curto IS NOT NULL AND nome_curto <> upper(btrim(nome_curto));

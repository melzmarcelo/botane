-- Botané 050 — fornecedor e tabelas de apoio em MAIÚSCULAS, como o produto.
-- Idempotente.
--
-- 🔑 **Isto REVERTE uma decisão registrada, e a reversão é do dono.** A nota da
-- migração 036 dizia: *"nome de fornecedor NÃO segue a regra: é razão social,
-- vem de um lugar só, e 'Cia. Brasileira de Distribuição' em caixa alta perde a
-- leitura sem ganhar nada"*. O argumento continua verdadeiro para a LEITURA de
-- um nome isolado — e é falso para o que a casa faz o dia inteiro, que é
-- percorrer uma COLUNA procurando um item. Ali a caixa alternada quebra a
-- varredura, e ter produto em caixa alta ao lado de fornecedor em caixa mista
-- deixa a tela com duas convenções.
--
-- Estado da base quando isto foi escrito: 43 fornecedores, 31 setores, 111
-- locais, 14 categorias e 17 unidades de medida fora do padrão.
--
-- ⚠️ **Gatilho, e não helper — a mesma razão da 036.** Estes nomes são escritos
-- em vários lugares: o formulário, o importador de fornecedores do Omie, a
-- família do Omie que vira categoria, o grupo e a impressora do cardápio do PDV
-- que viram categoria e setor, e a loja nova que nasce com um local. Um helper
-- teria de ser chamado em todos, e o próximo — que vai existir — nasceria sem
-- ele, trazendo a caixa mista de volta sem ninguém notar.
--
-- ⚠️ **NENHUMA colisão é possível.** A unicidade de `setores`, `locais_estoque`
-- e `perda_motivos` já é `lower(nome)`: dois nomes que só diferem na caixa nunca
-- puderam coexistir. Os 65 "ESTOQUE" da base são de 65 lojas diferentes, e a
-- unicidade do local é `(id_unidade, lower(nome))`.
--
-- ⚠️ **`unidades_medida.sigla` fica FORA, e não é esquecimento.** Ela é a chave
-- primária, referenciada por produto, ficha, item de nota e razão: subir a caixa
-- ali não renomeia um rótulo, quebra o de-para. Quem já a põe em maiúsculas é o
-- formulário, na digitação. Mesma razão pela qual `produtos.codigo` ficou fora
-- da 036.
--
-- ⚠️ **Observação, endereço e contato ficam fora.** São texto que alguém
-- escreveu para ser lido; em maiúsculas viram grito, como já valia para
-- `produtos.observacao`.
--
-- ⚠️ **`perda_motivos` fica fora de propósito**: não é uma das quatro tabelas de
-- apoio da tela, e "Quebra no transporte" é uma frase, não um rótulo de coluna.
-- Entra no dia em que alguém pedir.

CREATE OR REPLACE FUNCTION nome_maiusculo() RETURNS trigger AS $$
BEGIN
    IF NEW.nome IS NOT NULL THEN
        NEW.nome := upper(btrim(NEW.nome));
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- O fornecedor tem DOIS nomes, como o produto: a razão social e o fantasia.
-- Guardar um em caixa alta e o outro não deixaria a mesma tela com as duas
-- convenções — que é justamente o que se está corrigindo.
CREATE OR REPLACE FUNCTION fornecedor_nome_maiusculo() RETURNS trigger AS $$
BEGIN
    IF NEW.nome IS NOT NULL THEN
        NEW.nome := upper(btrim(NEW.nome));
    END IF;
    IF NEW.nome_fantasia IS NOT NULL THEN
        NEW.nome_fantasia := upper(btrim(NEW.nome_fantasia));
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS tg_fornecedor_nome_maiusculo ON fornecedores;
CREATE TRIGGER tg_fornecedor_nome_maiusculo
    BEFORE INSERT OR UPDATE OF nome, nome_fantasia ON fornecedores
    FOR EACH ROW EXECUTE FUNCTION fornecedor_nome_maiusculo();

DROP TRIGGER IF EXISTS tg_setor_nome_maiusculo ON setores;
CREATE TRIGGER tg_setor_nome_maiusculo
    BEFORE INSERT OR UPDATE OF nome ON setores
    FOR EACH ROW EXECUTE FUNCTION nome_maiusculo();

DROP TRIGGER IF EXISTS tg_local_nome_maiusculo ON locais_estoque;
CREATE TRIGGER tg_local_nome_maiusculo
    BEFORE INSERT OR UPDATE OF nome ON locais_estoque
    FOR EACH ROW EXECUTE FUNCTION nome_maiusculo();

DROP TRIGGER IF EXISTS tg_categoria_nome_maiusculo ON categorias;
CREATE TRIGGER tg_categoria_nome_maiusculo
    BEFORE INSERT OR UPDATE OF nome ON categorias
    FOR EACH ROW EXECUTE FUNCTION nome_maiusculo();

DROP TRIGGER IF EXISTS tg_um_nome_maiusculo ON unidades_medida;
CREATE TRIGGER tg_um_nome_maiusculo
    BEFORE INSERT OR UPDATE OF nome ON unidades_medida
    FOR EACH ROW EXECUTE FUNCTION nome_maiusculo();

-- O que já está gravado. ⚠️ A condição existe para o script ser barato quando
-- roda de novo: sem ela, todo deploy reescreveria as cinco tabelas inteiras.
UPDATE fornecedores SET nome = upper(btrim(nome))
 WHERE nome IS NOT NULL AND nome <> upper(btrim(nome));
UPDATE fornecedores SET nome_fantasia = upper(btrim(nome_fantasia))
 WHERE nome_fantasia IS NOT NULL AND nome_fantasia <> upper(btrim(nome_fantasia));

UPDATE setores SET nome = upper(btrim(nome))
 WHERE nome IS NOT NULL AND nome <> upper(btrim(nome));

UPDATE locais_estoque SET nome = upper(btrim(nome))
 WHERE nome IS NOT NULL AND nome <> upper(btrim(nome));

UPDATE categorias SET nome = upper(btrim(nome))
 WHERE nome IS NOT NULL AND nome <> upper(btrim(nome));

UPDATE unidades_medida SET nome = upper(btrim(nome))
 WHERE nome IS NOT NULL AND nome <> upper(btrim(nome));

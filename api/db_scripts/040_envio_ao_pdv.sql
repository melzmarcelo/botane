-- Botané 040 — o primeiro passo do envio para o PDV: o interruptor e a marca.
-- Idempotente.
--
-- A integração com o PDV Legal é de mão única desde que nasceu: lemos cardápio,
-- preços e vendas. Enviar de volta abre um caminho que pode estragar o sistema
-- que a casa usa para vender, então ele começa por duas coisas que **não
-- enviam nada**: o interruptor e a marcação de quem participa.
--
-- ⚠️ **`integracoes.enviar_ao_pdv` nasce FALSO.** Ligar é decisão de quem paga
-- a conta e responde pelo cardápio — não de uma migração. É a mesma regra da
-- agenda de busca, que também nasce MANUAL.
--
-- ⚠️ **`produtos.integrado_pdv` NÃO é o mesmo que `codigo_pdv`, e a diferença é
-- justamente a fila de envio:**
--
--   integrado | tem código lá | quer dizer                    | o que se faz
--   ----------|---------------|-------------------------------|--------------
--       sim   |      não      | deve existir lá e ainda não    | criar
--       sim   |      sim      | existe lá                      | atualizar se mudou
--       não   |      sim      | veio de lá; não mandamos nada  | nada
--       não   |      não      | insumo de compra               | nada
--
-- A terceira linha é a que impede este campo de ser derivado de `codigo_pdv`:
-- ela é um estado legítimo — "este produto existe no PDV e eu não quero que o
-- Botané mexa nele".

ALTER TABLE integracoes
    ADD COLUMN IF NOT EXISTS enviar_ao_pdv boolean NOT NULL DEFAULT false;

ALTER TABLE produtos
    ADD COLUMN IF NOT EXISTS integrado_pdv boolean NOT NULL DEFAULT false;

-- A fila vai perguntar "quem está marcado?" a cada abertura da tela. São 3.301
-- produtos e uns 500 marcados: o índice parcial é pequeno e responde direto.
CREATE INDEX IF NOT EXISTS ix_produto_integrado_pdv
    ON produtos (integrado_pdv) WHERE integrado_pdv;

-- ---------------------------------------------------------------------------
-- Quem já tem ligação com o PDV nasce marcado
-- ---------------------------------------------------------------------------
-- ⚠️ Marca por FATO, não por semelhança: quem tem o código principal do PDV, ou
-- um dos apelidos em `codigos_externos` — na conta real `ENTREGA` sozinho tem
-- quatro códigos de cardápio apontando para o mesmo produto.
-- ⚠️ A condição `AND NOT integrado_pdv` deixa o script barato ao rodar de novo,
-- e — mais importante — **não desfaz o desmarque de ninguém**: quem tirou a
-- marca de um produto que veio do PDV (a terceira linha da tabela acima) não a
-- recebe de volta no próximo deploy.

UPDATE produtos p
   SET integrado_pdv = true
 WHERE NOT p.integrado_pdv
   AND ( p.codigo_pdv IS NOT NULL
         OR EXISTS (SELECT 1 FROM codigos_externos ce
                     WHERE ce.id_produto = p.id AND ce.sistema = 'PDV_LEGAL') );

-- ---------------------------------------------------------------------------
-- E quem GANHAR a ligação depois nasce marcado também
-- ---------------------------------------------------------------------------
-- 🔑 **Gatilho, e pela mesma razão do 036.** O `codigo_pdv` é escrito em quatro
-- lugares — o formulário do produto, a importação do cardápio, e as duas rotas
-- do botão Vincular. Marcar na aplicação exigiria lembrar nos quatro, e o
-- quinto — que vai existir — nasceria sem a marca: o produto passaria a existir
-- no PDV e nunca apareceria na fila de envio. Quem garante regra de dado sem
-- depender de memória é o banco.
--
-- ⚠️ **Só na TRANSIÇÃO de vazio para preenchido.** Um gatilho que forçasse
-- `true` sempre que houvesse código destruiria a terceira linha da tabela: quem
-- desmarcou um produto que veio do PDV o veria remarcado no primeiro save.
-- Aqui, desmarcar é uma decisão que fica de pé.

CREATE OR REPLACE FUNCTION produto_marca_integrado_pdv() RETURNS trigger AS $$
BEGIN
    IF NEW.codigo_pdv IS NOT NULL
       AND (TG_OP = 'INSERT' OR OLD.codigo_pdv IS NULL) THEN
        NEW.integrado_pdv := true;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS tg_produto_marca_integrado_pdv ON produtos;
CREATE TRIGGER tg_produto_marca_integrado_pdv
    BEFORE INSERT OR UPDATE OF codigo_pdv ON produtos
    FOR EACH ROW EXECUTE FUNCTION produto_marca_integrado_pdv();

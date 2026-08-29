-- Botané 044 — liga a pendência de PRODUTO. Idempotente.
--
-- A 043 deixou a função do gatilho já sabendo tratar produto, e o
-- `CREATE TRIGGER` escrito e comentado, com a razão: 533 produtos marcados
-- gerariam pendência que ninguém conseguia enviar, porque não existia montador
-- de corpo nem rota. Agora existe.
--
-- 🔑 **O PREÇO mora noutra tabela, e sem este segundo gatilho ele não geraria
-- pendência nenhuma.** `produto_precos` é uma tabela à parte — mudar o preço
-- não toca em `produtos`, então o gatilho de lá nunca dispararia. Um envio que
-- ignora a mudança de preço é pior que não ter envio de preço: a tela diria
-- "tudo integrado" com o cardápio cobrando o valor velho.
--
-- ⚠️ **`ativo` ENTRA na regra do produto, ao contrário da categoria.** Lá o
-- campo tem donos diferentes (PASCOA fica ativa aqui o ano todo e é ligada e
-- desligada lá conforme a época); aqui, desativar um produto deve tirá-lo do
-- cardápio. O que impede o ping-pong é a PENDÊNCIA: é a mudança feita AQUI que
-- autoriza mexer no `ativo` de LÁ. Se alguém desativar no PDV e nada mudar
-- aqui, não há pendência — e nada é reativado.

CREATE OR REPLACE FUNCTION pdv_marcar_pendencia() RETURNS trigger AS $$
DECLARE
    v_tipo      varchar(20);
    v_motivo    varchar(12);
    v_antes     boolean;
    v_id        integer;
    v_integrado boolean;
BEGIN
    v_tipo := CASE TG_TABLE_NAME
                  WHEN 'categorias'     THEN 'CATEGORIA'
                  WHEN 'setores'        THEN 'SETOR'
                  WHEN 'produtos'       THEN 'PRODUTO'
                  WHEN 'produto_precos' THEN 'PRODUTO'
              END;
    IF v_tipo IS NULL THEN
        RETURN NEW;
    END IF;

    -- ⚠️ Na tabela de preços, `NEW.id` é o id da LINHA DE PREÇO, não o do
    -- produto. Usar o `NEW.id` genérico aqui criaria pendência para um produto
    -- que não existe — e ela nunca sairia da fila.
    IF TG_TABLE_NAME = 'produto_precos' THEN
        v_id := NEW.id_produto;
        SELECT p.integrado_pdv INTO v_integrado FROM produtos p WHERE p.id = v_id;
        v_antes := coalesce(v_integrado, false);
    ELSE
        v_id := NEW.id;
        v_integrado := NEW.integrado_pdv;
        v_antes := CASE WHEN TG_OP = 'UPDATE' THEN OLD.integrado_pdv ELSE false END;
    END IF;

    -- Quem nunca participou e continua sem participar não gera nada.
    IF NOT coalesce(v_integrado, false) AND NOT v_antes THEN
        RETURN NEW;
    END IF;

    v_motivo := CASE
        WHEN TG_TABLE_NAME = 'produto_precos'        THEN 'ALTERADO'
        WHEN TG_OP = 'INSERT'                        THEN 'CRIADO'
        WHEN v_antes AND NOT v_integrado             THEN 'REMOVIDO'
        WHEN NOT v_antes AND v_integrado             THEN 'CRIADO'
        ELSE 'ALTERADO'
    END;

    INSERT INTO pdv_pendencias (tipo, id_registro, motivo)
    VALUES (v_tipo, v_id, v_motivo)
    ON CONFLICT (tipo, id_registro) WHERE resolvido_em IS NULL
    DO UPDATE SET motivo = EXCLUDED.motivo, detectado_em = now();

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;


-- ---------------------------------------------------------------------------
-- O produto
-- ---------------------------------------------------------------------------
-- ⚠️ Os campos são os que o cardápio do PDV ENXERGA. `ncm`, `cest` e
-- `codigo_barras` entram porque vão no cadastro de lá; **os impostos NÃO** —
-- eles moram no PDV, estão preenchidos em 629 dos 630 (CFOP 5102, CSOSN 102,
-- CST 00, PIS/Cofins e a reforma tributária) e o Botané não tem nenhum deles.
-- Tocar neles zeraria a emissão fiscal do cliente.

DROP TRIGGER IF EXISTS tg_pdv_pendencia_produto_ins ON produtos;
DROP TRIGGER IF EXISTS tg_pdv_pendencia_produto_upd ON produtos;
CREATE TRIGGER tg_pdv_pendencia_produto_ins
    AFTER INSERT ON produtos
    FOR EACH ROW EXECUTE FUNCTION pdv_marcar_pendencia();
CREATE TRIGGER tg_pdv_pendencia_produto_upd
    AFTER UPDATE OF nome, nome_curto, integrado_pdv, ativo, id_categoria, id_setor,
                    um_estoque, ncm, cest, codigo_barras ON produtos
    FOR EACH ROW
    WHEN (OLD.nome IS DISTINCT FROM NEW.nome
          OR OLD.nome_curto IS DISTINCT FROM NEW.nome_curto
          OR OLD.integrado_pdv IS DISTINCT FROM NEW.integrado_pdv
          OR OLD.ativo IS DISTINCT FROM NEW.ativo
          OR OLD.id_categoria IS DISTINCT FROM NEW.id_categoria
          OR OLD.id_setor IS DISTINCT FROM NEW.id_setor
          OR OLD.um_estoque IS DISTINCT FROM NEW.um_estoque
          OR OLD.ncm IS DISTINCT FROM NEW.ncm
          OR OLD.cest IS DISTINCT FROM NEW.cest
          OR OLD.codigo_barras IS DISTINCT FROM NEW.codigo_barras)
    EXECUTE FUNCTION pdv_marcar_pendencia();

-- ---------------------------------------------------------------------------
-- O preço
-- ---------------------------------------------------------------------------
-- ⚠️ Só no INSERT: uma linha nova em `produto_precos` É a mudança de preço —
-- a tabela guarda a série ("quando o preço subiu"), e o `UPDATE` ali só fecha a
-- vigência da linha anterior, que não é preço novo nenhum.

DROP TRIGGER IF EXISTS tg_pdv_pendencia_preco ON produto_precos;
CREATE TRIGGER tg_pdv_pendencia_preco
    AFTER INSERT ON produto_precos
    FOR EACH ROW EXECUTE FUNCTION pdv_marcar_pendencia();

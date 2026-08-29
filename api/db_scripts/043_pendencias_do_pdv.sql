-- Botané 043 — a tabela intermediária: o que mudou aqui e ainda não foi ao PDV.
-- Idempotente.
--
-- 🔑 **Nada vai ao PDV em tempo real.** Alterar um cadastro aqui não escreve
-- lá: gera uma PENDÊNCIA, que fica esperando alguém abrir a tela de Exportação,
-- conferir o que vai sair e mandar. Escrever no cardápio de quem está vendendo
-- não pode ser efeito colateral de salvar um formulário.
--
-- 🔑 **Quem alimenta esta tabela é o BANCO, não a aplicação.** Um `INSERT` na
-- pendência escrito no código teria de existir em todo lugar que salva um
-- cadastro — e o próximo lugar, que vai existir, nasceria sem ele: o registro
-- mudaria aqui e nunca apareceria como pendente. É a mesma razão que fez a
-- maiúscula do nome (036) e a marca de integrado (040) virarem gatilho:
-- **regra de dado que depende de memória é regra que se perde.**

CREATE TABLE IF NOT EXISTS pdv_pendencias (
    id            bigserial PRIMARY KEY,
    tipo          varchar(20) NOT NULL,   -- CATEGORIA | SETOR | PRODUTO
    id_registro   integer     NOT NULL,
    -- O que aconteceu aqui. Não é o que será feito lá: quem decide entre
    -- adotar, criar e atualizar é o envio, olhando o que o PDV já tem.
    motivo        varchar(12) NOT NULL,   -- CRIADO | ALTERADO | REMOVIDO
    detectado_em  timestamptz NOT NULL DEFAULT now(),
    resolvido_em  timestamptz,
    id_envio      bigint REFERENCES pdv_envios(id)
);

-- ⚠️ **UMA pendência aberta por registro.** Sem isto, dez correções seguidas no
-- mesmo cadastro viram dez linhas na tela, e quem confere lê a mesma categoria
-- dez vezes sem entender por quê. O gatilho usa este índice no `ON CONFLICT`.
CREATE UNIQUE INDEX IF NOT EXISTS ux_pdv_pendencia_aberta
    ON pdv_pendencias (tipo, id_registro) WHERE resolvido_em IS NULL;

CREATE INDEX IF NOT EXISTS ix_pdv_pendencia_abertas
    ON pdv_pendencias (resolvido_em, tipo) WHERE resolvido_em IS NULL;


-- ---------------------------------------------------------------------------
-- O gatilho: um só, para os três tipos
-- ---------------------------------------------------------------------------
-- ⚠️ **`ativo` NÃO entra, e a ausência é a decisão mais importante deste
-- arquivo.** O campo tem donos diferentes dos dois lados: aqui quer dizer "uso
-- este cadastro"; no PDV, "aparece no cardápio para vender AGORA". PASCOA e DIA
-- DOS NAMORADOS ficam ativas aqui o ano todo e são ligadas e desligadas lá
-- conforme a época. Se `ativo` gerasse pendência, essas categorias entrariam na
-- fila a cada virada de estação — e o envio as reativaria no cardápio.

CREATE OR REPLACE FUNCTION pdv_marcar_pendencia() RETURNS trigger AS $$
DECLARE
    v_tipo   varchar(20);
    v_motivo varchar(12);
    v_antes  boolean;
BEGIN
    v_tipo := CASE TG_TABLE_NAME
                  WHEN 'categorias' THEN 'CATEGORIA'
                  WHEN 'setores'    THEN 'SETOR'
                  WHEN 'produtos'   THEN 'PRODUTO'
              END;
    IF v_tipo IS NULL THEN
        RETURN NEW;
    END IF;

    v_antes := CASE WHEN TG_OP = 'UPDATE' THEN OLD.integrado_pdv ELSE false END;

    -- Quem nunca participou e continua sem participar não gera nada: são
    -- milhares de cadastros que não têm o que fazer num PDV.
    IF NOT NEW.integrado_pdv AND NOT v_antes THEN
        RETURN NEW;
    END IF;

    v_motivo := CASE
        WHEN TG_OP = 'INSERT'                      THEN 'CRIADO'
        -- Tirar a marca é o pedido de saída: vira pendência de remoção, e é
        -- ela que o envio traduz em "desativar lá".
        WHEN v_antes AND NOT NEW.integrado_pdv     THEN 'REMOVIDO'
        WHEN NOT v_antes AND NEW.integrado_pdv     THEN 'CRIADO'
        ELSE 'ALTERADO'
    END;

    INSERT INTO pdv_pendencias (tipo, id_registro, motivo)
    VALUES (v_tipo, NEW.id, v_motivo)
    ON CONFLICT (tipo, id_registro) WHERE resolvido_em IS NULL
    -- ⚠️ Já havia pendência aberta: o motivo mais recente MANDA. Quem alterou e
    -- depois desmarcou quer sair, não quer atualizar — e o contrário também.
    DO UPDATE SET motivo = EXCLUDED.motivo, detectado_em = now();

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;


-- ⚠️ **São DOIS gatilhos por tabela, e não um, por causa do `WHEN`.**
-- `AFTER UPDATE OF nome` dispara quando a coluna é ESCRITA, mesmo que o valor
-- seja o mesmo — abrir uma categoria e salvar sem mexer em nada criava
-- pendência do nada, e a tela mandaria ao PDV um "atualize para o que já está
-- lá". O `WHEN (OLD.x IS DISTINCT FROM NEW.x)` só deixa passar mudança de
-- verdade, e ele não pode conviver com `INSERT` no mesmo gatilho porque ali
-- não existe `OLD`.
-- ⚠️ `IS DISTINCT FROM` e não `<>`: com nulo dos dois lados, `<>` é nulo e o
-- gatilho não dispararia nem quando deveria.

DROP TRIGGER IF EXISTS tg_pdv_pendencia_categoria ON categorias;
DROP TRIGGER IF EXISTS tg_pdv_pendencia_categoria_ins ON categorias;
DROP TRIGGER IF EXISTS tg_pdv_pendencia_categoria_upd ON categorias;
CREATE TRIGGER tg_pdv_pendencia_categoria_ins
    AFTER INSERT ON categorias
    FOR EACH ROW EXECUTE FUNCTION pdv_marcar_pendencia();
CREATE TRIGGER tg_pdv_pendencia_categoria_upd
    AFTER UPDATE OF nome, integrado_pdv ON categorias
    FOR EACH ROW
    WHEN (OLD.nome IS DISTINCT FROM NEW.nome
          OR OLD.integrado_pdv IS DISTINCT FROM NEW.integrado_pdv)
    EXECUTE FUNCTION pdv_marcar_pendencia();

DROP TRIGGER IF EXISTS tg_pdv_pendencia_setor ON setores;
DROP TRIGGER IF EXISTS tg_pdv_pendencia_setor_ins ON setores;
DROP TRIGGER IF EXISTS tg_pdv_pendencia_setor_upd ON setores;
CREATE TRIGGER tg_pdv_pendencia_setor_ins
    AFTER INSERT ON setores
    FOR EACH ROW EXECUTE FUNCTION pdv_marcar_pendencia();
CREATE TRIGGER tg_pdv_pendencia_setor_upd
    AFTER UPDATE OF nome, integrado_pdv ON setores
    FOR EACH ROW
    WHEN (OLD.nome IS DISTINCT FROM NEW.nome
          OR OLD.integrado_pdv IS DISTINCT FROM NEW.integrado_pdv)
    EXECUTE FUNCTION pdv_marcar_pendencia();

-- ---------------------------------------------------------------------------
-- PRODUTO — a função já sabe tratá-lo; o gatilho ainda NÃO existe
-- ---------------------------------------------------------------------------
-- ⚠️ **De propósito, e não por esquecimento.** Há 533 produtos marcados como
-- integrados. Criar o gatilho hoje faria a primeira alteração em qualquer um
-- deles gerar pendência que **ninguém consegue enviar**: não existe montador de
-- corpo de produto nem rota de envio. A tela encheria de linhas que não saem —
-- ou eu teria de escondê-las, e tabela cheia de linha invisível é pior que
-- tabela nenhuma.
--
-- Para ligar, quando o envio de produto existir, basta descomentar. Os campos
-- são os que o cardápio do PDV enxerga (`produtos/get`): descrição, grupo,
-- impressora, unidade e NCM.
--
-- CREATE TRIGGER tg_pdv_pendencia_produto_ins
--     AFTER INSERT ON produtos
--     FOR EACH ROW EXECUTE FUNCTION pdv_marcar_pendencia();
-- CREATE TRIGGER tg_pdv_pendencia_produto_upd
--     AFTER UPDATE OF nome, integrado_pdv, id_categoria, id_setor,
--                     um_estoque, ncm, codigo_barras ON produtos
--     FOR EACH ROW
--     WHEN (OLD.nome IS DISTINCT FROM NEW.nome
--           OR OLD.integrado_pdv IS DISTINCT FROM NEW.integrado_pdv
--           OR OLD.id_categoria IS DISTINCT FROM NEW.id_categoria
--           OR OLD.id_setor IS DISTINCT FROM NEW.id_setor
--           OR OLD.um_estoque IS DISTINCT FROM NEW.um_estoque
--           OR OLD.ncm IS DISTINCT FROM NEW.ncm
--           OR OLD.codigo_barras IS DISTINCT FROM NEW.codigo_barras)
--     EXECUTE FUNCTION pdv_marcar_pendencia();

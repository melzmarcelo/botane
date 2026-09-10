-- Com o envio ao PDV desligado, nada entra na fila de exportação.
--
-- 🔑 **Pedido do dono (09/09/2026):** *"quando está desmarcada a opção de enviar
-- as informações para o PDV, não gravar as informações de exportação"*.
--
-- O gatilho da 043/044 registra em `pdv_pendencias` toda mudança de categoria,
-- setor, produto e preço marcada como `integrado_pdv` — e registrava **mesmo
-- com o envio desligado**. Numa casa que não manda cadastro para o PDV (que é o
-- padrão, e a configuração real do cliente), isso é uma fila que só cresce, que
-- ninguém pode esvaziar (a rota de envio recusa com 409 quando o interruptor
-- está desligado) e que não descreve trabalho nenhum a fazer.
--
-- ⚠️ **A trava fica no GATILHO, não na aplicação.** É a razão de o gatilho
-- existir: *"quem a alimenta é o gatilho da 043 — nenhum caminho da aplicação
-- consegue esquecer, nem o que ainda vai ser escrito"*. Repetir a checagem em
-- cada rota que salva um cadastro seria repetir o esquecimento que ele veio
-- evitar — e a rota nova nasceria sem ela.
--
-- ⚠️ **Basta UMA loja com o envio ligado.** `pdv_pendencias` não tem
-- `id_unidade`: a pendência é do cadastro, e o cadastro é da rede. Se qualquer
-- loja manda cadastros ao PDV, a mudança interessa e é registrada.
--
-- ⚠️ **O que se perde ao desligar, e é de propósito:** mudança de ATIVAÇÃO
-- feita durante o período desligado não será empurrada quando alguém religar. É
-- a regra do anti-ping-pong (ver 044): *"é a mudança feita AQUI que autoriza
-- mexer no `ativo` de LÁ"* — e, sem pendência, nada é ativado ou desativado por
-- engano. Mudança de CONTEÚDO (nome, categoria, preço) continua aparecendo na
-- fila ao religar, porque a fila também compara com o que existe no PDV:
-- *"a pendência manda, mas a REALIDADE tem voto"* (`envio.fila`).
--
-- ⚠️ **A fila existente NÃO é apagada.** Ela é histórico do que já foi
-- detectado, e limpá-la aqui destruiria informação para resolver um incômodo.
-- Quem quiser zerar resolve pela tela, ou por um UPDATE consciente.

CREATE OR REPLACE FUNCTION pdv_marcar_pendencia() RETURNS trigger AS $$
DECLARE
    v_tipo      varchar(20);
    v_motivo    varchar(12);
    v_antes     boolean;
    v_id        integer;
    v_integrado boolean;
BEGIN
    -- 🔑 **A primeira pergunta, antes de qualquer trabalho.** Envio desligado
    -- em todas as lojas: não há exportação, e portanto não há o que registrar.
    IF NOT EXISTS (
        SELECT 1 FROM integracoes
         WHERE servico = 'PDV_LEGAL' AND enviar_ao_pdv
    ) THEN
        RETURN NEW;
    END IF;

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

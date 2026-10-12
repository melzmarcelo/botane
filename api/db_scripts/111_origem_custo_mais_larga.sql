-- 111 — `venda_itens.origem_custo` cabe o rótulo inteiro. Idempotente.
--
-- 🔑 **Achado em produção (11/10/2026):** a busca agendada das vendas no PDV
-- parou em 09/10 com `StringDataRightTruncation: value too long for type
-- character varying(20)`, e a manual passou a falhar junto.
--
-- A coluna nasceu com 20 (script 008), e em 02/09/2026 a ficha em RASCUNHO
-- passou a custear a venda, com dois rótulos que não cabem:
-- `ficha_rascunho_parcial` (22) e `ficha_rascunho_sem_custo` (24). Ninguém viu
-- por mais de um mês porque só aparecem quando se VENDE um prato cuja ficha em
-- rascunho está incompleta ou sem custo nenhum — e aí a transação é uma só: um
-- item assim derruba o lote inteiro, e nenhuma venda do período entra.
--
-- ⚠️ Alargar, e não encurtar o rótulo: ele é lido por nome em relatório e em
-- migração (`LIKE 'ficha%'`, na 094), e o próximo rótulo comprido repetiria a
-- história. 40 dá folga sem virar `text`.
-- ⚠️ Aumentar o tamanho de um `varchar` não reescreve a tabela.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns
                WHERE table_schema = current_schema()
                  AND table_name = 'venda_itens' AND column_name = 'origem_custo'
                  AND character_maximum_length < 40) THEN
        ALTER TABLE venda_itens ALTER COLUMN origem_custo TYPE varchar(40);
    END IF;
END $$;

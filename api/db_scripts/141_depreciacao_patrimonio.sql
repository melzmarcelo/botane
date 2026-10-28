-- 141 — Patrimônio, etapa 4: o VALOR dos bens — vida útil e depreciação. Idempotente.
--
-- 🔑 **Pedido do dono (28/10/2026):** *"pode seguir com a etapa 4 do patrimônio"* — da
-- proposta de 27/10: "valor patrimonial por setor e, se o contador quiser, depreciação
-- (valor de compra e vida útil, dando o valor atual), só como relatório".
--
-- 🔑 **Só relatório.** A depreciação é CALCULADA na consulta (`services/patrimonio_valor.py`),
-- nunca gravada mês a mês: gravada, mentiria no dia em que alguém corrigisse a data de
-- compra ou a vida útil — a mesma regra da próxima preventiva (139).
--
-- ⚠️ **Vida útil em ANOS, e vazia = o padrão** (10 anos, o da Receita para máquinas,
-- equipamentos e móveis). Gravar o padrão em cada bem esconderia quem foi escolhido de
-- propósito e quem só herdou o número.

ALTER TABLE bens ADD COLUMN IF NOT EXISTS vida_util_anos smallint;
DO $$ BEGIN
    ALTER TABLE bens ADD CONSTRAINT ck_bem_vida_util CHECK (vida_util_anos BETWEEN 1 AND 50);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- 🔑 **Quando saiu da casa.** A depreciação para na baixa, e o valor "em 31/12" ainda conta
-- o bem baixado em março do ano seguinte. Até aqui só havia o motivo.
ALTER TABLE bens ADD COLUMN IF NOT EXISTS data_baixa date;

-- ⚠️ **É GATILHO, como o 036, e pela mesma razão:** a baixa é escrita em QUATRO lugares
-- (a ficha, o fechamento da conferência, a importação da planilha e o conector), e o
-- quinto nasceria sem a data. Baixado sem data → hoje (a sessão está no fuso da casa);
-- saiu do baixado → a data some, senão o bem reativado pararia de depreciar.
CREATE OR REPLACE FUNCTION bem_data_baixa() RETURNS trigger AS $$
BEGIN
    IF NEW.situacao = 'BAIXADO' THEN
        IF NEW.data_baixa IS NULL THEN
            NEW.data_baixa := current_date;
        END IF;
    ELSE
        NEW.data_baixa := NULL;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS tg_bem_data_baixa ON bens;
CREATE TRIGGER tg_bem_data_baixa
    BEFORE INSERT OR UPDATE OF situacao, data_baixa ON bens
    FOR EACH ROW EXECUTE FUNCTION bem_data_baixa();

-- Os que já estavam baixados: a última alteração é a melhor data que se tem.
UPDATE bens SET data_baixa = atualizado_em::date
 WHERE situacao = 'BAIXADO' AND data_baixa IS NULL;

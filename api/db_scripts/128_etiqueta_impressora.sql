-- A impressora e o rolo da etiqueta, por loja.
--
-- 🔑 **Pedido do dono (22/10/2026):** *"na impressão das etiquetas, gostaria que fosse
-- impressa diretamente na impressora de etiquetas do cliente"* — uma Brother QL-810W — e
-- *"na configuração das etiquetas podemos colocar qual impressora vamos utilizar com
-- seleção, hoje podemos ter a PDF e esta nova de etiquetas. Aí podemos ter a seleção do
-- tipo de rolo também, isto facilita para futuras impressoras."*
--
-- O catálogo (que impressoras existem e que rolos cada uma aceita) mora no código, em
-- `services/etiquetas.py` (IMPRESSORAS): aqui fica só a ESCOLHA da loja. Por isso `rolo`
-- não tem CHECK — quem valida é o modelo, contra o catálogo.
-- ⚠️ `tamanho` continua sendo o da impressora PDF: quem já tinha modelo salvo segue
-- imprimindo exatamente como antes (o padrão da coluna nova é 'PDF').
-- Idempotente.

ALTER TABLE etiqueta_config
    ADD COLUMN IF NOT EXISTS impressora varchar(20) NOT NULL DEFAULT 'PDF';
ALTER TABLE etiqueta_config ADD COLUMN IF NOT EXISTS rolo varchar(20);
-- Só no rolo CONTÍNUO: o comprimento de cada etiqueta, que o rolo não define.
ALTER TABLE etiqueta_config ADD COLUMN IF NOT EXISTS comprimento_mm smallint;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'etiqueta_config_impressora_check') THEN
        ALTER TABLE etiqueta_config ADD CONSTRAINT etiqueta_config_impressora_check
            CHECK (impressora IN ('PDF', 'BROTHER_QL'));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'etiqueta_config_comprimento_check') THEN
        ALTER TABLE etiqueta_config ADD CONSTRAINT etiqueta_config_comprimento_check
            CHECK (comprimento_mm IS NULL OR comprimento_mm BETWEEN 20 AND 200);
    END IF;
END $$;

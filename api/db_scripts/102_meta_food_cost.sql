-- A meta de food cost da loja: a marca na régua do Início.
--
-- 🔑 Pedido do dono (29/09/2026), junto com a tela inicial nova ("pode implementar conforme
-- o protótipo" — `apresentacao/inicio-prototipo.html`). Percentual; NULO = sem meta, e a
-- régua aparece sem a marca. Idempotente.
ALTER TABLE parametros ADD COLUMN IF NOT EXISTS meta_food_cost_pct numeric(5,2);
DO $$ BEGIN
    ALTER TABLE parametros ADD CONSTRAINT ck_parametros_meta_food_cost
        CHECK (meta_food_cost_pct IS NULL OR meta_food_cost_pct BETWEEN 0 AND 100);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

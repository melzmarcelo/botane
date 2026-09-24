-- Fidelidade: o check-in só conta com o cliente NA CASA, pela localização do celular.
--
-- 🔑 **Pedido do dono (24/09/2026):** *"tem como validar a localização ao ler o QR code e
-- contar a visita? … pode implementar a localização configurável."* A brecha que o token
-- e o horário deixavam: quem fotografou o QR marca a visita do sofá, em dia de semana,
-- com a casa aberta.
--
-- ⚠️ **Quem decide é o SERVIDOR**: o site manda a posição, a API mede a distância até a
-- loja. Conferir no navegador seria conferir no aparelho de quem quer burlar.
-- ⚠️ **Não se guarda a posição do cliente** — só a distância em metros de cada check-in,
-- que é o que a auditoria precisa ("contou a 35 m da casa").
-- Idempotente.

-- As coordenadas da LOJA. `numeric(9,6)` dá ~10 cm — sobra para um raio de 200 m.
ALTER TABLE unidades ADD COLUMN IF NOT EXISTS latitude  numeric(9, 6);
ALTER TABLE unidades ADD COLUMN IF NOT EXISTS longitude numeric(9, 6);

-- 🔑 Ligada por padrão, como o dono aprovou. ⚠️ Com ela ligada e a loja SEM
-- coordenadas, o check-in é recusado com a frase dizendo o porquê — e a tela de
-- configuração avisa antes. A fidelidade ainda não está ligada em loja nenhuma.
ALTER TABLE fidelidade_config ADD COLUMN IF NOT EXISTS exige_local boolean NOT NULL DEFAULT true;
ALTER TABLE fidelidade_config ADD COLUMN IF NOT EXISTS raio_m integer NOT NULL DEFAULT 200;
DO $$ BEGIN
    ALTER TABLE fidelidade_config ADD CONSTRAINT ck_fidelidade_raio CHECK (raio_m BETWEEN 30 AND 5000);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

ALTER TABLE fidelidade_checkins ADD COLUMN IF NOT EXISTS distancia_m integer;

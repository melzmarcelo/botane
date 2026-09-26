-- Fidelidade: o prêmio vale a partir da PRÓXIMA visita.
--
-- 🔑 **Pedido do dono (24/09/2026):** *"a cada 10, no próximo é grátis e não vale o
-- carimbo."* Duas regras: (1) o prêmio que nasce no 10º check-in só pode ser consumido
-- a partir do dia seguinte; (2) a visita em que ele é consumido não conta carimbo
-- (essa mora no serviço, `services/fidelidade.py`).
--
-- `vale_de` fica GRAVADO no prêmio, como a validade e os dias de consumo: é regra que
-- o cliente leu quando ganhou, e não muda depois.
-- Idempotente: o preenchimento só toca os prêmios que ainda não têm a data.

ALTER TABLE fidelidade_premios ADD COLUMN IF NOT EXISTS vale_de date;

UPDATE fidelidade_premios
   SET vale_de = (emitido_em AT TIME ZONE 'America/Sao_Paulo')::date + 1
 WHERE vale_de IS NULL;

ALTER TABLE fidelidade_premios ALTER COLUMN vale_de SET NOT NULL;

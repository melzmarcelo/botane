-- O aceite do termo de consentimento (LGPD) no cadastro do cliente pelo site.
--
-- 🔑 **Pedido do dono (24/09/2026):** *"no cadastro de cliente, adicionar o item
-- Estou de acordo com o termo de consentimento … para seguir o cadastro é
-- necessário ter marcado."*
--
-- ⚠️ **Grava QUANDO e QUAL versão**, não só "aceitou". Consentimento é prova: se
-- o texto mudar, o cadastro antigo continua dizendo a que texto disse sim. O
-- texto de cada versão mora em `services/termo_consentimento.py`.
-- ⚠️ Nulo nos cadastros de antes deste dia — eles não viram termo nenhum, e
-- preencher agora seria afirmar um aceite que não aconteceu.
-- Idempotente.

ALTER TABLE reserva_clientes ADD COLUMN IF NOT EXISTS termo_aceito_em timestamptz;
ALTER TABLE reserva_clientes ADD COLUMN IF NOT EXISTS termo_versao varchar(20);

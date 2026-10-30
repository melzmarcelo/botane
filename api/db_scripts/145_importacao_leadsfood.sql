-- 145 — A importação do LeadsFood (o sistema de leads que a casa usava antes do Portal).
--
-- 🔑 Pedido do dono (30/10/2026): "siga para a importação do LeadsFood". Contatos, reservas,
-- selos em aberto e prêmios entram por Portal de Clientes → Clientes → Importar do LeadsFood.
-- Leitura do sistema antigo: docs/leadsfood-analise.md.
--
-- ⚠️ Idempotente: só ADD COLUMN IF NOT EXISTS e CREATE INDEX IF NOT EXISTS. Não reescreve dado.

-- O cadastro ganha o que o LeadsFood sabia e o Botané ainda não guardava.
ALTER TABLE reserva_clientes ADD COLUMN IF NOT EXISTS email       varchar(160);
ALTER TABLE reserva_clientes ADD COLUMN IF NOT EXISTS uf          varchar(2);
-- De onde o cliente veio (no LeadsFood: Conversão, Fidelidade, Reservas, Avaliações).
ALTER TABLE reserva_clientes ADD COLUMN IF NOT EXISTS origem      varchar(40);
-- As etiquetas ("Cardápio - Link bio", "Catálogo de Cestas"…): várias por cliente.
ALTER TABLE reserva_clientes ADD COLUMN IF NOT EXISTS etiquetas   text[] NOT NULL DEFAULT '{}';

-- 🔑 **`importado_de` marca o que veio de fora** — é o que deixa repetir a importação: o que
-- tem a marca pode ser atualizado ou retirado por uma importação nova; o que nasceu aqui, não.
ALTER TABLE reserva_clientes    ADD COLUMN IF NOT EXISTS importado_de varchar(20);
ALTER TABLE reservas            ADD COLUMN IF NOT EXISTS importado_de varchar(20);
ALTER TABLE fidelidade_checkins ADD COLUMN IF NOT EXISTS importado_de varchar(20);
ALTER TABLE fidelidade_premios  ADD COLUMN IF NOT EXISTS importado_de varchar(20);

-- 🔑 **A idempotência é do BANCO** (regra 8). O arquivo do LeadsFood não traz id de reserva
-- nem de prêmio: a chave é o que identifica cada um lá — a reserva pela loja, telefone, dia e
-- hora; o prêmio pelo cliente e a validade. Só para o que foi importado: as reservas daqui
-- podem repetir telefone e horário (remarcação, duas mesas).
CREATE UNIQUE INDEX IF NOT EXISTS ux_reserva_importada
    ON reservas (id_unidade, telefone, data, hora) WHERE importado_de IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS ux_fidelidade_premio_importado
    ON fidelidade_premios (id_cliente, vence_em) WHERE importado_de IS NOT NULL;

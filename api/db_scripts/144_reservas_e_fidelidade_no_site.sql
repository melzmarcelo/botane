-- Reservas e Fidelidade VISÍVEIS no site: a casa escolhe se o botão aparece.
--
-- 🔑 **Pedido do dono (30/10/2026):** *"nas configurações das reservas, criar uma opção se as
-- reservas vão estar visíveis no site. Fazer isto também para a Fidelidade. Caso desmarcado, não
-- aparecerá o botão desta ação."*
-- ⚠️ **Esconder não é desligar.** As reservas continuam na agenda do balcão, e o QR da mesa
-- continua contando visitas quando "Utiliza Fidelidade" está ligado — só some o botão do site.
-- 🔑 Padrão LIGADO: o site que já está no ar continua igual até a casa desmarcar.
-- Idempotente.
ALTER TABLE reserva_config ADD COLUMN IF NOT EXISTS reservas_no_site boolean NOT NULL DEFAULT true;
ALTER TABLE reserva_config ADD COLUMN IF NOT EXISTS fidelidade_no_site boolean NOT NULL DEFAULT true;

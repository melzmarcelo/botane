-- A data de nascimento de quem reserva, e o catálogo que pede cadastro para abrir.
--
-- 🔑 **Pedido do dono (24/09/2026):** *"adicionar data de nascimento no cadastro
-- do cliente em Reservas. Adicionar a validação do cliente ao acessar o
-- catálogo, colocar no cadastro do catálogo se exige cadastro."*
--
-- ⚠️ **A data de nascimento estava prevista desde a 068 e tinha saído de
-- propósito** em 21/09: dado pessoal só entra no dia em que a casa for usá-lo.
-- Esse dia chegou — é pedido explícito do dono.
-- ⚠️ **Nula para quem já tem cadastro**: ninguém sabe a data de quem se
-- cadastrou antes, e inventar uma seria pior que o vazio. O site a completa na
-- visita seguinte, sem sobrescrever o que já estiver lá.

ALTER TABLE reserva_clientes ADD COLUMN IF NOT EXISTS nascimento date;

-- ⚠️ **Nasce DESLIGADO**: todo catálogo que já está no ar continua abrindo como
-- sempre abriu. Ligar é decisão da casa, catálogo a catálogo.
ALTER TABLE catalogos
    ADD COLUMN IF NOT EXISTS exige_cadastro boolean NOT NULL DEFAULT false;

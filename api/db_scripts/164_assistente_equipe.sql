-- 164 — O assistente pelo WhatsApp, etapa 6: os avisos à EQUIPE (reserva nova e pedido novo).
--
-- 🔑 Pedido do dono (25/11/2026): *"o cliente reserva uma mesa, o sistema avisa o cliente e também
-- o WhatsApp da loja, que confirma … pode realizar ações na reserva pelo sistema ou pelo próprio
-- WhatsApp"* — e o mesmo para os pedidos do site. Decisões: quem recebe são os USUÁRIOS
-- vinculados ao assistente (o botão age com a permissão de quem tocou); o número é o MESMO dos
-- avisos a clientes (o assistente pode usar um número de loja — ver `assistente.conexao`); e as
-- reservas do dia entram no bom dia.
--
-- A configuração da casa (ligado, nome do modelo de cada aviso) mora no `config` da integração do
-- assistente; aqui só a escolha de cada pessoa. Desligado por padrão: ninguém passa a receber
-- mensagem sem pedir. Idempotente.

ALTER TABLE usuario_whatsapp ADD COLUMN IF NOT EXISTS avisos_reserva boolean NOT NULL DEFAULT false;
ALTER TABLE usuario_whatsapp ADD COLUMN IF NOT EXISTS avisos_pedido boolean NOT NULL DEFAULT false;

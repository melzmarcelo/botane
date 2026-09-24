-- O módulo "Reservas" passa a se chamar "Portal de Clientes".
--
-- 🔑 **Pedido do dono (24/09/2026):** *"alterar o módulo Reservas para Portal de
-- Clientes, tanto em textos gerais e também na configuração de ativação."* O
-- módulo cresceu além da mesa: é tudo o que o cliente vê no site — reserva,
-- cardápios, cadastro e contato.
--
-- ⚠️ **Muda só o NOME que a tela mostra** no catálogo de permissões. As chaves
-- (`reservas.*`, `catalogos.*`) ficam: renomear chave reescreveria os papéis de
-- todo mundo, e quem já concedeu `reservas.ver` a alguém não pediu para mexer
-- nisso. Pelo mesmo motivo `parametros.reservas_ligado` não muda de nome.
-- Idempotente: na segunda passada não há mais 'Reservas' para trocar.

UPDATE permissoes SET modulo = 'Portal de Clientes' WHERE modulo = 'Reservas';

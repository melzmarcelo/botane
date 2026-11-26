-- 168 — A nota RECEBIDA: a mercadoria chegou, e o Omie ainda não deu o recebimento.
-- Idempotente. Três colunas novas em `notas_entrada`; nenhum dado existente muda.
--
-- 🔑 Pedido do dono (26/11/2026): "quando no Omie estiver desmarcada a opção Somente recebidos,
-- vamos criar uma nova situação na nota, a situação Recebido. A nota vem do Omie como Conciliada,
-- aí o usuário vai ter a opção de marcar ela como Recebida, onde depois outro usuário pode
-- verificar as recebidas e no Omie fazer o recebimento dela, aí ela vem para o sistema como
-- Lançada. Ao marcar como recebida, vai abrir uma tela para o usuário informar o nome de quem
-- recebeu, informação obrigatória. Aí esta informação fica na nota também."
--
-- 🔑 O status novo é `RECEBIDA` (cabe no varchar(20) da 126). Quem recebeu é TEXTO digitado
-- (`recebido_por`) — quem recebe na porta nem sempre tem usuário no sistema; o usuário que
-- marcou fica à parte (`recebido_id_usuario`).
-- ⚠️ As colunas FICAM depois do lançamento: é a informação da nota. E é por elas que o
-- recálculo e o estorno sabem devolver a nota a RECEBIDA, e não a CONCILIADA.

ALTER TABLE notas_entrada ADD COLUMN IF NOT EXISTS recebido_por varchar(120);
ALTER TABLE notas_entrada ADD COLUMN IF NOT EXISTS recebido_em timestamptz;
ALTER TABLE notas_entrada ADD COLUMN IF NOT EXISTS recebido_id_usuario integer REFERENCES usuarios(id);

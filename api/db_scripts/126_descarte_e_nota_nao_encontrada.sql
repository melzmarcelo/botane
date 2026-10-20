-- 126 · O motivo Descarte e a nota que sumiu do Omie (1.1.114).
--
-- 🔑 Pedido do dono (20/10/2026): "Incluir o motivo Descarte no ajuste por Perda". Entra
-- na lista de motivos como os outros; quem já tem um "Descarte" cadastrado não ganha outro
-- (o índice é por `lower(nome)`).
-- 🔑 Pedido do dono (20/10/2026): "notas lançadas [no Omie] e por algum motivo elas foram
-- excluídas ... ao atualizar, devem ficar com um status de não encontrada no Omie. E ficar
-- igual a cancelada, sem poder lançar." O status novo é `NAO_ENCONTRADA` — catorze letras,
-- e a coluna era varchar(12).
-- ⚠️ Idempotente: o motivo entra só se faltar, e alargar o varchar é só metadado no
-- Postgres (nenhuma linha é reescrita). Nenhum dado existente muda.

INSERT INTO perda_motivos (nome)
SELECT 'Descarte'
 WHERE NOT EXISTS (SELECT 1 FROM perda_motivos WHERE lower(nome) = 'descarte');

ALTER TABLE notas_entrada ALTER COLUMN status TYPE varchar(20);

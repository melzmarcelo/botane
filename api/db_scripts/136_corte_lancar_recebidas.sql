-- 136 — O CORTE de data do "lançar notas recebidas". Idempotente.
--
-- 🔑 **Pedido do dono (27/10/2026):** com a 1.1.139 o lançamento automático passou a
-- valer também para as notas que já esperavam — e no ar havia 17 abertas, várias de
-- equipamento e obra (refrigeração, vidros), que ninguém lançou de propósito. O dono
-- escolheu o corte: *"pode fazer o corte de data a partir de 01/10"*.
--
-- Só a nota com data de ENTRADA (ou de emissão, sem ela) a partir do corte é lançada
-- sozinha; as anteriores ficam na fila, para lançar à mão. Nulo = sem corte.
-- ⚠️ O estorno do recebimento desfeito no Omie NÃO olha o corte: ele só toca nota que
-- o próprio sistema (ou alguém) lançou, e desfazer o que o Omie desfez vale sempre.
ALTER TABLE integracoes ADD COLUMN IF NOT EXISTS lancar_recebidas_corte date;

-- O corte escolhido pelo dono, para a linha do Omie que já existe. ⚠️ Só onde está
-- nulo: rodar de novo não desfaz uma data que alguém mudou na tela.
UPDATE integracoes SET lancar_recebidas_corte = DATE '2026-10-01'
 WHERE servico = 'OMIE' AND lancar_recebidas_corte IS NULL;

COMMENT ON COLUMN integracoes.lancar_recebidas_corte IS
    'Lançar notas recebidas: só nota com entrada a partir desta data. Nulo = sem corte.';

-- Botané 130 — notas do Omie: só as recebidas, e lançar as recebidas. Idempotente.
--
-- 🔑 Pedido do dono (23/10/2026): "Criar dois parametros no Omie. 1-Lançar notas
-- recebidas (ao puxar uma nota recebida, já fazer o lançamento no estoque)
-- 2-Somente recebidas (irá buscar somente as notas recebidas)".
--
-- "Recebida" é a marca `cRecebido = "S"` que o Omie manda em `infoCadastro` de
-- cada recebimento (conferida no ar em 23/10/2026: a NF 30018 veio com etapa 40,
-- faturada e NÃO recebida; a 3040633 com etapa 80, faturada e recebida). A marca,
-- e não o número da etapa: o de-para dos códigos de etapa não está documentado.
--
-- ⚠️ **As duas nascem FALSAS**: é o comportamento de hoje, e uma migração não muda
-- o que a casa já faz.

ALTER TABLE integracoes
    ADD COLUMN IF NOT EXISTS so_recebidas boolean NOT NULL DEFAULT false;

ALTER TABLE integracoes
    ADD COLUMN IF NOT EXISTS lancar_recebidas boolean NOT NULL DEFAULT false;

-- 🔑 **Desde quando lançar.** Só nota IMPORTADA depois de ligar a opção é lançada
-- sozinha. No ar havia 29 notas conciliadas esperando o clique — ligar a opção não
-- pode despejá-las no razão (append-only) sem ninguém olhar. Para elas existe o
-- "lançar as conciliadas", com prévia. Desligar limpa; religar recomeça a contar.
ALTER TABLE integracoes
    ADD COLUMN IF NOT EXISTS lancar_recebidas_desde timestamptz;

-- ⚠️ **A nota não recebida que ficou para trás.** Com "somente recebidas" ela não é
-- gravada — então nada aqui lembra dela, e a janela automática (última busca menos
-- 7 dias) a perderia se o recebimento demorar mais que isso. Guarda-se a data da
-- mais antiga que esperava recebimento na última busca, e a próxima varre desde ela
-- (até 60 dias). Nulo = nenhuma esperando.
ALTER TABLE integracoes
    ADD COLUMN IF NOT EXISTS aguardando_recebimento_desde date;

-- O relógio da sincronização de CADASTROS do PDV.
--
-- 🔑 A busca de vendas passou a trazer o cardápio junto (01/09/2026, pedido do
-- dono): prato novo no PDV nasce aqui, e prato desligado lá é desativado aqui.
-- Mas a agenda pode rodar de HORA EM HORA, e ler os 630 itens do cardápio 24
-- vezes por dia para achar um prato novo é caro sem ser mais útil — prato novo
-- não nasce de hora em hora.
--
-- ⚠️ Coluna PRÓPRIA, e não `ultima_sincronizacao`: aquela é o relógio das
-- VENDAS e avança a cada busca. Usá-la aqui faria o cardápio ser lido em toda
-- busca (é o que se quer evitar) ou nunca mais (se a comparação fosse pelo dia).
-- É a mesma lição do `agenda_rodou_em`, que existe porque
-- `ultima_sincronizacao` só avança quando alguma nota chega.
--
-- ⚠️ Idempotente, como todo script daqui.

ALTER TABLE integracoes
    ADD COLUMN IF NOT EXISTS cardapio_em timestamptz;

COMMENT ON COLUMN integracoes.cardapio_em IS
    'Quando os cadastros do cardápio foram sincronizados pela última vez. '
    'A agenda faz isso no primeiro disparo do dia; o botão faz sempre.';

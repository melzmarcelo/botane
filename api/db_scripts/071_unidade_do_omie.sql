-- A unidade em que o OMIE cadastrou o produto — e por que ela precisa existir.
--
-- 🔑 **O custo vinha de lá sem dizer em que unidade estava** (15/09/2026,
-- relatado pelo dono: *"o custo também ficou estranho"*). O `ListarPosEstoque`
-- traz o CMC e nada mais: nem a unidade. Quando o produto nasce da importação,
-- `um_estoque` É a unidade do Omie e os dois coincidem — mas basta alguém
-- corrigir a unidade aqui (o bloco de 5 KG virando KG, que é o caso real) para
-- o CMC passar a ser gravado como se fosse por quilo.
--
-- O efeito, medido na base: a MANTEIGA SEM SAL ficou a **R$ 315,00/KG**, que é
-- o preço do bloco inteiro. Cinco vezes o custo real, alimentando toda ficha
-- que a usa, o CMV teórico e a margem — sem nada denunciando.
--
-- ⚠️ **Nasce NULA e é preenchida pela próxima importação de catálogo.** Nulo
-- quer dizer "não sei", e aí o custo entra como entrava — nenhum
-- comportamento muda para quem não importar de novo. Preencher agora com
-- `um_estoque` seria afirmar que ninguém nunca mexeu na unidade, que é
-- exatamente a suposição que criou o problema.
ALTER TABLE produtos ADD COLUMN IF NOT EXISTS um_omie varchar(6);

COMMENT ON COLUMN produtos.um_omie IS
    'Unidade em que o produto está cadastrado no Omie. O CMC de lá é nessa '
    'unidade; o custo daqui é por um_estoque. Nulo = desconhecida.';

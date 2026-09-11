-- Botané 064 — o custo médio passa a ser da LOJA, não da prateleira. Idempotente.
--
-- 🔑 **Pedido do dono (11/09/2026):** "hoje temos produto com custo em um local,
-- porém em outros locais não tem. gostaria que neste primeiro momento o custo
-- fosse geral".
--
-- O médio sempre foi por `(unidade, local, produto)` — uma linha de
-- `estoque_saldos` por prateleira, cada uma com o seu custo. Isso tem sentido
-- para quem compra a mesma coisa por preços diferentes em depósitos diferentes,
-- e é o que a casa NÃO faz: aqui o mesmo açúcar está na despensa e no bar, veio
-- da mesma nota, e custa a mesma coisa. O efeito prático era o produto ter custo
-- numa prateleira e ZERO na outra — e a saída pela prateleira sem custo sair de
-- graça, que é o mesmo defeito de custo zero que este projeto já perseguiu três
-- vezes por outros caminhos.
--
-- ⚠️ **Falso é o padrão, e isso MUDA o comportamento de quem já está rodando.**
-- É o pedido: o primeiro momento é geral. Quem precisar do custo por prateleira
-- liga a chave na tela de Lojas — a coluna existe justamente para essa escolha
-- não virar um `if` escondido no código.
--
-- ⚠️ **Esta migração NÃO reavalia estoque nenhum.** Ela só cria a chave. Unificar
-- o custo dos produtos que já existem muda quanto o estoque vale, e portanto o
-- CMV do período — isso é um LANÇAMENTO (`AJUSTE_CUSTO`, migração 039), com
-- prévia e um lote que explica de onde veio, não um `UPDATE` calado no meio de
-- uma migração. A tela de Estoque tem o botão.
ALTER TABLE parametros
    ADD COLUMN IF NOT EXISTS custo_por_local boolean NOT NULL DEFAULT false;

COMMENT ON COLUMN parametros.custo_por_local IS
    'false (padrão): o custo médio é um só por produto na loja — toda prateleira '
    'mostra e movimenta o mesmo número. true: cada local tem o seu médio, como '
    'era até a migração 064.';

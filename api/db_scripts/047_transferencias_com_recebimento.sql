-- Botané 047 — a transferência entre lojas passa a ter REMESSA e RECEBIMENTO.
-- Idempotente.
--
-- 🔑 **Entre lojas, a mercadoria leva tempo no caminho — e o sistema dizia que
-- ela já tinha chegado.** Saída e entrada eram gravadas na mesma transação: o
-- carro saía hoje e chegava amanhã, e a filial já aparecia com o produto na
-- prateleira. Pior, quem recebia não conferia nada — chegando menos, a
-- diferença só apareceria na contagem seguinte como *ajuste de inventário*,
-- que é exatamente onde a diferença some sem nome.
--
-- 🔑 **A decisão difícil não é a tela, é de QUEM é o valor no caminho.** Se a
-- saída acontecesse no envio e a entrada só no recebimento, o valor sumiria das
-- duas lojas nesse intervalo e o CMV da origem sairia inflado — um buraco que
-- nenhum relatório explicaria. Por isso o envio **não escreve no razão**: a
-- quantidade continua contando no estoque da ORIGEM, agora marcada como em
-- trânsito. Os dois movimentos nascem juntos no recebimento, como sempre
-- nasceram, e a identidade `inicial + entradas − saídas = final` continua
-- fechando nas duas lojas em qualquer data de corte.
--
-- ⚠️ **Dentro da MESMA loja nada muda.** Prateleira para prateleira da mesma
-- casa não tem trânsito: alguém carrega a caixa e pronto. Continua imediata,
-- pelo caminho de sempre. Exigir recebimento ali seria burocracia inventada.
--
-- ⚠️ **Cancelar remessa em trânsito não estorna nada** — nada foi lançado. É a
-- vantagem silenciosa deste desenho: o arrependimento não deixa rastro no razão
-- (o append-only obrigaria a um par de movimentos que não corresponderam a
-- nada que aconteceu).

CREATE TABLE IF NOT EXISTS transferencias (
    id                      serial PRIMARY KEY,
    id_unidade_origem       integer NOT NULL REFERENCES unidades(id),
    id_local_origem         integer NOT NULL REFERENCES locais_estoque(id),
    id_unidade_destino      integer NOT NULL REFERENCES unidades(id),
    id_local_destino        integer NOT NULL REFERENCES locais_estoque(id),
    -- EM_TRANSITO → RECEBIDA | CANCELADA. Sem CHECK, pela mesma razão de
    -- `produtos.tipo`: estado novo é migração de dado, não alteração de tabela.
    status                  varchar(20) NOT NULL DEFAULT 'EM_TRANSITO',
    observacao              text,
    enviada_em              timestamptz NOT NULL DEFAULT now(),
    id_usuario_envio        integer NOT NULL REFERENCES usuarios(id),
    recebida_em             timestamptz,
    id_usuario_recebimento  integer REFERENCES usuarios(id),
    observacao_recebimento  text,
    cancelada_em            timestamptz,
    id_usuario_cancelamento integer REFERENCES usuarios(id)
);

CREATE TABLE IF NOT EXISTS transferencia_itens (
    id                  serial PRIMARY KEY,
    id_transferencia    integer NOT NULL REFERENCES transferencias(id) ON DELETE CASCADE,
    id_produto          integer NOT NULL REFERENCES produtos(id),
    qtd_enviada         numeric(18,4) NOT NULL,
    -- Nula enquanto em trânsito: "ainda não conferido" e "conferido, veio
    -- zero" são coisas diferentes, e zero não pode responder pelas duas.
    qtd_recebida        numeric(18,4),
    -- 🔑 **Os três movimentos que o recebimento gera.** A perda existe porque
    -- a mercadoria que não chegou saiu da prateleira da origem do mesmo jeito:
    -- transferir só o que chegou deixaria a origem com um saldo que ela não
    -- tem, e a próxima contagem cobriria o buraco como ajuste anônimo. Como
    -- PERDA ela tem nome e aparece na linha do CMV que se cobra de alguém.
    id_movimento_saida  integer REFERENCES estoque_movimentos(id),
    id_movimento_entrada integer REFERENCES estoque_movimentos(id),
    id_movimento_perda  integer REFERENCES estoque_movimentos(id),
    observacao          text,
    UNIQUE (id_transferencia, id_produto)
);

-- A pergunta cara é sempre "o que está em trânsito?", e ela é feita por loja —
-- de saída, na tela de quem mandou; de chegada, na de quem espera.
CREATE INDEX IF NOT EXISTS ix_transferencia_origem
    ON transferencias (id_unidade_origem, status);
CREATE INDEX IF NOT EXISTS ix_transferencia_destino
    ON transferencias (id_unidade_destino, status);
-- "Quanto deste produto está em trânsito, saindo desta prateleira?" — é o
-- número que a tela de saldos mostra ao lado do saldo.
CREATE INDEX IF NOT EXISTS ix_transferencia_item_produto
    ON transferencia_itens (id_produto);


-- ---------------------------------------------------------------------------
-- Receber é outro trabalho, feito por outra pessoa
-- ---------------------------------------------------------------------------
-- 🔑 **Quem manda está numa loja; quem confere, na outra.** Com uma chave só,
-- quem recebe a remessa poderia também despachar mercadoria da casa — e a
-- conferência perderia o sentido, porque conferente e remetente seriam a mesma
-- permissão. Mesma separação do inventário (045).
--
-- ⚠️ **A chave nova é a de RECEBER, não a de enviar** — quem transfere hoje
-- continua transferindo, e ganha o recebimento de graça. Invertida, o deploy
-- tiraria de todo mundo uma coisa que fazia ontem.
INSERT INTO permissoes (chave, modulo, descricao, ordem) VALUES
    ('estoque.transferencia_receber', 'Estoque',
     'Conferir e receber remessa de outra loja', 351)
ON CONFLICT (chave) DO NOTHING;

INSERT INTO papel_permissoes (id_papel, chave)
SELECT pp.id_papel, 'estoque.transferencia_receber'
  FROM papel_permissoes pp
 WHERE pp.chave = 'estoque.transferencias'
ON CONFLICT DO NOTHING;

-- Botané 042 — a fila de envio ao PDV: o histórico e o de-para do setor.
-- Idempotente.
--
-- Medido contra a conta REAL em 29/08/2026, e cada linha abaixo sai de um
-- achado, não de suposição:
--
-- 1. `grupoprodutos` tem **`codRefExterna`** — o PDV guarda o NOSSO id, e
--    `GET grupoprodutos/get/{nosso_id}` responde. Por isso categoria **não
--    precisa** de coluna de código aqui: o de-para mora lá.
-- 2. `impressoras` tem só `{codigo, nome, kds}` — **sem `codRefExterna` e sem
--    `ativo`**. Setor, então, precisa guardar o código DELES deste lado.
-- 3. `save` devolve o id criado (`{"id":465198,...}`), o que permite gravar o
--    de-para na hora, sem uma segunda leitura.
-- 4. **`delete` é DESATIVAR**, não excluir: o registro continua na lista com
--    `ativo: false`. "Enviar exclusão" é desativar lá.

ALTER TABLE setores
    ADD COLUMN IF NOT EXISTS codigo_pdv varchar(40);

-- ⚠️ Único, mas só entre os preenchidos: dois setores não podem apontar para a
-- mesma impressora, e a maioria não aponta para nenhuma.
CREATE UNIQUE INDEX IF NOT EXISTS ux_setor_codigo_pdv
    ON setores (codigo_pdv) WHERE codigo_pdv IS NOT NULL;

-- ---------------------------------------------------------------------------
-- O histórico dos envios
-- ---------------------------------------------------------------------------
-- 🔑 **Esta tabela é o que FOI, nunca o que falta.** A tentação é manter aqui
-- uma fila com estado "pendente", marcada quando alguém salva um cadastro. É a
-- armadilha do 036 ao contrário: o nome de um produto é escrito em cinco
-- lugares, e uma fila mantida à mão precisaria ser alimentada nos cinco — o
-- sexto, que vai existir, nasceria sem ela, e o registro mudaria aqui sem
-- nunca aparecer como pendente.
--
-- Então **pendente é uma CONSULTA**: está marcado para integrar E (nunca foi
-- enviado OU a impressão do que seria enviado agora difere da do último envio
-- que deu certo). Assim a fila está sempre certa, venha a mudança de onde vier
-- — inclusive de uma tela que ainda não foi escrita.

CREATE TABLE IF NOT EXISTS pdv_envios (
    id             bigserial PRIMARY KEY,
    id_unidade     integer NOT NULL REFERENCES unidades(id),
    tipo           varchar(20) NOT NULL,   -- CATEGORIA | SETOR | PRODUTO
    id_registro    integer NOT NULL,       -- o id daqui
    acao           varchar(12) NOT NULL,   -- CRIAR | ATUALIZAR | DESATIVAR
    estado         varchar(8)  NOT NULL,   -- OK | ERRO
    -- A impressão do corpo enviado. É ela que responde "mudou desde o último
    -- envio?" sem comparar campo a campo — e sem esquecer o campo novo que
    -- alguém acrescentar amanhã.
    impressao      varchar(64),
    enviado        jsonb,                  -- o corpo que foi mandado
    resposta       jsonb,                  -- o que voltou
    erro           text,                   -- a mensagem, quando deu errado
    codigo_pdv     varchar(40),            -- o código de lá, quando ele volta
    id_usuario     integer REFERENCES usuarios(id),
    criado_em      timestamptz NOT NULL DEFAULT now()
);

-- A pergunta que a fila faz o tempo todo: "qual foi o último envio OK deste
-- registro?". Sem o índice ela varre o histórico inteiro a cada linha da tela.
CREATE INDEX IF NOT EXISTS ix_pdv_envios_registro
    ON pdv_envios (id_unidade, tipo, id_registro, id DESC);

-- E a aba de erros: "o que falhou e ainda não foi refeito".
CREATE INDEX IF NOT EXISTS ix_pdv_envios_estado
    ON pdv_envios (id_unidade, estado, id DESC);

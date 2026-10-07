-- 107 — Etiquetas: consumir uma PARTE do pote. Idempotente.
--
-- 🔑 **Pedido do dono (06/10/2026):** *"temos somente como descartar ou baixar
-- tudo, tem como consumir partes?"* A etiqueta só saía inteira — "usei tudo" ou
-- "descartar" —, e o pote de 2 kg do qual se tirou 300 g não tinha o que dizer.
--
-- 🔑 **`quantidade` passa a ser o que RESTA; `quantidade_inicial` guarda o que
-- nasceu.** Mexer no sentido de `quantidade` (em vez de criar uma coluna
-- "restante") é de propósito: tudo que já lê essa coluna — o descarte, a
-- reimpressão, o painel, dividir o pote — passa a enxergar o que há no pote
-- AGORA sem mudar uma linha. O descarte de um pote meio usado lança como perda
-- só o que sobrou, que é o certo.

ALTER TABLE etiquetas
    ADD COLUMN IF NOT EXISTS quantidade_inicial numeric(14,4);

-- ⚠️ Só onde ainda está nula: rodar de novo não desfaz o consumo já registrado
-- (depois da primeira retirada, `quantidade` < `quantidade_inicial`, e copiar de
-- novo apagaria essa diferença).
UPDATE etiquetas
   SET quantidade_inicial = quantidade
 WHERE quantidade_inicial IS NULL AND quantidade IS NOT NULL;

COMMENT ON COLUMN etiquetas.quantidade IS
    'O que RESTA no pote, na unidade de estoque do produto. É o que o descarte lança '
    'como perda. Diminui a cada uso parcial (etiqueta_usos).';
COMMENT ON COLUMN etiquetas.quantidade_inicial IS
    'A quantidade com que a etiqueta nasceu. Não muda.';

-- 🔑 **Cada retirada é um registro**: quanto saiu, quanto ficou, quando e quem. É
-- o histórico do pote — e o que deixa conferir uma quantidade que não bate.
-- ⚠️ **Não é razão de estoque.** O consumo já entra no estoque pela venda ou pela
-- produção que usou o pote; baixar aqui também contaria duas vezes. Esta tabela
-- diz o que aconteceu com o POTE, não com o saldo.
CREATE TABLE IF NOT EXISTS etiqueta_usos (
    id          bigserial PRIMARY KEY,
    id_etiqueta bigint NOT NULL REFERENCES etiquetas(id) ON DELETE CASCADE,
    quantidade  numeric(14,4) NOT NULL CHECK (quantidade > 0),
    -- O que ficou no pote DEPOIS desta retirada.
    restante    numeric(14,4) NOT NULL CHECK (restante >= 0),
    feito_em    timestamptz NOT NULL DEFAULT now(),
    id_usuario  integer REFERENCES usuarios(id),
    observacao  varchar(200)
);
CREATE INDEX IF NOT EXISTS ix_etiqueta_usos_etiqueta ON etiqueta_usos (id_etiqueta, id);

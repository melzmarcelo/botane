-- O de-para das unidades que chegam de fora.
--
-- 🔑 **Decisão do dono (09/09/2026):** *"conforme as unidades vão chegando pelas
-- notas podemos ir vinculando ou cadastrando"*.
--
-- A alternativa era importar de uma vez as unidades do Omie. O catálogo real
-- tem **603 unidades** — uma tabela global e compartilhada, com `%`, `01`,
-- `1/4`, `12X4` e `18x4x4` no meio. E, mesmo restrito às que os produtos da casa
-- usam, sobram 57 siglas para uns doze conceitos: `PC`, `UNID`, `UND`, `UN1`,
-- `1 UNID`, `UM` e `1` são todas "unidade"; `PT`, `PAC`, `PK` e `SC` são todas
-- "pacote". Criá-las como unidades faria o combo do cadastro oferecer sete
-- coisas diferentes com o mesmo significado — e **unidade diferente não
-- converte**, então o custo pararia de fluir do jeito mais silencioso possível.
--
-- ⚠️ **Apelido não é unidade.** Ele não entra em combo nenhum, não tem grandeza
-- nem fator: é só a tradução de um texto que veio de fora para uma unidade que
-- existe aqui. Quem tem grandeza e fator continua sendo `unidades_medida`, e é
-- lá que nasce a unidade que realmente falta (metro, por exemplo).
--
-- ⚠️ **Global, não por fornecedor.** A sigla de unidade é praticamente
-- universal — "KG." é quilo em qualquer nota —, e um de-para por fornecedor
-- faria a mesma pessoa traduzir "UNID" uma vez para cada um dos 793. Se um dia
-- aparecer o caso real de dois fornecedores usando a mesma sigla para coisas
-- diferentes, a coluna `id_fornecedor` entra aqui com `NULL` valendo "para
-- todos" — a forma já prevista pelo preço da casa e pelo preço da loja.

CREATE TABLE IF NOT EXISTS unidade_apelidos (
    -- Como veio escrito lá fora, já em maiúsculas e sem espaço nas pontas: é
    -- assim que a comparação acontece, e guardar o texto cru obrigaria a
    -- normalizar em toda consulta — uma delas ficaria para trás.
    apelido     varchar(20) PRIMARY KEY,
    -- O que ele quer dizer AQUI. `ON DELETE CASCADE` porque um apelido que
    -- aponta para uma unidade apagada não traduz nada: seria um de-para que
    -- responde com um vazio, pior que não responder.
    sigla       varchar(10) NOT NULL REFERENCES unidades_medida(sigla) ON DELETE CASCADE,
    criado_em   timestamptz NOT NULL DEFAULT now(),
    criado_por  integer REFERENCES usuarios(id),
    -- ⚠️ Um apelido NÃO pode ser uma unidade de verdade: "KG" traduzido para
    -- "G" faria o quilo virar grama em toda nota, e o de-para venceria o
    -- cadastro sem ninguém entender por quê. A trava é do banco.
    CONSTRAINT ck_apelido_nao_e_unidade CHECK (apelido <> sigla)
);

CREATE INDEX IF NOT EXISTS ix_unidade_apelidos_sigla ON unidade_apelidos (sigla);

-- ⚠️ **A fila NÃO tem tabela.** As unidades pendentes são uma CONSULTA sobre
-- `nota_itens` (o que chegou, menos o que já se conhece, menos o que já foi
-- traduzido) — a mesma decisão da fila de envio ao PDV. Uma fila mantida à mão
-- precisaria ser alimentada em todo lugar que grava um item de nota, e o
-- próximo lugar — que vai existir — nasceria sem ela.

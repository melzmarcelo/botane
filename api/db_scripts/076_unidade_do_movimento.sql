-- A unidade em que CADA linha do razão foi gravada.
--
-- 🔑 **Pedido do dono (19/09/2026):** *"mesmo com estoque, às vezes queremos
-- alterar a unidade do produto, gostaria que fosse possível"*. Até aqui o
-- sistema RECUSAVA a troca quando havia movimento, e a recusa estava certa pelo
-- que se sabia: `estoque_movimentos` é append-only, as quantidades históricas
-- estão gravadas na unidade antiga, e trocar o cadastro faria o razão dizer
-- "10" numa unidade e o saldo "10" noutra — a mesma prateleira valendo dois
-- números diferentes.
--
-- 🔑 **Esta coluna é o que desfaz o impasse.** Com a unidade gravada na LINHA,
-- o passado continua legível na unidade da época e o futuro anda na nova: não
-- é preciso reescrever nada, e é por isso que a troca passa a ser possível sem
-- ferir o append-only.
--
-- ⚠️ **O backfill diz o que é VERDADE hoje**, não um palpite: nenhuma conversão
-- aconteceu ainda, então toda linha existente está na unidade atual do produto.
-- Depois desta migração, quem grava a unidade é o movimento.
--
-- ⚠️ **Nula é "não sei", e a tela cai na unidade do produto.** Produto sem
-- `um_estoque` (rascunho recém-importado do Omie) não ganha unidade inventada.
ALTER TABLE estoque_movimentos ADD COLUMN IF NOT EXISTS um varchar(6);

-- Sem FK para `unidades_medida`: a sigla histórica precisa sobreviver a alguém
-- apagar a unidade do cadastro. O razão não se reescreve nem por isso.
UPDATE estoque_movimentos m
   SET um = p.um_estoque
  FROM produtos p
 WHERE p.id = m.id_produto
   AND m.um IS NULL
   AND p.um_estoque IS NOT NULL;

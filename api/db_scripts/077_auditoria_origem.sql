-- Botané 077 — de onde veio cada alteração: a tela ou o Claude.
-- Idempotente.
--
-- 🔑 **Pedido do dono (20/09/2026): deixar o Claude GRAVAR** (conciliar nota,
-- corrigir cadastro, criar produto, lançar nota). A auditoria já dizia quem
-- mudou o quê; com uma máquina agindo em nome de alguém, falta dizer **por onde**.
--
-- 🔑 **A pergunta que esta coluna responde é "o que o Claude fez ontem?"** —
-- e ela aparece justamente quando algo saiu errado. Sem a coluna, a resposta
-- seria cruzar horário de auditoria com `ultimo_uso_em` da chave, à mão, e
-- ninguém faria isso no dia em que precisasse.
--
-- ⚠️ **Nula quer dizer a tela**, que é o caso de tudo o que já está gravado e da
-- maior parte do que virá. Preencher o passado seria inventar história.
ALTER TABLE auditoria ADD COLUMN IF NOT EXISTS origem varchar(10);

COMMENT ON COLUMN auditoria.origem IS
  'Por onde veio a alteracao: claude (chave de maquina) ou nulo, que e a tela. '
  'Migracao 077.';

-- 166 — Ordem de compra: cada um vê os próprios pedidos; ver todos é chave à parte.
-- Idempotente. Só permissões: não reescreve dado.
--
-- 🔑 **Pedido do dono (25/11/2026):** *"ajustar as permissão, separar a visualização. Gostaria
-- que usuarios sem permissão pudessem visualizar somente os seus itens pedidos. Sem realizar
-- alteração após a aprovação do gestor."*
--
-- 🔑 **Vê a lista inteira quem tem `compras.ordem_ver_todos`, e também quem compra ou aprova**
-- (não dá para comprar ou aprovar o que não se vê). Os outros veem só o que pediram, nas abas,
-- nas contagens e no relatório.
-- ⚠️ Depois de aprovado, quem só pediu não corrige NEM cancela (a regra mora no service).

INSERT INTO permissoes (chave, modulo, descricao, ordem) VALUES
    ('compras.ordem_ver_todos', 'Compras',
     'Ver os pedidos de todos na ordem de compra (sem ela, cada um vê só os seus)', 442)
ON CONFLICT (chave) DO UPDATE
    SET modulo = EXCLUDED.modulo, descricao = EXCLUDED.descricao, ordem = EXCLUDED.ordem;

UPDATE permissoes
   SET descricao = 'Pedir itens na ordem de compra, ver os próprios pedidos e corrigir ou '
                   'cancelar o próprio pedido enquanto não é aprovado'
 WHERE chave = 'compras.ordem_solicitar';

-- ⚠️ Concedido AQUI (ver 091): os papéis que já compram ou aprovam. Cozinha e Salão ficam só
-- com os próprios pedidos.
INSERT INTO papel_permissoes (id_papel, chave)
SELECT p.id, 'compras.ordem_ver_todos'
  FROM papeis p
 WHERE p.sistema AND p.nome IN ('Administrador', 'Gerente', 'Conferente / Estoque')
ON CONFLICT DO NOTHING;

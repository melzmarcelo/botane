-- Botane 003 — a empresa e a primeira loja existem desde o start.
-- Sem isso não há id_unidade para carimbar nos movimentos, e o sistema não
-- funciona nem para o primeiro login. Os dados reais entram pela tela.

INSERT INTO empresa (id, razao_social, nome_fantasia)
VALUES (1, 'Botane', 'Botane')
ON CONFLICT (id) DO NOTHING;

INSERT INTO unidades (nome, apelido, matriz, ativo)
SELECT 'Loja principal', 'Matriz', true, true
 WHERE NOT EXISTS (SELECT 1 FROM unidades);

INSERT INTO parametros (id_unidade)
SELECT u.id FROM unidades u
 WHERE NOT EXISTS (SELECT 1 FROM parametros p WHERE p.id_unidade = u.id);

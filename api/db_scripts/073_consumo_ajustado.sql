-- O que REALMENTE saiu, quando não foi o que a ficha pedia.
--
-- 🔑 **Pedido do dono (16/09/2026):** *"na lista de insumos, ter uma nova coluna
-- com o que realmente foi usado. Por padrão é a mesma quantidade, mas o usuário
-- pode alterar, inclusive a unidade — por exemplo, na receita vão 5 ovos, mas
-- por um acaso usei 6 ovos."*
--
-- 🔑 **O razão já era capaz disso; o que faltava era a porta.** A produção
-- sempre gravou o que saiu, e o custo do produzido sempre foi "o que realmente
-- saiu, não o custo teórico da ficha" — só que a quantidade vinha calculada da
-- receita, sem ninguém poder corrigi-la. Quem usava seis ovos lançava cinco e o
-- sexto sumia do controle: aparecia semanas depois, no inventário, como falta
-- sem causa.
--
-- ⚠️ **A coluna é um AVISO, não um dado novo.** Tudo o que ela diz já está nos
-- movimentos — basta comparar com a ficha. Ela existe para a comparação não
-- precisar ser feita: produção que se afasta da receita com frequência é ficha
-- errada, e isso é uma pergunta que alguém tem de fazer olhando a lista, não
-- recalculando cada linha.
ALTER TABLE producoes ADD COLUMN IF NOT EXISTS consumo_ajustado boolean NOT NULL DEFAULT false;

COMMENT ON COLUMN producoes.consumo_ajustado IS
  'Alguem corrigiu a quantidade de pelo menos um insumo na hora de produzir: o '
  'que saiu nao e o que a ficha pedia. Migracao 073.';

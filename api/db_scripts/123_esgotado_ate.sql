-- 123 · O esgotado que volta sozinho (1.1.109).
--
-- 🔑 Proposta da análise de 17/10/2026: o prato marcado "esgotado" no almoço ficava esgotado
-- para sempre, até alguém lembrar de desmarcar. Agora quem marca escolhe: volta no próximo dia
-- (às 4h da casa) ou só quando alguém tirar.
-- 🔑 `esgotado_ate` nulo = até alguém tirar (o comportamento de antes). Preenchido = o item
-- só conta como esgotado até essa hora — a conta é feita NA LEITURA (`now() < esgotado_ate`),
-- então não depende do agendador ter rodado; o agendador da madrugada só arruma a linha.
-- ⚠️ Idempotente: só acrescenta coluna. Nenhum dado existente muda.

ALTER TABLE catalogo_itens ADD COLUMN IF NOT EXISTS esgotado_ate timestamptz;

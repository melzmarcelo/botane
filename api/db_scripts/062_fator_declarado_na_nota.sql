-- O fator que a NOTA FISCAL declara, para poder conferir com o do cadastro.
--
-- 🔑 **A nota já traz a resposta e o sistema a jogava fora.** No XML da NF-e o
-- emitente declara a unidade COMERCIAL (`uCom`/`qCom`) e a TRIBUTÁVEL
-- (`uTrib`/`qTrib`). Numa caixa de 24, isso sai como `uCom=CX, qCom=1,
-- uTrib=UN, qTrib=24` — e a razão `qTrib/qCom` É o fator real, dito pelo
-- fornecedor no documento fiscal. O parser lia os dois campos apenas como
-- reserva um do outro, nunca para comparar.
--
-- Sem esta coluna, o cadastro que diz "CX = 12" fazia uma nota de CX de 24
-- entrar pela METADE, calada — e como o dinheiro da nota é o mesmo, o custo
-- unitário saía pelo dobro e contaminava o custo médio, a ficha e o CMV.
--
-- ⚠️ **É CONFERÊNCIA, não decisão.** A coluna guarda o que a nota disse; quem
-- decide o que entra no razão continua sendo o cadastro, e a divergência
-- aparece na tela para uma pessoa resolver. Deixar o número da nota mandar
-- sozinho trocaria um erro silencioso por outro.
--
-- ⚠️ Nulo quando a nota não diz: nota digitada à mão não tem unidade
-- tributável, e XML com `uCom = uTrib` não informa conversão nenhuma. Nulo é
-- "a nota não declarou", que é diferente de "declarou 1".
ALTER TABLE nota_itens ADD COLUMN IF NOT EXISTS fator_declarado numeric(18,6);

COMMENT ON COLUMN nota_itens.fator_declarado IS
  'Fator que a NF-e declara (qTrib/qCom). Nulo quando a nota nao informa. '
  'Serve para CONFERIR com o fator do cadastro, nunca para decidir sozinho.';

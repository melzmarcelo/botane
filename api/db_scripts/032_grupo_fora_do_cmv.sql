-- Botané 032 — grupo do CMV que NÃO entra no CMV real. Idempotente.
--
-- Os grupos nasceram para EXPLICAR o número: "deste CMV, R$ 420 é material de
-- limpeza". Mas a pergunta que vem em seguida é outra — se detergente e marmita
-- não são comida, por que estão dentro do custo da comida? O food cost sai mais
-- alto do que a cozinha custa, e é esse percentual que vira decisão de cardápio.
--
-- Agora cada grupo escolhe: **entra no CMV real, ou fica de fora dele.**
--
-- ⚠️ **Ficar de fora é sair da conta INTEIRA, não só das compras.** O CMV real é
-- `inicial + compras − final`; tirar só as compras deixaria o estoque de
-- detergente do começo e do fim dentro da conta, e a diferença entre os dois
-- viraria custo de comida do mesmo jeito — pior, com sinal imprevisível. Quem
-- sai, sai das três pontas, e aí a contribuição do grupo se anula por completo.
--
-- ⚠️ **O dinheiro não some da tela.** O grupo continua aparecendo no painel,
-- agora dito "fora do CMV real": gastar com limpeza é gastar, e um número que
-- desaparece da vista é um número que ninguém controla.

ALTER TABLE cmv_grupos
    ADD COLUMN IF NOT EXISTS considerar_no_cmv boolean NOT NULL DEFAULT true;

COMMENT ON COLUMN cmv_grupos.considerar_no_cmv IS
    'Falso tira os produtos destes tipos do CMV real — do estoque inicial, das '
    'compras e do estoque final. O grupo continua aparecendo no painel, à parte.';

-- ⚠️ O grupo de exemplo nasce FORA do CMV, que é o motivo de ele existir:
-- material de limpeza e embalagem não são comida. Só mexe em quem nunca foi
-- tocado — se alguém já decidiu, a decisão fica.
UPDATE cmv_grupos
   SET considerar_no_cmv = false
 WHERE lower(nome) = 'material de limpeza e embalagem'
   AND considerar_no_cmv;

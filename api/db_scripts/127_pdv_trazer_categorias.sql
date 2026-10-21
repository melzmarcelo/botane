-- Botané 127 — trazer ou não as categorias do PDV. Idempotente.
--
-- 🔑 Pedido do dono (21/10/2026): "na integração com o PDV, cria uma opção se vamos
-- ou não integrar as categorias do PDV para o Botané; caso desmarcado, para de
-- sincronizar elas". Até aqui o grupo do cardápio (`nomeGrupo`) virava categoria
-- SEMPRE: criada quando não existia e gravada no produto — no "Importar cardápio" e,
-- com o envio desligado, também na busca automática de vendas.
--
-- ⚠️ **Nasce VERDADEIRO**, e de propósito: é o comportamento de hoje, e uma migração
-- não muda o que a casa já faz. Desligar é decisão de quem organiza o cadastro.
-- ⚠️ Desligar NÃO apaga nada: as categorias que já vieram e o que está nos produtos
-- ficam como estão. Só para de criar e de gravar a partir dali.
-- ⚠️ É só a mão PDV → Botané. O envio da categoria daqui para o PDV (`enviar_ao_pdv`)
-- é outro interruptor e não muda.

ALTER TABLE integracoes
    ADD COLUMN IF NOT EXISTS trazer_categorias boolean NOT NULL DEFAULT true;

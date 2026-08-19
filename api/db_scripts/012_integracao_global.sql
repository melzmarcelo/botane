-- Botané 012 — integração que não é de loja nenhuma (o SMTP). Idempotente.
--
-- `integracoes` tem UNIQUE (id_unidade, servico), e o SMTP é da casa inteira:
-- entra com id_unidade NULL. Só que no Postgres **dois nulos são distintos**,
-- então a restrição não se aplica a essas linhas e o `ON CONFLICT` do UPSERT
-- nunca dispara: cada gravação da tela criava outra linha, e a leitura passava
-- a devolver uma qualquer — a tela mostrava o servidor de uma configuração e o
-- envio usava a senha de outra.
--
-- O índice parcial abaixo é o que faltava: para as linhas sem loja, o serviço
-- é único por si só.

-- Antes do índice, resolver o que já duplicou: fica a linha mais recente de
-- cada serviço, que é a que a pessoa configurou por último.
DELETE FROM integracoes i
 WHERE i.id_unidade IS NULL
   AND i.id < (SELECT max(j.id) FROM integracoes j
                WHERE j.id_unidade IS NULL AND j.servico = i.servico);

CREATE UNIQUE INDEX IF NOT EXISTS ux_integracao_global
    ON integracoes (servico) WHERE id_unidade IS NULL;

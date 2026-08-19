-- Botané 014 — a composição do kit/combo. Idempotente.
--
-- Combo ("prato do dia + refrigerante") chega do PDV como UMA linha, com um
-- código só. Sem isto ele não tem custo: não é produzido (logo não tem ficha) e
-- não é estocado (logo não tem custo médio) — e o CMV teórico do mês ficava
-- furado justamente nos itens que mais vendem.
--
-- Por que apontar para PRODUTO e não para ficha, como o `ficha_itens` faz: a
-- ficha é uma VERSÃO. Um combo que apontasse para a ficha do prato continuaria
-- calculando pela receita velha depois que a cozinha homologasse a nova. O kit
-- aponta para o produto, e cada componente resolve o próprio custo pela regra
-- dele — ficha vigente se for produzido, custo médio se for revenda.

CREATE TABLE IF NOT EXISTS kit_itens (
    id            serial PRIMARY KEY,
    id_kit        integer NOT NULL REFERENCES produtos(id) ON DELETE CASCADE,
    id_componente integer NOT NULL REFERENCES produtos(id) ON DELETE RESTRICT,
    quantidade    numeric(18,4) NOT NULL DEFAULT 1,
    observacao    varchar(120),
    ordem         smallint NOT NULL DEFAULT 0,
    CONSTRAINT ck_kit_qtd CHECK (quantidade > 0),
    -- Um kit que se contém não passa nem no caso trivial; o ciclo indireto é
    -- recusado pelo service, como no ficha_itens.
    CONSTRAINT ck_kit_nao_e_ele_mesmo CHECK (id_kit <> id_componente)
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_kit_item ON kit_itens (id_kit, id_componente);
CREATE INDEX IF NOT EXISTS ix_kit_itens_kit ON kit_itens (id_kit, ordem);
CREATE INDEX IF NOT EXISTS ix_kit_itens_componente ON kit_itens (id_componente);

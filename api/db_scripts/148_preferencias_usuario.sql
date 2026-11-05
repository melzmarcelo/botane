-- 148 — As preferências de tela de cada usuário (colunas do grid, densidade, visões salvas). Idempotente.
--
-- 🔑 **Pedido do dono (05/11/2026), fase 2 do layout novo:** *"grids configuráveis e que
-- proporcionam uma ótima visualização"*. Cada pessoa escolhe as colunas, a ordem, a densidade e
-- guarda visões com os filtros. Fica no SERVIDOR, e não no navegador, para valer em qualquer
-- aparelho: quem arruma o grid no escritório o encontra igual no tablet.
--
-- ⚠️ É dado de tela, não regra de negócio: um JSON por (usuário, chave), e a chave nomeia a tela
-- (`grade:produtos`). Quem lê e escreve é sempre o PRÓPRIO usuário (`routers/preferencias.py`).
-- ⚠️ Usuário apagado leva as preferências junto (CASCADE): não há o que preservar.

CREATE TABLE IF NOT EXISTS preferencias_usuario (
    id_usuario    integer      NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    chave         varchar(80)  NOT NULL,
    valor         jsonb        NOT NULL,
    atualizado_em timestamptz  NOT NULL DEFAULT now(),
    PRIMARY KEY (id_usuario, chave)
);

COMMENT ON TABLE preferencias_usuario IS
    'Preferências de tela por usuário (148): colunas, ordem e densidade dos grids e as visões '
    'salvas. Chave = a tela (ex.: grade:produtos). Só o próprio usuário lê e grava.';

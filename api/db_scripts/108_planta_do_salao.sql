-- 108 — Salão: a planta. O formato da mesa. Idempotente.
--
-- 🔑 **Segunda entrega do estudo `docs/salao-estudo.md`** (07/10/2026): as mesas
-- desenhadas na posição em que estão. `pos_x`/`pos_y` existem desde a 069 e
-- ninguém usava; o que faltava para desenhar é o FORMATO.
--
-- ⚠️ **Só desenho.** A disponibilidade não lê formato nem posição: quem decide
-- se cabe continua sendo `capacidade_max` e a junta.

ALTER TABLE mesas
    ADD COLUMN IF NOT EXISTS formato varchar(12) NOT NULL DEFAULT 'QUADRADA';

ALTER TABLE mesas DROP CONSTRAINT IF EXISTS ck_mesa_formato;
ALTER TABLE mesas ADD CONSTRAINT ck_mesa_formato
    CHECK (formato IN ('REDONDA', 'QUADRADA', 'RETANGULAR'));

-- ⚠️ A posição é em pontos da planta, a partir do canto de cima à esquerda, e
-- nunca negativa: mesa arrastada para fora do desenho não pode sumir da tela.
ALTER TABLE mesas DROP CONSTRAINT IF EXISTS ck_mesa_posicao;
ALTER TABLE mesas ADD CONSTRAINT ck_mesa_posicao
    CHECK ((pos_x IS NULL OR pos_x BETWEEN 0 AND 4000)
       AND (pos_y IS NULL OR pos_y BETWEEN 0 AND 4000));

COMMENT ON COLUMN mesas.formato IS
    'REDONDA, QUADRADA ou RETANGULAR — só para desenhar a planta do salão.';
COMMENT ON COLUMN mesas.pos_x IS
    'Posição na planta do salão (pontos, da esquerda). Nula = ainda não posicionada: '
    'a tela arruma em fileiras até alguém arrastar.';

-- 157 — Patrimônio, entrega 2 da ficha do bem: responsável, garantia em meses + tipo, checklist
-- da preventiva, nota fiscal da manutenção e fotos/documentos anexados.
--
-- 🔑 Decisões do dono (10/11/2026): responsável é TEXTO livre (como a planilha), não usuário;
-- garantia em meses + tipo com a data final CALCULADA da compra (e editável); anexos no BANCO,
-- como a logo e a foto da ficha (`arquivos`, 046) — o disco do App Platform some a cada deploy.
-- ⚠️ A situação no Omie dos custos NÃO é gravada: é consulta na hora (só leitura).
-- Idempotente.

ALTER TABLE bens ADD COLUMN IF NOT EXISTS responsavel varchar(120);
ALTER TABLE bens ADD COLUMN IF NOT EXISTS garantia_meses smallint;
ALTER TABLE bens ADD COLUMN IF NOT EXISTS garantia_tipo varchar(12);
-- Os itens a verificar em cada preventiva deste bem ("limpar condensador", "trocar filtro").
ALTER TABLE bens ADD COLUMN IF NOT EXISTS preventiva_checklist text[] NOT NULL DEFAULT '{}';

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_bens_garantia_meses') THEN
        ALTER TABLE bens ADD CONSTRAINT ck_bens_garantia_meses
            CHECK (garantia_meses BETWEEN 1 AND 240);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_bens_garantia_tipo') THEN
        ALTER TABLE bens ADD CONSTRAINT ck_bens_garantia_tipo
            CHECK (garantia_tipo IN ('FABRICA', 'ESTENDIDA', 'LOJA'));
    END IF;
END $$;

-- A nota da visita (para achar a conta a pagar no Omie) e o checklist como foi marcado —
-- uma FOTO: se o checklist do bem mudar depois, a visita antiga continua dizendo o que viu.
ALTER TABLE bem_manutencoes ADD COLUMN IF NOT EXISTS nota_fiscal varchar(40);
ALTER TABLE bem_manutencoes ADD COLUMN IF NOT EXISTS checklist jsonb;

-- Fotos e documentos do bem. O conteúdo mora em `arquivos`; aqui, a quem pertence.
CREATE TABLE IF NOT EXISTS bem_anexos (
    id          serial PRIMARY KEY,
    id_bem      integer NOT NULL REFERENCES bens(id) ON DELETE CASCADE,
    tipo        varchar(10) NOT NULL CHECK (tipo IN ('FOTO', 'DOCUMENTO')),
    nome        varchar(160) NOT NULL,
    url         varchar(200) NOT NULL,
    bytes       integer NOT NULL,
    criado_em   timestamptz NOT NULL DEFAULT now(),
    criado_por  integer REFERENCES usuarios(id)
);
CREATE INDEX IF NOT EXISTS ix_bem_anexos_bem ON bem_anexos (id_bem, id);

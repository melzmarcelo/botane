-- O cardápio do site em inglês e alemão.
--
-- 🔑 Pedido do dono (24/09/2026, decidido em 29/09/2026): *"em produtos, aba catálogo,
-- gerar o texto do catálogo em inglês e alemão de forma automática, e a escolha do idioma no
-- site"* — com o **Claude Haiku**, **categorias também**, e o **site nos três idiomas**.
-- Estudo em `docs/memoria/reservas.md` ("cardápio e site em inglês e alemão").
--
-- Em cada coisa que o cliente lê: as versões EN e DE, a lista do que foi CORRIGIDO À MÃO
-- (`traducao_editada`, que a tradução automática nunca sobrescreve) e a impressão digital
-- do português que foi traduzido (`traducao_origem`): mudou o português, a tradução
-- automática fica velha e é refeita. Idempotente.

ALTER TABLE produtos ADD COLUMN IF NOT EXISTS nome_catalogo_en varchar(160);
ALTER TABLE produtos ADD COLUMN IF NOT EXISTS nome_catalogo_de varchar(160);
ALTER TABLE produtos ADD COLUMN IF NOT EXISTS informacao_adicional_en varchar(700);
ALTER TABLE produtos ADD COLUMN IF NOT EXISTS informacao_adicional_de varchar(700);
ALTER TABLE produtos ADD COLUMN IF NOT EXISTS traducao_editada text[] NOT NULL DEFAULT '{}';
ALTER TABLE produtos ADD COLUMN IF NOT EXISTS traducao_origem varchar(64);
ALTER TABLE produtos ADD COLUMN IF NOT EXISTS traducao_em timestamptz;

ALTER TABLE catalogo_categorias ADD COLUMN IF NOT EXISTS nome_en varchar(160);
ALTER TABLE catalogo_categorias ADD COLUMN IF NOT EXISTS nome_de varchar(160);
ALTER TABLE catalogo_categorias ADD COLUMN IF NOT EXISTS descricao_en varchar(700);
ALTER TABLE catalogo_categorias ADD COLUMN IF NOT EXISTS descricao_de varchar(700);
ALTER TABLE catalogo_categorias ADD COLUMN IF NOT EXISTS traducao_editada text[] NOT NULL DEFAULT '{}';
ALTER TABLE catalogo_categorias ADD COLUMN IF NOT EXISTS traducao_origem varchar(64);
ALTER TABLE catalogo_categorias ADD COLUMN IF NOT EXISTS traducao_em timestamptz;

ALTER TABLE catalogo_subcategorias ADD COLUMN IF NOT EXISTS nome_en varchar(160);
ALTER TABLE catalogo_subcategorias ADD COLUMN IF NOT EXISTS nome_de varchar(160);
ALTER TABLE catalogo_subcategorias ADD COLUMN IF NOT EXISTS descricao_en varchar(700);
ALTER TABLE catalogo_subcategorias ADD COLUMN IF NOT EXISTS descricao_de varchar(700);
ALTER TABLE catalogo_subcategorias ADD COLUMN IF NOT EXISTS traducao_editada text[] NOT NULL DEFAULT '{}';
ALTER TABLE catalogo_subcategorias ADD COLUMN IF NOT EXISTS traducao_origem varchar(64);
ALTER TABLE catalogo_subcategorias ADD COLUMN IF NOT EXISTS traducao_em timestamptz;

-- O nome do catálogo também aparece no site (é o botão da página inicial).
ALTER TABLE catalogos ADD COLUMN IF NOT EXISTS nome_en varchar(160);
ALTER TABLE catalogos ADD COLUMN IF NOT EXISTS nome_de varchar(160);
ALTER TABLE catalogos ADD COLUMN IF NOT EXISTS traducao_editada text[] NOT NULL DEFAULT '{}';
ALTER TABLE catalogos ADD COLUMN IF NOT EXISTS traducao_origem varchar(64);
ALTER TABLE catalogos ADD COLUMN IF NOT EXISTS traducao_em timestamptz;

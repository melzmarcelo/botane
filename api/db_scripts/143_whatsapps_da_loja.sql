-- Vários WhatsApps por loja, um principal; o número do catálogo e o "entre em contato".
--
-- 🔑 **Pedido do dono (30/10/2026):** *"no cadastro de whatsapp nas lojas, poder configurar mais
-- de um, e tornar um o principal da loja. E no cardápio, permitir a seleção do número que será
-- responsável pela interação. E também colocar uma opção configurável no catálogo, como permite
-- entrar em contato: um botão no cabeçalho do catálogo que direciona para o contato cadastrado
-- no catálogo."* Estudo em `docs/whatsapp-numeros-estudo.md`.
--
-- ⚠️ São números para o CLIENTE chamar (link wa.me). A conexão com a Meta (099), que ENVIA os
-- avisos, continua uma só por loja e não muda.
-- 🔑 **`unidades.whatsapp` FICA, como espelho do principal**: quem já lia o campo (o "Entre em
-- contato" do site, o termo LGPD, a fidelidade) continua lendo e recebe o principal, sem mudar.
-- Quem grava a lista (`services/whatsapps_da_loja.py`) é quem mantém o espelho.
-- Idempotente.

CREATE TABLE IF NOT EXISTS unidade_whatsapps (
    id          serial PRIMARY KEY,
    id_unidade  integer NOT NULL REFERENCES unidades(id) ON DELETE CASCADE,
    rotulo      varchar(60) NOT NULL,
    numero      varchar(30) NOT NULL,
    principal   boolean NOT NULL DEFAULT false,
    ordem       integer NOT NULL DEFAULT 0,
    criado_em   timestamptz NOT NULL DEFAULT now()
);
-- Um principal por loja, no máximo.
CREATE UNIQUE INDEX IF NOT EXISTS ux_unidade_whatsapp_principal
    ON unidade_whatsapps (id_unidade) WHERE principal;
CREATE INDEX IF NOT EXISTS ix_unidade_whatsapps_loja ON unidade_whatsapps (id_unidade, ordem);

-- O número que já estava no cadastro entra na lista, como principal. Só em loja que ainda não
-- tem lista: rodar de novo não duplica nem desfaz o que a casa arrumou.
INSERT INTO unidade_whatsapps (id_unidade, rotulo, numero, principal, ordem)
SELECT u.id, 'Atendimento', btrim(u.whatsapp), true, 0
  FROM unidades u
 WHERE nullif(btrim(u.whatsapp), '') IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM unidade_whatsapps w WHERE w.id_unidade = u.id);

-- 🔑 O número RESPONSÁVEL pelo catálogo (um da loja dona). Nulo = o principal da loja onde o
-- cliente está. Número apagado da lista volta o catálogo ao principal (SET NULL).
ALTER TABLE catalogos ADD COLUMN IF NOT EXISTS id_whatsapp integer
    REFERENCES unidade_whatsapps(id) ON DELETE SET NULL;
-- 🔑 O botão "entre em contato" no cabeçalho do catálogo (site e Cardápio Vivo). Desligado
-- por padrão: catálogo que já está no ar não ganha botão sem a casa pedir.
ALTER TABLE catalogos ADD COLUMN IF NOT EXISTS permite_contato boolean NOT NULL DEFAULT false;

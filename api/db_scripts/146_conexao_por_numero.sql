-- A conexão com a Meta passa a ser de cada NÚMERO da loja, não da loja.
--
-- 🔑 **Pedido do dono (30/10/2026):** *"foi realizado o cadastro somente do número; acho que
-- teria que criar uma configuração completa como tem na aba WhatsApp da loja, onde permite
-- enviar mensagem automaticamente e receber os devidos retornos."* Na 143 a lista era só de
-- números para o cliente chamar e a conexão (099) continuava uma por loja; agora cada número
-- pode ter a dele, e cada aviso diz por qual número sai.
--
-- ⚠️ **A conexão que já existia vai para o número principal** (ou para o da lista que tem os
-- mesmos dígitos do número que estava na conexão), com o MESMO token de verificação do
-- webhook: nada a refazer na Meta. A linha de `integracoes` (servico = 'whatsapp') fica no
-- banco, mas deixa de ser lida.
-- Idempotente: a cópia só acontece em loja onde nenhum número tem conexão ainda.

ALTER TABLE unidade_whatsapps ADD COLUMN IF NOT EXISTS conectado boolean NOT NULL DEFAULT false;
ALTER TABLE unidade_whatsapps ADD COLUMN IF NOT EXISTS modo varchar(10) NOT NULL DEFAULT 'simulado';
DO $$ BEGIN
    ALTER TABLE unidade_whatsapps ADD CONSTRAINT ck_unidade_whatsapp_modo
        CHECK (modo IN ('simulado', 'real'));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
ALTER TABLE unidade_whatsapps ADD COLUMN IF NOT EXISTS phone_number_id varchar(40);
ALTER TABLE unidade_whatsapps ADD COLUMN IF NOT EXISTS waba_id varchar(40);
ALTER TABLE unidade_whatsapps ADD COLUMN IF NOT EXISTS api_versao varchar(10);
ALTER TABLE unidade_whatsapps ADD COLUMN IF NOT EXISTS verify_token varchar(60);
-- Token e segredo do app, cifrados como os do Omie (`services/segredos.py`).
ALTER TABLE unidade_whatsapps ADD COLUMN IF NOT EXISTS credenciais bytea;
-- 🔑 Os números da loja costumam estar no MESMO app da Meta: marcado, o número usa o token e
-- o segredo do principal e ninguém digita duas vezes.
ALTER TABLE unidade_whatsapps ADD COLUMN IF NOT EXISTS conta_do_principal boolean NOT NULL DEFAULT false;
ALTER TABLE unidade_whatsapps ADD COLUMN IF NOT EXISTS ultimo_status varchar(10);
ALTER TABLE unidade_whatsapps ADD COLUMN IF NOT EXISTS ultima_mensagem text;
-- O webhook acha o número (e a loja) pelo identificador da Meta: um número, um dono.
CREATE UNIQUE INDEX IF NOT EXISTS ux_unidade_whatsapp_pnid
    ON unidade_whatsapps (phone_number_id) WHERE phone_number_id IS NOT NULL;

-- Por qual número sai cada aviso. Nulo = o principal da loja.
ALTER TABLE whatsapp_avisos ADD COLUMN IF NOT EXISTS id_whatsapp integer
    REFERENCES unidade_whatsapps(id) ON DELETE SET NULL;
-- Por qual número a mensagem saiu: a resposta do cliente volta por ele.
ALTER TABLE whatsapp_mensagens ADD COLUMN IF NOT EXISTS id_whatsapp integer
    REFERENCES unidade_whatsapps(id) ON DELETE SET NULL;

DO $$
DECLARE
    i record;
    alvo integer;
    num text;
BEGIN
    FOR i IN
        SELECT g.id_unidade, g.ativa, g.modo, g.config, g.credenciais, g.ultimo_status,
               g.ultima_mensagem
          FROM integracoes g
         WHERE g.servico = 'whatsapp'
           AND NOT EXISTS (SELECT 1 FROM unidade_whatsapps w
                            WHERE w.id_unidade = g.id_unidade
                              AND (w.verify_token IS NOT NULL OR w.phone_number_id IS NOT NULL))
    LOOP
        num := nullif(regexp_replace(coalesce(i.config->>'numero', ''), '\D', '', 'g'), '');
        -- O número da lista com os mesmos dígitos; senão, o principal.
        SELECT w.id INTO alvo FROM unidade_whatsapps w
         WHERE w.id_unidade = i.id_unidade
         ORDER BY coalesce(regexp_replace(w.numero, '\D', '', 'g') = num, false) DESC,
                  w.principal DESC, w.ordem, w.id
         LIMIT 1;
        IF alvo IS NULL THEN
            -- Loja com conexão e sem número na lista: o número nasce, como principal.
            INSERT INTO unidade_whatsapps (id_unidade, rotulo, numero, principal, ordem)
            SELECT i.id_unidade, 'Atendimento',
                   coalesce(nullif(btrim(i.config->>'numero'), ''), nullif(btrim(u.whatsapp), ''),
                            (SELECT nullif(btrim(e.whatsapp), '') FROM empresa e WHERE e.id = 1), ''),
                   true, 0
              FROM unidades u WHERE u.id = i.id_unidade
            RETURNING id INTO alvo;
            UPDATE unidades u SET whatsapp = w.numero
              FROM unidade_whatsapps w
             WHERE w.id = alvo AND u.id = i.id_unidade AND nullif(btrim(w.numero), '') IS NOT NULL;
        END IF;
        UPDATE unidade_whatsapps
           SET conectado = i.ativa, modo = coalesce(i.modo, 'simulado'),
               phone_number_id = nullif(btrim(i.config->>'phone_number_id'), ''),
               waba_id = nullif(btrim(i.config->>'waba_id'), ''),
               api_versao = nullif(btrim(i.config->>'api_versao'), ''),
               verify_token = nullif(i.config->>'verify_token', ''),
               credenciais = i.credenciais,
               ultimo_status = i.ultimo_status, ultima_mensagem = i.ultima_mensagem
         WHERE id = alvo;
        -- As mensagens de antes saíram por ele: um "Confirmo" atrasado volta pelo mesmo número.
        UPDATE whatsapp_mensagens SET id_whatsapp = alvo
         WHERE id_unidade = i.id_unidade AND id_whatsapp IS NULL;
    END LOOP;
END $$;

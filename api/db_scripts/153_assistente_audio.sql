-- 153 — O assistente pelo WhatsApp, etapa 3: entender ÁUDIO.
--
-- 🔑 **Pedido do dono (06/11/2026):** *"pela manhã mando um áudio ou um texto para este
-- número…"*. Estudo em `docs/assistente-whatsapp-estudo.md`. O áudio é baixado da Meta,
-- transcrito por um serviço de fala-para-texto (OpenAI ou Groq — o mesmo formato de API, a casa
-- escolhe em Integrações ▸ Assistente) e o texto segue para o Claude como uma pergunta escrita.
--
-- ⚠️ **O áudio não é guardado**: os bytes vivem só na memória durante a transcrição. Fica o texto
-- transcrito (`texto`), que substitui o marcador "[áudio]" com que a pergunta nasce no webhook.
-- Idempotente.

-- O id da mídia na Meta (para baixar o áudio depois do 200 do webhook).
ALTER TABLE assistente_conversa ADD COLUMN IF NOT EXISTS midia_id varchar(120);
ALTER TABLE assistente_conversa ADD COLUMN IF NOT EXISTS de_audio boolean NOT NULL DEFAULT false;
-- Quando o áudio virou texto. Nulo num áudio = ainda não transcrito (a nova tentativa sabe disso).
ALTER TABLE assistente_conversa ADD COLUMN IF NOT EXISTS transcrito_em timestamptz;

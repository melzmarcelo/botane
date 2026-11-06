-- 155 — O assistente pelo WhatsApp, etapa 5: o "bom dia" com as pendências.
--
-- 🔑 Estudo em `docs/assistente-whatsapp-estudo.md`, etapa 5 ("às 7h, modelo aprovado 'Bom dia,
-- {{1}}! Hoje: {{2}}' para quem ligou a opção — é a única parte com custo de mensagem").
--
-- ⚠️ **Mensagem que o sistema INICIA é sempre um modelo aprovado pela Meta**, e variável de modelo
-- não aceita quebra de linha. Por isso o bom dia é CURTO ("hoje você tem 3 itens na agenda de
-- produção") e traz dois botões: "Ver pendências" — o toque abre a janela de 24 h e vira uma
-- pergunta ao Claude, respondida por inteiro — e "Parar o bom dia".
-- A configuração (ligado, hora, dias, só com pendência, nome do modelo) mora no `config` da
-- integração do assistente; aqui só o que é de cada pessoa.
-- Idempotente.

-- Cada pessoa escolhe receber (Perfil ▸ Assistente no WhatsApp). Desligado por padrão: ninguém
-- passa a receber mensagem da casa sem pedir.
ALTER TABLE usuario_whatsapp ADD COLUMN IF NOT EXISTS bom_dia boolean NOT NULL DEFAULT false;
-- 🔑 O último dia tratado (enviado OU pulado por não haver pendência). É o que impede mandar duas
-- vezes no mesmo dia — e é reivindicado num UPDATE só, então dois processos nunca mandam juntos.
ALTER TABLE usuario_whatsapp ADD COLUMN IF NOT EXISTS bom_dia_em date;

-- A mensagem que sai como MODELO da Meta: {nome, idioma, variaveis, botoes (payloads)}.
ALTER TABLE assistente_mensagens ADD COLUMN IF NOT EXISTS modelo jsonb;

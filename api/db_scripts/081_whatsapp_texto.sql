-- O texto padrão da mensagem de WhatsApp, configurável pela casa.
--
-- 🔑 **Pedido do dono (21/09/2026):** *"em configurações da reserva, colocar o
-- texto padrão configurável para o whatsapp."*
--
-- ⚠️ **Estava ESCRITO NO SITE**, em duas frases diferentes — uma para quem
-- clica em "Entre em contato" e outra para quem escolhe um horário. Texto de
-- cliente escrito em código é texto que só muda quando alguém publica: a casa
-- que quisesse trocar o tom da mensagem teria de pedir uma versão nova.
--
-- 🔑 **Mora em `reserva_config`, não em `empresa`**, e é onde o dono pediu. O
-- WhatsApp é o canal da empresa; a MENSAGEM é do site de reservas, e muda com o
-- que a casa está oferecendo. São duas decisões diferentes, com dois donos.

-- ⚠️ **Dois textos, não um.** Quem clica em "Entre em contato" ainda não
-- escolheu nada; quem vem da reserva já tem dia, hora e quantas pessoas. A
-- mesma frase nos dois lugares ou perde a informação que o cliente já deu, ou
-- manda "reservar para {pessoas}" sem pessoas nenhuma.
ALTER TABLE reserva_config ADD COLUMN IF NOT EXISTS whatsapp_texto text;
ALTER TABLE reserva_config ADD COLUMN IF NOT EXISTS whatsapp_texto_reserva text;

-- 🔑 **Os marcadores são o que fazem a mensagem valer a pena**: `{casa}`,
-- `{pessoas}`, `{data}` e `{hora}` são trocados pelo site na hora do clique.
-- ⚠️ **O padrão é semeado só onde está NULO.** Uma casa que já escreveu o texto
-- dela não pode perdê-lo quando esta migração rodar de novo — e migração roda
-- de novo em toda base que ainda não a tem.
UPDATE reserva_config
   SET whatsapp_texto = 'Olá! Vim pelo site do {casa}.'
 WHERE whatsapp_texto IS NULL;

UPDATE reserva_config
   SET whatsapp_texto_reserva =
       'Olá! Queria reservar para {pessoas} pessoas no dia {data} às {hora}.'
 WHERE whatsapp_texto_reserva IS NULL;

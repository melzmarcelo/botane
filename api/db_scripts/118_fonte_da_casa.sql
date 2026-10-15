-- 118 — A fonte da casa passa a ser a do SITE (Fraunces). Idempotente.
--
-- 🔑 **Pedido do dono (15/10/2026):** *"o site que utilizamos para reserva e cardápio ficou
-- parecendo dois sistemas separados. Gostaria que tudo estivesse com o mesmo layout."*
-- A configuração do Cardápio Vivo oferecia "Newsreader (a do site)", mas o site usa Fraunces
-- desde o protótipo aprovado: a frase dizia uma coisa e a tela, outra. Desde esta versão a
-- aparência da casa vale para os DOIS (site e feed), e o padrão é a fonte do site.
-- ⚠️ Quem estava no padrão (NEWSREADER) escolheu "a do site" — vira FRAUNCES. Quem escolheu
-- outra fonte de propósito (Playfair, Lora, Cormorant) fica com a dela.
-- ⚠️ **NÃO editar este arquivo depois de promovido**: o `db_updater` roda de novo a migração
-- cujo checksum mudou, e o UPDATE abaixo desfaria quem escolheu Newsreader depois.

ALTER TABLE cardapio_config ALTER COLUMN fonte SET DEFAULT 'FRAUNCES';
UPDATE cardapio_config SET fonte = 'FRAUNCES' WHERE fonte = 'NEWSREADER';

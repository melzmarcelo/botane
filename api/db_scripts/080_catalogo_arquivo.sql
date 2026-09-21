-- O PDF do catálogo: o arquivo que o site de reservas exibe.
--
-- 🔑 **Pedido do dono (21/09/2026):** *"criei o catálogo, agora tenho que poder
-- carregar o PDF, neste caso para ele ser exibido."* A migração 079 criou a
-- capa com `origem = 'PDF'` e o arquivo ainda não subia — esta é a outra
-- metade.
--
-- 🔑 **O arquivo mora no BANCO, não em disco**, e quem cuida disso é
-- `api/arquivos.py` — o mesmo lugar da logo. Não é preferência: o disco do App
-- Platform é EFÊMERO, `api/uploads/` some a cada deploy. A logo já sumiu assim
-- uma vez. Um cardápio que desaparece na publicação seria pior: o site de
-- reservas continuaria anunciando um catálogo no ar, sem nada para mostrar.
--
-- ⚠️ **Aqui fica só a URL.** Os bytes ficam em `arquivos`, e quem chama recebe
-- um endereço sem saber de onde ele vem — foi para isso que aquele módulo
-- existe desde o começo. No dia em que o Spaces entrar, só ele muda.

-- A URL relativa (`/arquivos/catalogo-3-a1b2c3d4.pdf`). Nula = sem arquivo.
ALTER TABLE catalogos ADD COLUMN IF NOT EXISTS arquivo_url varchar(200);

-- 🔑 **O nome ORIGINAL, como veio do computador de quem enviou.** A URL leva um
-- sufixo aleatório para o cache não servir o arquivo velho, então ela não diz
-- mais qual PDF é aquele. Sem este campo, a tela mostraria
-- "catalogo-3-a1b2c3d4.pdf" a quem enviou "Cardápio de verão 2026.pdf" — e
-- quem for conferir se subiu o arquivo certo não tem como saber.
ALTER TABLE catalogos ADD COLUMN IF NOT EXISTS arquivo_nome varchar(255);

-- ⚠️ **O tamanho fica GRAVADO, não calculado na hora.** Lê-lo exigiria trazer
-- os bytes do PDF só para contar — a lista de catálogos faria isso uma vez por
-- linha, e um cardápio ilustrado tem megabytes.
ALTER TABLE catalogos ADD COLUMN IF NOT EXISTS arquivo_bytes integer;

-- Quando subiu. ⚠️ Não é `atualizado_em`: trocar o nome do catálogo não troca o
-- arquivo, e quem pergunta "esse PDF é o novo?" quer a data do ARQUIVO.
ALTER TABLE catalogos ADD COLUMN IF NOT EXISTS arquivo_em timestamptz;

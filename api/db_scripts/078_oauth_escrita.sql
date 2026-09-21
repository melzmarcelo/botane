-- Botané 078 — a conexão do claude.ai pode nascer podendo alterar.
-- Idempotente.
--
-- 🔑 **Pedido do dono (21/09/2026), depois de topar na prática.** Até aqui a
-- conexão feita pelo claude.ai era SEMPRE só leitura, e alterar exigia uma chave
-- gerada à mão em Usuários — foi a escolha do dia anterior. Só que o trabalho
-- que ele quer fazer com o Claude (achar cadastros repetidos e fundi-los) começa
-- no claude.ai, e de lá as ferramentas de gravação nem apareciam.
--
-- 🔑 **A escolha passa a ser da pessoa, na hora de entrar**, numa caixa que
-- nasce DESMARCADA. O código de autorização carrega a resposta daqui até a troca
-- por chave; sem isso, o "sim" dado na página se perderia no caminho e toda
-- conexão voltaria a nascer só de leitura.
--
-- ⚠️ **Falso é o padrão, e é o que vale para todo código já gravado.** Quem não
-- marcar nada continua com uma conexão que só consulta.
ALTER TABLE oauth_codigos ADD COLUMN IF NOT EXISTS escrita boolean NOT NULL DEFAULT false;

COMMENT ON COLUMN oauth_codigos.escrita IS
  'A pessoa autorizou o Claude a ALTERAR cadastros (caixa marcada na pagina de '
  'entrada). Vira tokens_api.somente_leitura = false. Migracao 078.';

-- Botané 038 — a sessão lembra se é "manter conectado". Idempotente.
--
-- Até aqui toda sessão durava 30 dias e o navegador guardava o token em
-- `localStorage`, que sobrevive ao fechamento. Resultado: fechar o navegador
-- não encerrava nada, e quem usa o sistema num computador compartilhado
-- deixava a sessão aberta para o próximo.
--
-- Agora quem entra escolhe. Sem marcar, a sessão morre com o navegador e o
-- refresh vale poucas horas; marcando "manter conectado", vale os 30 dias de
-- sempre.
--
-- ⚠️ **A coluna existe porque o refresh é ROTATIVO.** A cada renovação nasce um
-- token novo, e sem saber em que modo a sessão começou, a rotação daria 30 dias
-- a uma sessão que a pessoa pediu que fosse curta — a escolha dela duraria até
-- a primeira renovação e depois sumiria, sem nada avisando.
--
-- ⚠️ **O padrão é `true` de propósito.** As sessões que já existem foram criadas
-- sob a regra antiga, de 30 dias; nascer com `false` encurtaria a validade de
-- quem está logado agora e derrubaria todo mundo na próxima renovação. A escolha
-- nova vale para quem entrar a partir de agora.

ALTER TABLE sessoes
    ADD COLUMN IF NOT EXISTS persistente boolean NOT NULL DEFAULT true;

COMMENT ON COLUMN sessoes.persistente IS
    'Verdadeiro quando a pessoa marcou "manter conectado" no login: o refresh '
    'vale REFRESH_EXPIRY_DIAS e o navegador guarda em localStorage. Falso é a '
    'sessão do navegador: vale REFRESH_SESSAO_HORAS e morre em sessionStorage.';

-- 🔑 **Por que não basta `revogada_em`.** A janela de graça existe para a
-- CORRIDA: duas abas apresentam o mesmo refresh, a primeira rotaciona, e a
-- segunda chegaria com um token revogado há milissegundos sem ninguém ter
-- feito nada errado.
--
-- ⚠️ Mas `revogada_em` também é preenchida pelo LOGOUT, e aí a graça vira
-- buraco: sair da conta deixaria o refresh valendo mais 30 segundos. A suíte
-- pegou exatamente isso. Sair tem de valer na hora, sempre.
--
-- Com esta coluna a diferença fica explícita: só quem foi **substituído por
-- uma rotação** ganha a folga. Logout, sessão derrubada pelo admin e troca de
-- senha continuam matando o token no ato.
ALTER TABLE sessoes
    ADD COLUMN IF NOT EXISTS substituida_em timestamptz;

COMMENT ON COLUMN sessoes.substituida_em IS
    'Quando esta sessão deu lugar a outra por ROTAÇÃO do refresh. Só ela abre '
    'a janela de graça (REFRESH_GRACA_SEGUNDOS) — revogação por logout não.';

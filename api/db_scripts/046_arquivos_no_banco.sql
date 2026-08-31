-- Botané 046 — a logo passa a morar no BANCO. Idempotente.
--
-- 🔑 **O filesystem do App Platform é EFÊMERO: `api/uploads/` some a cada
-- deploy.** O risco estava anotado desde o preparo da subida, e a saída prevista
-- era o Spaces. Na prática a casa pôs a logo, publicou uma versão e a logo
-- sumiu — três vezes, sem nada explicando.
--
-- 🔑 **Para UMA imagem de até 2 MB, o banco é a resposta mais honesta que o
-- Spaces.** Ele já sobrevive ao deploy, já entra no backup do roteiro, e não
-- pede bucket, chave nem segredo. Este projeto já perdeu duas credenciais
-- guardadas (a do Omie e a do e-mail); a melhor credencial é a que não existe.
-- ⚠️ Isto vale porque o arquivo é pequeno, é um só e é lido com cache. No dia em
-- que houver foto de produto ou anexo de nota, o Spaces volta a ser a resposta —
-- e quem muda continua sendo `api/arquivos.py`, um arquivo só.

CREATE TABLE IF NOT EXISTS arquivos (
    -- O nome do arquivo é a chave, e é ele que aparece na URL. Traz sufixo
    -- aleatório a cada envio: sem isso o navegador continuaria mostrando a logo
    -- antiga do cache.
    nome        varchar(120) PRIMARY KEY,
    -- Quem é o dono, para a troca apagar as versões anteriores.
    dono        varchar(60)  NOT NULL,
    tipo        varchar(60)  NOT NULL,
    conteudo    bytea        NOT NULL,
    bytes       integer      NOT NULL,
    criado_em   timestamptz  NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_arquivos_dono ON arquivos (dono);

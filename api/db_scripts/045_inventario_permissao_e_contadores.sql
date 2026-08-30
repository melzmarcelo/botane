-- Botané 045 — quem CONTA deixa de poder CRIAR, e cada contagem diz quem conta.
-- Idempotente.
--
-- 🔑 **Contar e montar a contagem são trabalhos diferentes, feitos por gente
-- diferente.** Até aqui `estoque.inventario` dava as duas coisas: quem ia à
-- prateleira contar podia abrir contagem nova, escolher o recorte e cancelar a
-- dos outros. Quem conta precisa de uma coisa só — abrir a contagem que já
-- existe e digitar o que viu.
--
-- ⚠️ **A chave nova é a de CRIAR, não a de contar** — e a escolha não é
-- estética. Invertê-la (criar fica com a antiga, contar vira nova) faria todo
-- mundo que hoje conta parar de contar no instante do deploy, até alguém
-- reconfigurar os papéis. Do jeito que está, ninguém perde o que já fazia: quem
-- tinha a chave continua contando, e só ganha a de criar quem já podia.

INSERT INTO permissoes (chave, modulo, descricao, ordem) VALUES
    ('estoque.inventario_criar', 'Estoque',
     'Abrir, configurar e cancelar inventário', 361)
ON CONFLICT (chave) DO NOTHING;

-- ⚠️ **Quem já criava continua criando.** Sem esta linha, o deploy tiraria do
-- gerente e do conferente uma coisa que eles faziam ontem — e o sintoma seria
-- um 403 numa tela que sempre funcionou, sem nada explicando.
INSERT INTO papel_permissoes (id_papel, chave)
SELECT pp.id_papel, 'estoque.inventario_criar'
  FROM papel_permissoes pp
 WHERE pp.chave = 'estoque.inventario'
ON CONFLICT DO NOTHING;


-- ---------------------------------------------------------------------------
-- Quem pode contar ESTA contagem
-- ---------------------------------------------------------------------------
-- 🔑 **Lista VAZIA quer dizer "qualquer um que tenha a permissão".** É o
-- comportamento de hoje, e é o que faz esta migração não mudar nada para as
-- contagens que já existem. Quem quiser restringir, restringe — e aí a lista
-- passa a ser a resposta.
--
-- ⚠️ **Não é permissão, é ESCALA.** A permissão diz o que a pessoa sabe fazer;
-- esta tabela diz quem foi escalado para esta contagem. Misturar as duas faria
-- o administrador ter de mexer em papel toda vez que a equipe do dia mudasse.

CREATE TABLE IF NOT EXISTS inventario_contadores (
    id_inventario integer NOT NULL REFERENCES inventarios(id) ON DELETE CASCADE,
    id_usuario    integer NOT NULL REFERENCES usuarios(id),
    PRIMARY KEY (id_inventario, id_usuario)
);

-- A pergunta que o servidor faz a cada contagem é "esta pessoa pode contar esta
-- contagem?", e ela é feita por inventário.
CREATE INDEX IF NOT EXISTS ix_inventario_contador_usuario
    ON inventario_contadores (id_usuario);

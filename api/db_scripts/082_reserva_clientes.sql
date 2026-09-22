-- Quem reserva pelo site: um cadastro simples, com o telefone como chave.
--
-- 🔑 **Pedido do dono (21/09/2026):** *"para a realização de reserva, precisamos
-- de um cadastro simples do usuário. Clica em Reserve sua Mesa, abre uma tela
-- com o número do telefone; caso não tenha cadastrada, realiza o cadastro com
-- Nome, telefone, gênero e cidade."*
--
-- 🔑 **O esboço dizia que a tabela de pessoas seria `fornecedores`, e isso está
-- ERRADO hoje.** A decisão é de antes de a integração com o Omie existir; desde
-- então a casa aprendeu, na conta real, que misturar as duas coisas custa caro:
-- uma conta com 919 cadastros despejou **888 clientes** (pessoas físicas) dentro
-- dos fornecedores, e a saída foi filtrar por etiqueta no servidor. Mandar para
-- lá quem reserva mesa é refazer à mão o problema que aquele filtro resolveu —
-- e a tela de Fornecedores passaria a listar quem jantou no sábado.
-- ⚠️ E `fornecedores` **não tem gênero**: entraria como coluna nova numa tabela
-- que já carrega prazo de entrega, pedido mínimo e cupom.

CREATE TABLE IF NOT EXISTS reserva_clientes (
    id            serial PRIMARY KEY,
    -- 🔑 **Por LOJA.** Reserva é de uma casa; duas casas com reserva são dois
    -- públicos, e o site de cada uma já vem por `/publico/{id_unidade}/…`.
    id_unidade    integer NOT NULL REFERENCES unidades(id) ON DELETE CASCADE,
    -- ⚠️ **Só dígitos**, normalizado pelo servidor. O mesmo telefone digitado
    -- como "(47) 99910-5033" e como "47999105033" tem de achar o MESMO cadastro
    -- — senão a pessoa se recadastra a cada reserva e a casa fica com três
    -- fichas dela.
    telefone      varchar(20)  NOT NULL,
    nome          varchar(120) NOT NULL,
    -- ⚠️ **`NAO_INFORMADO` é uma resposta, não a ausência de uma.** Sem ela, quem
    -- não quer responder inventa — e resposta inventada é pior que campo vazio
    -- para qualquer uso que a casa faça depois.
    genero        varchar(16),
    cidade        varchar(80),
    criado_em     timestamptz NOT NULL DEFAULT now(),
    atualizado_em timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_reserva_cliente_genero
        CHECK (genero IS NULL
               OR genero IN ('FEMININO', 'MASCULINO', 'OUTRO', 'NAO_INFORMADO'))
);

-- 🔑 **A idempotência é do BANCO**, como manda a regra 8 da casa: é este índice
-- que impede o segundo cadastro do mesmo telefone, não a pergunta que a rota faz
-- antes. Rota pública tem corrida: duas abas do mesmo celular tocando "cadastrar"
-- ao mesmo tempo passam as duas pela pergunta.
CREATE UNIQUE INDEX IF NOT EXISTS ux_reserva_cliente_fone
    ON reserva_clientes (id_unidade, telefone);

-- A reserva passa a saber de QUEM ela é.
-- ⚠️ **`id_pessoa` continua existindo e aponta para `fornecedores`** — é o
-- vínculo do balcão, para a casa que quiser ligar a reserva a um cadastro que
-- ela já tem. São dois caminhos diferentes para a mesma pergunta, e apagar um
-- para aproveitar a coluna do outro quebraria a agenda de quem já usa.
ALTER TABLE reservas
    ADD COLUMN IF NOT EXISTS id_cliente integer
        REFERENCES reserva_clientes(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS ix_reserva_cliente ON reservas (id_cliente)
    WHERE id_cliente IS NOT NULL;

-- Conter abuso é a diferença entre LER e GRAVAR numa rota pública.
--
-- 🔑 **Sem isto, o salão amanhece lotado de reservas que ninguém fez.** Era o
-- item que faltava desde o esboço, e é o que separa as rotas de leitura do site
-- (que só mostram o que a casa publicou) desta, que cria registro.
--
-- ⚠️ **O que se guarda é o HASH da origem, não o endereço.** Contar quantas
-- tentativas vieram do mesmo lugar não exige saber qual lugar é — e um IP é dado
-- pessoal que a casa não tem por que acumular. O hash conta e não identifica.
CREATE TABLE IF NOT EXISTS reserva_tentativas (
    id         bigserial PRIMARY KEY,
    id_unidade integer     NOT NULL REFERENCES unidades(id) ON DELETE CASCADE,
    origem     varchar(64) NOT NULL,
    em         timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_reserva_tentativa_janela
    ON reserva_tentativas (id_unidade, origem, em DESC);

-- ⚠️ **Tentativa velha não serve para nada e não se guarda.** O limite é por
-- hora; manter o resto seria acumular rastro de visitante sem uso nenhum.
DELETE FROM reserva_tentativas WHERE em < now() - interval '2 days';

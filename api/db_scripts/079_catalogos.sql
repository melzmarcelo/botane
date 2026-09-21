-- O cabeçalho do catálogo: o que a casa publica para o cliente.
--
-- 🔑 **Pedido do dono (21/09/2026):** *"vamos iniciar pelo cadastro de
-- catálogos. Onde teremos o cabeçalho do catálogo, origem — neste momento
-- somente vamos ter PDF —, o nome dele no site do cliente, o período de
-- publicação, a situação: rascunho, ativo, inativo."*
--
-- 🔑 **PDF, não PDV** (correção do dono no mesmo dia): a origem é um **arquivo
-- PDF importado**, que é apresentado no **site de reservas**. Não tem relação
-- com o cardápio do PDV Legal — a semelhança das três letras é coincidência, e
-- ela já custou uma primeira versão inteira deste módulo.
--
-- 🔑 **O catálogo pertence a RESERVAS** (mesma correção): o menu fica dentro do
-- grupo Reservas e só aparece com o módulo ligado nesta loja. É a mesma porta
-- de `parametros.reservas_ligado` da migração 068 — desligado, o catálogo não
-- existe: sem item no menu e com as rotas recusando 409.
--
-- ⚠️ **É só o CABEÇALHO.** Os itens do catálogo são a próxima fatia; esta
-- migração cria a capa e mais nada. Criar as duas de uma vez obrigaria a
-- decidir agora como o item se liga ao produto, e essa decisão fica melhor
-- depois de a capa existir e ser usada.

CREATE TABLE IF NOT EXISTS catalogos (
    id              serial PRIMARY KEY,
    -- 🔑 **De cada LOJA** (decisão do dono, 21/09/2026). Acompanha Reservas e a
    -- regra 5 do projeto: cada casa publica o seu, com nome e período próprios.
    -- Fosse da empresa, a primeira filial com cardápio diferente pediria
    -- migração para separar — e separar depois é mais caro que juntar.
    id_unidade      integer NOT NULL REFERENCES unidades(id),
    -- ⚠️ **`origem` nasce com uma opção só, e mesmo assim é COLUNA.** Hoje todo
    -- catálogo é um **PDF** importado e mostrado no site de reservas, e seria
    -- tentador não guardar o que não varia. Mas no dia em que entrar a segunda
    -- origem — o cardápio montado item a item aqui dentro — os catálogos
    -- antigos precisam continuar sabendo de onde vieram; um DEFAULT posto
    -- naquele dia mentiria sobre o passado.
    -- ⚠️ **NÃO confundir com `PDV`.** Este módulo nasceu com a sigla errada por
    -- um engano de digitação, e a primeira versão inteira foi escrita em cima
    -- dela. PDF é arquivo; PDV é o caixa, e vive em `services/pdv/`.
    origem          varchar(20) NOT NULL DEFAULT 'PDF',
    -- 🔑 **O nome que o CLIENTE lê**, não o nome interno. "Cardápio de verão" é
    -- o que aparece no site; quem opera reconhece pelo mesmo nome, e ter dois
    -- seria manter dois e divergir num deles.
    nome            varchar(120) NOT NULL,
    -- ⚠️ **As duas pontas são OPCIONAIS, e querem dizer coisas diferentes.**
    -- Sem `publica_de`, vale desde já; sem `publica_ate`, vale sem prazo. O
    -- cardápio permanente da casa não tem período, e exigir datas dele obrigaria
    -- a inventar um "até 2099" que ninguém entenderia depois.
    publica_de      date,
    publica_ate     date,
    -- RASCUNHO | ATIVO | INATIVO — as três que o dono nomeou.
    -- ⚠️ Nasce RASCUNHO: catálogo que nasce ativo é catálogo publicado antes de
    -- alguém conferir o que tem dentro.
    situacao        varchar(10) NOT NULL DEFAULT 'RASCUNHO',
    observacao      text,
    criado_por      integer REFERENCES usuarios(id),
    criado_em       timestamptz NOT NULL DEFAULT now(),
    atualizado_em   timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_catalogo_situacao
        CHECK (situacao IN ('RASCUNHO', 'ATIVO', 'INATIVO')),
    -- ⚠️ **O período só se compara quando as DUAS pontas existem.** Com uma
    -- nula a comparação é nula, e um CHECK nulo passa — que é o que se quer:
    -- "sem prazo" não é um período invertido.
    CONSTRAINT ck_catalogo_periodo
        CHECK (publica_de IS NULL OR publica_ate IS NULL OR publica_ate >= publica_de)
);

-- ⚠️ **Nome único por LOJA, sem caixa.** Dois "Cardápio de verão" na mesma casa
-- são o mesmo catálogo cadastrado duas vezes, e quem publica escolhe um dos dois
-- sem saber qual. `lower()` porque "Verão" e "verão" são o mesmo nome para
-- quem lê. É a mesma forma de `ux_ficha_modos_nome`.
CREATE UNIQUE INDEX IF NOT EXISTS ux_catalogo_nome
    ON catalogos (id_unidade, lower(nome));

-- A lista da tela abre por loja, com os ativos na frente.
CREATE INDEX IF NOT EXISTS ix_catalogo_loja
    ON catalogos (id_unidade, situacao);

-- 🔑 **Vários catálogos ATIVOS ao mesmo tempo são permitidos** (decisão do dono,
-- 21/09/2026: *"vários, sem trava nenhuma"*). Por isso NÃO há índice único
-- sobre `situacao = 'ATIVO'` nem restrição de períodos sobrepostos.
-- ⚠️ **A consequência fica escrita aqui para não surpreender depois**: quem for
-- publicar no site precisa de uma regra que escolha ENTRE os ativos, e essa
-- regra ainda não existe. Ela é da fatia do site, não do cadastro.

-- ---------------------------------------------------------------------------
-- Permissões
-- ---------------------------------------------------------------------------
-- ⚠️ **As chaves são concedidas AQUI, e não é redundância** — mesma razão da
-- migração 068: a 002 re-semeia os papéis de sistema ANTES desta rodar, então o
-- administrador ficaria sem as chaves até o restart seguinte.
INSERT INTO permissoes (chave, modulo, descricao, ordem) VALUES
    ('catalogos.ver',    'Reservas', 'Ver os catálogos do site de reservas', 680),
    ('catalogos.editar', 'Reservas', 'Criar, alterar e publicar catálogos', 690)
ON CONFLICT (chave) DO UPDATE
    SET modulo = EXCLUDED.modulo, descricao = EXCLUDED.descricao, ordem = EXCLUDED.ordem;

-- 🔑 **Quem recebe**: Administrador e Gerente, que é o que a 002 já faria.
-- ⚠️ **Salão fica de fora, embora as outras chaves de Reservas o incluam.**
-- Garçom atende telefone e marca mesa; publicar o que a casa mostra no site é
-- decisão de quem responde pelo cardápio. Libera-se em Papéis se a casa quiser.
-- ⚠️ **As chaves são nomeadas uma a uma, não por módulo.** Elas moram em
-- `Reservas` agora, e um `x.modulo = 'Reservas'` aqui reconcederia as três
-- chaves da 068 a quem alguém tivesse tirado de propósito.
INSERT INTO papel_permissoes (id_papel, chave)
SELECT p.id, x.chave
  FROM papeis p CROSS JOIN permissoes x
 WHERE p.sistema AND x.chave IN ('catalogos.ver', 'catalogos.editar')
   AND p.nome IN ('Administrador', 'Gerente')
ON CONFLICT DO NOTHING;

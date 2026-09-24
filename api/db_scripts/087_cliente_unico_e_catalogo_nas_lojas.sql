-- Duas lojas no mesmo site: o cliente é UM, o catálogo escolhe onde aparece.
--
-- 🔑 **Pedido do dono (24/09/2026):** *"o cadastro de cliente seria o mesmo. A
-- reserva, os catálogos e o entre em contato seriam separados por loja. No
-- cadastro do catálogo, podemos ter um Visível nas Lojas, aí o usuário marca onde
-- ficaria visível."*
--
-- ⚠️ **Idempotente de ponta a ponta**, porque roda no start e reescreve dado: a
-- fusão só acha o que ainda está repetido, e cada DDL tem o seu IF (NOT) EXISTS.

-- ---------------------------------------------------------------------------
-- 1. O cliente passa a ser da CASA, não da loja
-- ---------------------------------------------------------------------------
-- ⚠️ **Antes do índice único por telefone, junta os repetidos.** A mesma pessoa
-- pode ter se cadastrado nas duas lojas (o índice antigo era por loja + telefone).
-- Fica o cadastro MAIS ANTIGO; o que ele não tinha (gênero, cidade, nascimento) é
-- completado pelos outros, e as reservas dos outros passam a apontar para ele.

UPDATE reserva_clientes f
   SET genero     = COALESCE(f.genero, o.genero),
       cidade     = COALESCE(f.cidade, o.cidade),
       nascimento = COALESCE(f.nascimento, o.nascimento)
  FROM (SELECT telefone,
               min(id) AS fica,
               (array_agg(genero ORDER BY id) FILTER (WHERE genero IS NOT NULL))[1] AS genero,
               (array_agg(cidade ORDER BY id) FILTER (WHERE cidade IS NOT NULL))[1] AS cidade,
               (array_agg(nascimento ORDER BY id) FILTER (WHERE nascimento IS NOT NULL))[1]
                   AS nascimento
          FROM reserva_clientes
         GROUP BY telefone
        HAVING count(*) > 1) o
 WHERE f.id = o.fica;

UPDATE reservas r
   SET id_cliente = d.fica
  FROM (SELECT id, min(id) OVER (PARTITION BY telefone) AS fica
          FROM reserva_clientes) d
 WHERE r.id_cliente = d.id AND d.id <> d.fica;

DELETE FROM reserva_clientes c
 USING (SELECT id, min(id) OVER (PARTITION BY telefone) AS fica
          FROM reserva_clientes) d
 WHERE c.id = d.id AND d.id <> d.fica;

DROP INDEX IF EXISTS ux_reserva_cliente_fone;
CREATE UNIQUE INDEX IF NOT EXISTS ux_reserva_cliente_telefone ON reserva_clientes (telefone);

-- ⚠️ `id_unidade` FICA, como "a loja onde a pessoa se cadastrou" — é dado de
-- marketing que a casa pode querer. Mas deixa de mandar: vira opcional, e apagar
-- uma loja não pode mais apagar clientes que as outras atendem.
ALTER TABLE reserva_clientes ALTER COLUMN id_unidade DROP NOT NULL;
ALTER TABLE reserva_clientes DROP CONSTRAINT IF EXISTS reserva_clientes_id_unidade_fkey;
ALTER TABLE reserva_clientes
    ADD CONSTRAINT reserva_clientes_id_unidade_fkey
        FOREIGN KEY (id_unidade) REFERENCES unidades(id) ON DELETE SET NULL;

-- ---------------------------------------------------------------------------
-- 2. O catálogo escolhe em que lojas aparece
-- ---------------------------------------------------------------------------
-- 🔑 **`catalogos.id_unidade` continua sendo a DONA** (quem edita, pela loja em
-- que a pessoa está no sistema). Esta tabela diz só onde o CLIENTE o vê.
CREATE TABLE IF NOT EXISTS catalogo_lojas (
    id_catalogo integer NOT NULL REFERENCES catalogos(id) ON DELETE CASCADE,
    id_unidade  integer NOT NULL REFERENCES unidades(id) ON DELETE CASCADE,
    PRIMARY KEY (id_catalogo, id_unidade)
);
CREATE INDEX IF NOT EXISTS ix_catalogo_lojas_unidade ON catalogo_lojas (id_unidade);

-- ⚠️ **Todo catálogo que já existe nasce visível na PRÓPRIA loja** — é o que o
-- site mostrava até aqui. Sem isto, os cardápios no ar sumiriam no deploy.
-- Idempotente: só acrescenta o par que ainda não existe.
INSERT INTO catalogo_lojas (id_catalogo, id_unidade)
SELECT c.id, c.id_unidade
  FROM catalogos c
 WHERE NOT EXISTS (SELECT 1 FROM catalogo_lojas l WHERE l.id_catalogo = c.id)
ON CONFLICT DO NOTHING;

-- ---------------------------------------------------------------------------
-- 3. O WhatsApp da LOJA
-- ---------------------------------------------------------------------------
-- 🔑 "Entre em contato separado por loja": cada casa com o seu número. Nulo =
-- vale o da empresa, que é o de sempre.
ALTER TABLE unidades ADD COLUMN IF NOT EXISTS whatsapp varchar(30);

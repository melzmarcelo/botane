-- 110 — A produção feita NA HORA sabe de qual venda nasceu. Idempotente.
--
-- 🔑 **Achado do dono (08/10/2026), em produção:** vendeu um Café Passado (ficha
-- NA_HORA, um insumo), o estoque andou certo — produziu, baixou o pó, baixou o
-- café. Cancelou a venda: o café voltou, e o pó NÃO.
--
-- O cancelamento procura os movimentos por `origem_tipo = 'VENDA'`, e só a saída
-- do produto vendido nasce assim. A produção que a venda disparou grava os dela
-- com `origem_tipo = 'PRODUCAO'` apontando para `producoes.id` — e nada ligava
-- essa produção à venda. Sobrava a produção inteira: o produzido com saldo (que
-- "na hora" nunca tem) e o insumo consumido por uma venda que não existiu.
--
-- ⚠️ Nulo é o normal: produção da agenda ou lançada à mão não tem venda.
ALTER TABLE producoes
    ADD COLUMN IF NOT EXISTS id_venda bigint REFERENCES vendas(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS ix_producao_venda ON producoes (id_venda)
    WHERE id_venda IS NOT NULL;

COMMENT ON COLUMN producoes.id_venda IS
    'A venda que disparou esta produção (produto NA_HORA). É por aqui que o '
    'cancelamento da venda acha o consumo de insumo a estornar. Nulo nas demais.';

-- 🔑 **As produções que já existem ganham o vínculo**, senão cancelar uma venda
-- de ontem continuaria deixando o insumo para trás.
-- A venda e a produção dela nascem na MESMA transação, e `now()` é o instante
-- em que a transação começou: `vendas.importada_em` e `producoes.data` saem
-- idênticos, até o microssegundo. Somado ao documento, que a produção guarda na
-- observação ("Venda <documento>"), o par é exato.
-- ⚠️ Venda sem documento fica de fora: a observação dela é só "Venda", e num
-- lote com várias o instante sozinho não diz qual é qual. Vínculo errado
-- estornaria o insumo de outra venda — pior do que vínculo nenhum.
-- ⚠️ `HAVING count(*) = 1`: o mesmo documento pode existir em duas origens na
-- mesma loja. Com mais de uma candidata, não se escolhe.
-- ⚠️ Só onde está nulo: rodar de novo não mexe no que já foi ligado.
UPDATE producoes p
   SET id_venda = alvo.id_venda
  FROM (SELECT pr.id AS id_producao, min(v.id) AS id_venda
          FROM producoes pr
          JOIN vendas v ON v.id_unidade = pr.id_unidade
                       AND v.importada_em = pr.data
                       AND v.documento IS NOT NULL
                       AND pr.observacao = 'Venda ' || v.documento
          JOIN venda_itens vi ON vi.id_venda = v.id AND vi.id_produto = pr.id_produto
         WHERE pr.id_venda IS NULL
         GROUP BY pr.id
        HAVING count(DISTINCT v.id) = 1) alvo
 WHERE p.id = alvo.id_producao AND p.id_venda IS NULL;

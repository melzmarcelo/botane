-- O identificador do produto no Omie, guardado no item da nota.
--
-- Por que a coluna existe: o item do recebimento traz `nIdProduto`, o mesmo
-- número que o catálogo grava em `produtos.codigo_omie`. É o de-para que o Omie
-- já fez — mais confiável que EAN (que muitos itens não têm) e que semelhança
-- de texto (que erra). Numa conta real, 109 de 114 itens encontraram o produto
-- por aqui.
--
-- Só que ele vinha na resposta e se perdia: ficava no `bruto` da nota e não no
-- item. Quem importasse as notas ANTES do catálogo — a ordem natural, porque
-- é a nota que revela quais insumos a casa compra — ficava com todos os itens
-- pendentes, sem nada para reconciliar depois senão o JSON cru.

ALTER TABLE nota_itens ADD COLUMN IF NOT EXISTS codigo_omie varchar(40);

CREATE INDEX IF NOT EXISTS ix_nota_itens_codigo_omie
    ON nota_itens (codigo_omie) WHERE codigo_omie IS NOT NULL;

-- Repõe o que já tinha entrado antes da coluna existir. O número está no
-- `bruto` da nota — o JSON da resposta do Omie, guardado justamente para que
-- nada dependa de ter sido lido na hora certa. Casa item a item pela sequência.
UPDATE nota_itens i
   SET codigo_omie = x.id_produto
  FROM notas_entrada n
       CROSS JOIN LATERAL jsonb_array_elements(
           coalesce(n.bruto -> 'itensRecebimento', '[]'::jsonb)) AS item(dado)
       CROSS JOIN LATERAL (
           SELECT (item.dado -> 'itensCabec' ->> 'nSequencia')::int AS seq,
                  item.dado -> 'itensCabec' ->> 'nIdProduto'       AS id_produto
       ) AS x
 WHERE i.id_nota = n.id
   AND i.seq = x.seq
   AND i.codigo_omie IS NULL
   AND x.id_produto IS NOT NULL
   AND n.bruto ? 'itensRecebimento';

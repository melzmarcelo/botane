-- Quem absorveu este cadastro — um PONTEIRO, e não uma frase.
--
-- 🔑 **O rastro da fusão só existia em TEXTO.** `produtos_vinculo.fundir`
-- escrevia na observação do arquivado "Fundido em ACU1-200000 — ACUCAR …", e
-- era daí que qualquer conserto precisava extrair o sobrevivente. Serve para
-- uma pessoa ler; não serve para o sistema decidir. Sem coluna não há como
-- perguntar "para onde vai este item de nota?" sem fazer regex em observação.
--
-- ⚠️ **A carga retroativa lê a MESMA frase**, e casa pelo `codigo` do
-- sobrevivente. Só preenche onde está nulo: rodar de novo não reescreve nada, e
-- quem já tiver o ponteiro certo não é tocado por uma leitura de texto.
--
-- ⚠️ **Só para cadastro ARQUIVADO.** Produto ativo não foi absorvido por
-- ninguém, e um ponteiro nele seria uma afirmação falsa.
--
-- ⚠️ A referência é para `produtos` e sem `ON DELETE`: produto não se apaga
-- neste sistema, se arquiva. Se um dia se apagar, o erro é melhor que o
-- ponteiro pendurado.
ALTER TABLE produtos ADD COLUMN IF NOT EXISTS fundido_em integer REFERENCES produtos(id);

CREATE INDEX IF NOT EXISTS ix_produtos_fundido_em ON produtos (fundido_em)
  WHERE fundido_em IS NOT NULL;

-- Carga retroativa a partir da observação deixada pela fusão.
-- ⚠️ `(.+?) — ` com o travessão do texto original: o código pode ter ponto e
-- hífen ("055.095.050-4"), então recortar por classe de caracteres erraria.
-- ⚠️ `a.id <> b.id` porque um cadastro não se funde em si mesmo — e um código
-- repetido no histórico faria exatamente isso.
UPDATE produtos a
   SET fundido_em = b.id
  FROM produtos b
 WHERE a.fundido_em IS NULL
   AND NOT a.ativo
   AND a.observacao LIKE '%Fundido em %'
   AND b.codigo = substring(a.observacao from 'Fundido em (.+?) — ')
   AND a.id <> b.id;

COMMENT ON COLUMN produtos.fundido_em IS
  'Cadastro que absorveu este numa fusao. Nulo em produto que nunca foi '
  'absorvido. Preenchido por produtos_vinculo.fundir e, retroativamente, pela '
  'migracao 063 a partir da observacao.';

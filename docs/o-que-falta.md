# O que falta

Revisado em 10/11/2026 (versão 1.3.11, migração 156), conferindo no código cada item da
lista anterior (de 02/09/2026) e somando as pendências registradas nas memórias dos módulos
(`docs/memoria/`). O primeiro levantamento foi feito em 25/08/2026 a partir do
[`MAPEAMENTO.md`](../MAPEAMENTO.md).

---

## 🟠 Código que falta

### Remessa de VÁRIOS produtos numa vez (31/08/2026)

`POST /transferencias` já aceita N itens, e a tela de recebimento confere item a item — mas o
**envio** só nasce por *Estoque ▸ Ajustes*, um produto de cada vez, então na prática cada
remessa tem um item só. Quem manda a produção da semana para a filial despacha oito produtos
num carro só, e hoje isso vira oito remessas para o outro lado conferir uma a uma.

Falta a tela `/transferencias/nova`: escolher origem, destino e ir somando produtos, no modelo
de `/compras/nova`. **O servidor não muda.** ⚠️ Vale a mesma prévia do inventário: quantos
itens, e o saldo de cada um na prateleira de origem, ANTES do botão. Só dói quando a filial
abrir (ver "Segunda loja" abaixo).

### Engenharia de cardápio

`cmv.margem_por_prato` já entrega o que cada prato vendeu, custou e deixou. Falta a matriz que
cruza **popularidade × margem** e classifica em estrela, cavalo de batalha, quebra-cabeça e
abacaxi — que é o que transforma a lista numa decisão de cardápio.

### Conciliação por semelhança fora do Python

Medido em 25/08: **296 ms por item pendente**, dos quais 94% é comparação de texto contra os
produtos. Uma nota com 50 itens desconhecidos leva 15 s. O `pg_trgm` está disponível no
servidor e **segue sem uso** — com índice trigrama isso vira milissegundos.

### Assistente no WhatsApp — o que ficou para depois

As cinco etapas do estudo (`docs/assistente-whatsapp-estudo.md`) estão construídas (1.3.5 a
1.3.9). Falta:
- **O número de verdade** conectado à Meta — o código está pronto e só roda simulado até lá.
- **Etiqueta e saída/perda pelo WhatsApp**, pela mesma trilha de prévia + botão Confirmar da
  produção.

---

## 🟡 Infraestrutura

- **Filesystem efêmero no App Platform**: `api/uploads/` (logo, fotos) e `api/arquivos/emails/`
  somem a cada deploy. A saída é o **Spaces** — `api/arquivos.py` já foi escrito para a troca.
- **Python preso em `3.13.13`** (`api/.python-version`), de propósito e por pouco tempo, porque
  o buildpack da DO pedia uma versão que não existia lá. Voltar para `3.13` assim que o
  buildpack aceitar (ver `docs/deploy.md`).
- **Componente estático `reservas`** no app da DO: desde 16/10 o ingress de `reservas` aponta
  para o `web`. Remover o componente quando estiver estável — só junto com o dono.
- **Lighthouse** do site do cliente, pendente desde o Cardápio Vivo.

---

## 🔵 Dados no ar (cadastro, não código)

- **Limpeza dos insumos em rascunho** (ver memória `botane-limpeza-rascunhos`): hortifruti
  (seção 2) feito em 06/10; a equipe segue pela tela desde 17/10. Faltam as seções 1 e 3 a 7. O
  ponto de partida é [`pre-analise-unidades.md`](pre-analise-unidades.md); ler o estado atual
  com `detalhe_produto` antes de propor lote, porque a lista envelhece sozinha.
- **Vínculo errado**: o código Omie **000172 (sêmola)** continua ligado ao TOMATE CEREJA (137) —
  nota de sêmola entraria como tomate. O conector não desvincula: Produto ▸ Vinculados ▸
  desvincular, pela tela.
- **Pães da Luciani**: desde 23/10 os códigos 50/51 estão desvinculados do PÃO BOTANE (3448) e
  do PÃO DE GRÃOS (3449); a próxima nota pode cair em COSTELA (1222) ou TEQUILA (772). A
  correção está na memória `botane-paes-luciani`.
- **LeadsFood**: enquanto a casa usar o LeadsFood, os dados de lá andam. No dia da troca,
  exportar de novo e reimportar (os selos em aberto valem como foto — o arquivo tem de ser a
  lista inteira).
- **Fichas técnicas**: eram zero em 25/08 e eram o maior buraco do CMV teórico. Conferir no ar
  a cobertura atual (painel do CMV, "receita com custo") antes de tratar como resolvido.

---

## ⚪ Só quando a filial abrir

- **No ar só existe UMA loja.** As duas lojas estão provadas na base local
  (`smoke_duas_lojas.py`), mas vazamento entre lojas só aparece com duas. Módulo novo com
  `id_unidade` pede varredura de isolamento antes da abertura.
- A tela de remessa com vários produtos (acima) passa a ser necessária.

---

## 🟡 Limitação conhecida — retroativo não reprocessado

`saldo_apos`/`custo_medio_apos` são calculados na **ordem de lançamento** — decisão de projeto:
recalcular por data faria o CMV de ontem mudar sozinho. A consequência é que um movimento
gravado hoje com data de trás carrega a fotografia do momento em que foi gravado, e a
identidade `inicial + entradas − saídas = final` pode abrir num recorte que termina antes de
hoje.

Mitigado desde então: o parâmetro `bloquear_retroativo` (ligado por padrão) trava o lançamento
retroativo para quem não tem `estoque.retroativo`, e existe o reprocessamento do estoque. O que
**não** se acerta sozinho é o retroativo lançado e não reprocessado (ver
`docs/memoria/estoque.md`).

---

## ✅ Feito desde a lista anterior

- **O envio de e-mail não segura mais a transação** (1.3.15, 11/11/2026) — `email.preparar`
  (com banco) e `email.despachar` (sem banco). A recuperação pública responde na hora e envia
  depois da resposta (falha vira `recuperacao_falhou` na auditoria); o token é gravado antes de
  qualquer envio, e a tela de Usuários recebe o link mesmo com o SMTP recusando; o último status
  do botão de teste passou a guardar o ERRO (o 502 desfazia a gravação). `smoke_senha` §9b.
- **Foto na ficha e no produto** — upload, exibição e cópia na nova versão (ver
  `docs/memoria/producao.md`).
- **Cobertura por receita** — o CMV mostra a % da receita com custo, não só a cobertura de ficha.
- **Classificar produtos em massa** — "Alterar em lote" na lista de produtos; a reestruturação
  de setores, categorias, locais e grupo de CMV entrou no ar em 25/10.
- **Unificar cadastros duplicados** — botão Vincular/fusão (27/08) e a tela de duplicados.
  🔑 A detecção automática por semelhança de nome foi construída e REMOVIDA: errava nos dois
  sentidos, e nenhum piso separa os casos. Quem reconhece produto é gente. ⚠️ Onde os DOIS
  cadastros têm movimento, a fusão é recusada — o razão é append-only.
- **`cest` no produto** — migração 031.
- **Deploy e backup** — no ar em `sistema.botanedeliecafe.com.br` (ver `docs/deploy.md`).
- **PDV Legal** — vendas, de-para e baixa funcionando. ⚠️ Segue valendo: **não case código de
  cardápio com código de produto** (a primeira cascata criou 78 vínculos errados, REDBULL →
  LIMÃO TAITY).

---

## Divergências entre o mapeamento e o que foi construído

Coisas que mudaram com bom motivo e que o `MAPEAMENTO.md` ainda não registra:

1. **"A venda não baixa estoque"** (seção 9, decisão 1) deixou de valer. A venda baixa todo
   produto que controla estoque. O receio original — contar duas vezes o mesmo quilo de carne
   — não se materializa porque o insumo sai pela produção e o produto PRONTO sai pela venda;
   são movimentos de coisas diferentes. Sem essa baixa, o CMV real saía subestimado e a
   primeira contagem cobria o buraco como "ajuste de inventário".
2. **`modo_producao`** (`PARA_ESTOQUE` / `NA_HORA`) não existia no mapeamento. Sem ele, a casa
   venderia mil cafés e o pó continuaria inteiro no razão.
3. **`KIT`** era um tipo previsto e não implementado; hoje é `services/kits.py`.

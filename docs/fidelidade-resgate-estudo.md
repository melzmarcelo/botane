# Vincular o documento ao resgate do prêmio da fidelidade — estudo

🔑 **Pedido do dono (03/11/2026):** *"analisa o estudo para vincular o documento com o resgate
de prêmios."* Retoma o pendente de 28/09/2026 (`docs/memoria/reservas.md`, "PENDENTE — o
consumo (resgate) do prêmio") com o que a migração 134 trouxe depois.

Estado: ✅ **construído na 1.2.1 (migração 147, 03/11/2026)** — código obrigatório. Cancelar o
documento devolve o prêmio só quando foi o DOCUMENTO quem entregou (o do balcão continua
entregue). Detalhes em `docs/memoria/reservas.md`.

## 1. Os dois lados, hoje, sem ligação

| | Entrega do prêmio | Documento com motivo Prêmio |
|---|---|---|
| Onde | Fidelidade → Prêmios ou Painel (`fidelidade.entregar`) | Vendas → Lançar, motivo "Prêmio" (134) |
| O que grava | `fidelidade_premios.usado_em / usado_por / id_unidade_uso`; tira o selo do dia | `vendas` com `motivo='PREMIO'`, `consumo_interno=true` |
| Estoque | nada | baixa os pratos como `SAIDA_CONSUMO_INTERNO`, pelo custo |
| CMV | nada | fora da receita; entra em `consumo_por_motivo` e no painel Documentos por motivo |
| Sabe de quem é | sim (cliente, código) | não |
| Sabe quanto custou | não | sim |

`vendas.id_premio` (FK para `fidelidade_premios`) já existe desde a 134, com o comentário
"previsto para a fidelidade, ainda sem uso". Falta a regra que a preenche.

**No ar (03/11/2026):** 41 prêmios (importados do LeadsFood + os novos), 34 entregues, 6 a
entregar, 1 vencido. Cerca de 3 a 4 almoços por mês, sempre "Almoço cortesia (terça a sexta)".
Nenhum dos entregues tem documento ligado — o custo do programa hoje é desconhecido.

🔑 **Resposta do dono (03/11/2026):** *"é lançado no PDV, mas como documento que não vem para o
Botané, ele é lançado posteriormente à mão."* Logo: o documento manual com motivo Prêmio é o
ÚNICO registro do almoço no Botané (sem baixa em dobro, sem receita zero no food cost), e ele
chega DEPOIS da entrega. O caso principal é, portanto, **prêmio já entregue no balcão → o
documento só liga**; entregar pelo documento é o caso de quem não passou por Prêmios.

## 2. Proposta: uma ação só, no lugar de duas

🔑 **O documento com motivo Prêmio ENTREGA o prêmio.** Na tela Lançar, escolhido o motivo
Prêmio, aparece o campo **Código do prêmio** (6 letras). Ao gravar, na MESMA transação:

1. confere o código com as regras de `entregar` (existe, não entregue, não vencido, já vale,
   dia de consumo);
2. grava o documento com `id_premio`, baixa o estoque como já faz;
3. marca o prêmio como entregue (`usado_em`, `usado_por`, `id_unidade_uso` = loja do documento)
   e tira o selo do dia, como já faz.

Se qualquer passo falha, nada é gravado: não existe prêmio entregue sem documento nem documento
apontando para prêmio que continua disponível.

E o caminho inverso, para quem começa pelo balcão: **Entregar** em Prêmios ganha o botão
**"Lançar o que foi servido"**, que abre Lançar com motivo Prêmio e o código preenchidos. O
prêmio entregue sem documento aparece num filtro novo, **"Entregue sem documento"**, para a
gerência completar depois.

### Regras de banco (regra 8: idempotência é do banco)

- Índice único parcial: `vendas (id_premio) WHERE id_premio IS NOT NULL AND NOT cancelada` —
  um prêmio, um documento, venha da tela, do conector ou de duas abas ao mesmo tempo.
- CHECK: `id_premio IS NULL OR motivo = 'PREMIO'`.
- Prêmio travado com `SELECT … FOR UPDATE` (como `entregar` já faz) antes de gravar.

### Casos de borda

| Caso | Comportamento proposto |
|---|---|
| Documento com data retroativa (lançado no dia seguinte) | Regras conferidas na DATA DO DOCUMENTO; `usado_em` = data do documento |
| Prêmio já entregue no balcão, sem documento | O campo aceita o código e só liga (não entrega de novo) |
| Prêmio já ligado a outro documento | Recusa, dizendo qual documento |
| Documento cancelado | Desliga e **devolve o prêmio** (volta a disponível se não venceu), auditado — ver pergunta 3 |
| Alterar o documento e trocar o motivo para outro | Mesmo efeito do cancelamento |
| Motivo Prêmio sem código | Ver pergunta 2 |
| Prêmios antigos do LeadsFood (34 entregues) | Ficam sem documento; não há o que ligar |

## 3. O que passa a existir

- **Custo do programa por mês**: soma das saídas dos documentos com `id_premio`, no Painel da
  fidelidade (cartão novo) e em Documentos por motivo (que já separa o motivo Prêmio).
- **Custo por prêmio**: na ficha do cliente e no grid de Prêmios, o prato servido e o custo.
- **Conferência**: prêmios entregues sem documento e documentos Prêmio sem código.
- Conector: `lancar_vendas` aceita `codigo_premio`; `entregar_premio` devolve se há documento.

## 4. O que não muda

- O PDV continua de fora: o Botané não escreve no PDV.
- A regra do prêmio (vale da próxima visita, dias de consumo, sem selo na visita do prêmio)
  continua num lugar só — a ligação chama a mesma função que o balcão.
- Fora da receita continua sendo `consumo_interno`; o motivo Prêmio já faz isso.

## 5. Perguntas para o dono

1. ~~O almoço do prêmio é lançado no PDV hoje?~~ **Respondida (03/11):** sim, num documento
   do PDV que não é importado; no Botané entra só pelo lançamento manual, depois. O filtro
   "Entregue sem documento" vira a lista do que falta lançar.
2. ~~O código do prêmio é obrigatório no motivo Prêmio?~~ **Respondida (03/11): sim.** Recomendado: sim, quando a loja usa
   fidelidade — sem ele não há custo por programa. Brinde que não é da fidelidade usa
   "Brinde/Aniversário".
3. **Cancelar o documento devolve o prêmio ao cliente?** Recomendado: sim, se ainda não venceu.
4. **Quem lança**: o caixa, na hora, ou a gerência no fim do dia? Muda se o caminho principal é
   a tela Lançar ou o botão em Prêmios.

## 6. Tamanho e ordem

Uma entrega pequena (uma migração com índice e CHECK, regra no `vendas` + `fidelidade`, campo na
tela, filtro em Prêmios, cartão de custo no Painel), com seção nova em `smoke_venda_motivo.py` e
`smoke_fidelidade.py` e um passo na bateria do navegador. A resposta 1 manteve o desenho; falta a 2
(as 3 e 4 têm padrão recomendado).

# Padrões de UI

> Extraído do CLAUDE.md original (seções "O que já existe" e "Armadilhas já pagas").
> Consultar antes de mexer nesta área do sistema.

## O que já existe

- **Paginação**: as listas grandes devolvem o total em **`X-Total`** (via `count(*) OVER ()`,
  na mesma varredura) e o front usa `api.listar()`. ⚠️ O header precisa estar em
  `expose_headers` do CORS, senão o navegador não o entrega à tela.

- 🔑 **A janela (`Modal`) era do tamanho do CONTEÚDO, e conteúdo longo saía da tela sem
  rolagem nenhuma** (29/08/2026). A de exportação, com cinco filtros, passava de mil pixels:
  num notebook os últimos campos e o botão de baixar ficavam fora, **e não havia barra de
  rolagem em lugar nenhum** — porque `Modal` trava o `overflow` do corpo da página enquanto
  está aberta. O defeito era do componente, não daquela tela: valia para toda janela do
  sistema, e só apareceu quando uma delas cresceu.
  Agora o cartão é limitado pela altura da JANELA (`max-h-[calc(100dvh-4rem)]`), vira
  `flex-col`, e só o miolo rola (`min-h-0 flex-1 overflow-y-auto` — sem o `min-h-0` um filho
  de flex não encolhe abaixo do próprio conteúdo, e o `overflow` não teria o que rolar).
  ⚠️ **`dvh`, não `vh`**: no celular a barra de endereço entra na conta do `vh`, e o pé do
  cartão fica atrás dela.
  ⚠️ **`Modal` ganhou `rodape`**, que fica FORA da rolagem: botão de ação que rolou para fora
  da vista é botão que não existe, e quem não o acha conclui que a janela não tem saída. A
  contagem da prévia fica ao lado dele porque é o número que se olha imediatamente antes de
  clicar.
  ⚠️ **A bateria rodava a 1440×1000 e não pegaria isso.** A checagem nova MEDE numa tela de
  notebook de verdade (1440×760) e devolve o tamanho depois — altura generosa demais no teste
  esconde exatamente a classe de defeito que o teste existe para achar.

- **Aviso de ação flutua** (`components/aviso-flutuante.tsx`, 20/08/2026): sucesso e erro de
  AÇÃO saem por `useAviso()` e aparecem presos ao canto inferior — a mensagem ficava no topo e
  o botão de salvar está no fim de um formulário longo, então quem clicava não via confirmação
  nenhuma e clicava de novo. Sucesso some em 6 s; **erro fica até fecharem**. O aviso pode levar
  UMA ação ("cadastrar outro"), que é a resposta ao "cadastrei, e agora?".
  ⚠️ **Os dois somem sozinhos** (26/08/2026): sucesso em 6 s, erro em 14 — a frase do erro é
  mais longa. Antes o erro ficava até alguém fechar, e uma pilha que não se limpa acaba tapando
  a tela em uso. O que torna isso seguro é o aviso **parar de contar enquanto o ponteiro está
  em cima** (ou o foco dentro): o medo real era a mensagem sumir no meio da leitura. A barrinha
  embaixo mostra quanto falta — sem ela, o aviso sumindo parece a tela piscando.
  ⚠️ Erro de **carregamento** continua inline no cartão (é ele que explica a tela vazia) — a
  regra de bolso: mensagem com "Falha ao carregar" fica; o resto flutua.

- 🔑 **`localStorage` está VAZIO até alguém mexer no seletor de loja** (31/08/2026), e a tela da
  remessa foi a primeira a DECIDIR com base nele: `Number(unidadeAtual() || 0)` dava **zero**
  para quem nunca trocou de loja — que é a maioria —, e aí nem o botão de receber nem o de
  cancelar apareciam. Quem abrisse a própria remessa não tinha o que fazer com ela. O layout
  disfarçava o buraco porque só usava o valor para MARCAR a opção do `<select>`, com
  `?? eu.unidades[0].id` na frente.
  ⚠️ A resposta mora em `useSessao().unidade` e **espelha `seguranca.unidade_atual` passo a
  passo**: a escolhida no seletor, senão a matriz para quem enxerga todas, senão a de menor id.
  "O primeiro da lista" como reserva NÃO é o padrão do servidor quando a matriz não é a de
  menor id — o seletor mostraria uma loja e o pedido iria para outra.
  ⚠️ Ler `localStorage` no render é seguro **ali** porque `eu` nasce nulo: a primeira pintura do
  cliente é igual à do servidor, e o valor só aparece depois do `/auth/me`.

- 🔑 **4px de raio é canto vivo disfarçado** (30/08/2026). A tela é feita de caixas, e num
  raio tão curto nenhuma tem forma perceptível — só borda. `.cartao` foi para **14px** com
  **sombra dupla**: uma linha de 1px logo abaixo, que separa do papel, e um halo largo e
  claríssimo, que dá a altura. Sombra única e escura é o que faz uma tela parecer de 2012.
  Botão e campo foram para 9px — canto vivo dentro de cartão redondo são duas linguagens na
  mesma tela, e a mais dura é a que se nota.
  🔑 **E o aviso não era um balão, era uma LINHA**: barra de 2px à esquerda com o texto solto
  no fundo da página, lendo como mais um parágrafo com a cor trocada. Virou `.aviso` +
  `.aviso-{info,ok,erro}` — fundo tingido, borda da mesma família, 12px de canto. Entraram os
  tokens que faltavam (`--color-erro-claro`, `--color-alerta-claro`); o `erva-claro` já
  existia e servia só ao verde. ⚠️ A forma mora no CSS, não em oito utilitárias repetidas no
  componente: o aviso aparece em quase toda tela, e um balão diferente por página seria a
  primeira coisa a divergir.

## Armadilhas já pagas

- Componente `Aviso` renderiza `<p>`: não colocar dentro de outro `<p>` (erro de hidratação).

- **Paginação é o PADRÃO de todo grid** (25/08/2026): `components/paginacao.tsx` —
  `usePaginacao(nome, { padrao, filtros })` + `<Paginacao p={pag} rotulo="…" />`. O rodapé diz
  "1–20 de 2.183", deixa escolher **20, 50 ou 100** e **lembra a escolha** (localStorage, por
  lista: conferir estoque numa tela grande pede 100, o celular pede 20).
  ⚠️ **O corte é do SERVIDOR** — trazer tudo e fatiar no navegador só troca a mentira de lugar.
  ⚠️ **Trocar o filtro volta para a primeira página** (é o que `filtros:` faz): quem está na
  página 7 e digita uma busca cairia numa tela vazia sem nada explicando.
  ⚠️ A preferência é lida num **efeito**, não no estado inicial: o servidor renderiza a tela
  antes de existir `localStorage`, e valores diferentes dos dois lados quebram a hidratação.
  Aplicado em produtos, fornecedores, notas, saldos, razão, fichas, vendas, inventários,
  produções, auditoria, usuários e movimentação do CMV. **Fora, de propósito**: tabelas de
  apoio, lojas, papéis e tudo que é detalhe de UM registro (itens da nota, insumos da ficha) —
  são poucos por natureza, e rodapé de página em lista de três linhas é ruído.
  ⚠️ **A movimentação do CMV é a única que fatia no navegador**, porque o rodapé precisa somar
  TODAS as linhas para a identidade fechar — o relatório vem inteiro de propósito.

- ⚠️ **O total sai em consulta SEPARADA e só na primeira página** (`paginacao.pagina`). Medido
  com 400.000 movimentos no razão: página de 100 sem total **4 ms**, com `count(*) OVER ()`
  **388 ms** — a janela obriga o banco a materializar todas as linhas do filtro para depois
  cortar em 100. Virar a página não muda o total, então a conta roda no `offset = 0` e mais
  nada: 148 ms na primeira, **2 ms** nas seguintes. Quando o cabeçalho não vem, `api.listar`
  devolve `total: null` e `usePaginacao.setTotal` **guarda o que já tinha** — tratar nulo como
  zero apagaria o rodapé na página 2. Quem monta a consulta passa o SQL **sem LIMIT**: o total
  usa o mesmo texto e os mesmos parâmetros, e uma cópia do filtro escrita à mão divergiria no
  primeiro `WHERE` novo. As listas limitadas por natureza (fichas, inventários, usuários)
  continuam com `com_total` e `count(*) OVER ()`.

- 🔑 **"Guardar o que já tinha" pressupõe TER TIDO** (09/09/2026, relatado pelo dono: *"quando
  vou para a segunda ou terceira página adiante, ao entrar no produto e voltar para o grid, a
  parte de paginação some"*). Quem volta de um registro não teve: a tela é montada do ZERO. A
  página vem da URL (`?p=3`) — isso já funcionava —, mas o total não vem de lugar nenhum: a
  primeira busca já sai com `offset = 40`, o cabeçalho não vem por regra, o total fica em 0 e o
  rodapé se esconde inteiro. **E com ele some o caminho de volta para a página 2**: a lista fica
  presa naquela fatia, sem nada dizendo que existem outras.

  🔑 **A correção é `?com_total=1`**: quem não tem o total pede a contagem, mesmo fora da
  primeira página. **Quem sabe que precisa é o CLIENTE** — o servidor não tem como saber se
  aquela tela já viu o número antes —, e o custo só é pago quando falta, nunca a cada clique.

  ⚠️ **No backend o flag é lido por MIDDLEWARE** (`main._marcar_pedido_de_total` → um
  `ContextVar` que `paginacao.pagina` consulta), não por parâmetro de cada rota. São oito
  chamadas de `pagina()` em cinco routers; um parâmetro por endpoint seriam dezesseis lugares
  para acertar, e **a lista NOVA nasceria sem** — com o mesmo defeito e sem nada avisando. É a
  armadilha da lista de campos que já comeu a `marca` e depois o `custo_referencia` na fusão.
  O `ContextVar` é devolvido no `finally`: sem isso uma listagem herdaria o pedido da anterior e
  a contagem cara voltaria a rodar em toda virada de página, sem ninguém ver.

  ⚠️ **No front o pedido sai de `p.parametros`**, que TODA lista espalha na query — uma linha
  conserta as catorze e a lista nova nasce consertada. Repetir a condição em cada tela seria
  repeti-la errado numa delas.

  ⚠️ **Isto não vale para o `fator_compra`.** Mudar o fator de conversão NÃO reescreve custo
  nenhum, e não é defeito: todo custo guardado já é por unidade de estoque (razão, último preço
  do fornecedor e `custo_referencia`), e o fator só converte a QUANTIDADE da próxima nota. Quem
  mexe em custo gravado é a troca de UNIDADE (`troca_de_unidade`), porque aí o denominador muda.

- ⚠️ **Nada de `window.prompt`/`confirm`**: é a caixa do NAVEGADOR — fonte de sistema, botão
  em inglês, sem espaço para explicar o que a ação faz. O que não se desfaz pergunta pelo
  `Confirmacao` de `components/ui.tsx`, e o número que a ação usa fica num campo **na linha**,
  à vista antes do clique. Aplicado em: estornar movimento (razão e ajustes), estornar nota,
  fechar contagem, fechar e reabrir mês, cancelar venda e produzir da agenda.
  ⚠️ **Confirmação só onde mexe no razão ou fecha período.** Lançar a nota NÃO pergunta — a
  tela inteira é a conferência (itens, custos e destinos à vista) e um diálogo no caminho
  comum treina a clicar sem ler. Cancelar linha da agenda também não: é plano, não é razão.
  Cada diálogo diz **o que a ação faz**, não só "tem certeza".

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

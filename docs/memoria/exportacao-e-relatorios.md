# Exportação e relatórios

> Extraído do CLAUDE.md original (seções "O que já existe" e "Armadilhas já pagas").
> Consultar antes de mexer nesta área do sistema.

## O que já existe

- 🔑 **Baixar deixou de ser um clique cego** (`services/exportacao_catalogo.py`,
  `components/exportar.tsx`, 29/08/2026). O botão de `/produtos` despejava os **3.226** do
  cadastro, sempre; o de saldos trazia os 99 locais; o razão MANDAVA `id_produto` e o servidor
  **ignorava** — filtrar um produto na tela e baixar dava a planilha inteira, calada, que é
  exatamente o defeito que aquele endpoint dizia existir para evitar. Agora o botão abre uma
  janela: os filtros pertinentes ÀQUELE processo, todos de escolha múltipla, mais a escolha
  entre **planilha e PDF**.
  🔑 **O PDF não foi nove trabalhos, foi um** — e a razão é que os relatórios já se declaravam
  na mesma forma. `exportacao.pdf_de` tem a MESMA assinatura de `csv_de`
  (`linhas, colunas, titulo, resumo`), então relatório novo nasce com os dois formatos sem que
  ninguém escreva nada a mais, e é impossível a planilha e o PDF discordarem sobre o conteúdo.
  ⚠️ **O motor é `reportlab`** (preso em `requirements.txt`), e a escolha é restrição, não
  gosto: `weasyprint` exige GTK/cairo e **quebraria o build no App Platform**. Gerar no
  navegador criaria a segunda implementação do mesmo relatório.
  ⚠️ **A extensão do caminho É o formato, e por isso a URL não mente**: `/exportar/saldos.csv`
  e `/exportar/saldos.pdf`. Quando o caminho traz extensão é ela que manda — um `?formato=pdf`
  pendurado num `.csv` faria o arquivo baixado discordar do endereço que o gerou.
  ⚠️ **O catálogo dos filtros vem do SERVIDOR** (`GET /exportar/catalogo`), com as opções já
  resolvidas. É a lição das três listas de `TIPOS`: escrita no front, a lista divergiria
  **calada** — a tela ofereceria um filtro que o servidor ignora e o arquivo sairia com mais
  linhas do que se pediu. As opções vêm resolvidas para a janela não precisar de quatro
  requisições a mais (e piscar quatro vezes) antes de deixar escolher.
  ⚠️ **O vocabulário é o de `inventario_selecao`**: filtro opcional, combinando com E, vazio
  querendo dizer "todos", e no SQL `(%(x)s IS NULL OR coluna = ANY(%(x)s))`.
  ⚠️ **Produto NÃO vira lista de caixinhas** — são milhares, e seria a mesma mentira do
  `<select>` paginado. O catálogo marca o filtro com `tipo: "produtos"` e a tela resolve com a
  `BuscaCadastro` da casa, guardando o escolhido como etiqueta.
  ⚠️ **A prévia diz quantas linhas viriam ANTES do botão** (`/exportar/{rel}/previa`), como a
  do inventário — e conta o ANEXO junto, senão ela diria "10" e o contador abriria 443 linhas.
  ⚠️ **Dois relatórios são COMPOSTOS de propósito**: o do contador leva a apuração **e** a
  margem por prato; o da reunião com o fornecedor leva a evolução de preço **e** o peso por
  setor. `csv_de`/`pdf_de` recebem `anexos=` por causa deles. Partir em dois arquivos faria
  quem recebe juntar de novo — e duas suítes cobram os dois quadros no mesmo arquivo.
  ⚠️ O BOM do anexo **sai**: ele só vale no começo do arquivo, e um solto no meio vira
  caractere invisível numa célula do Excel (o `precos.csv` tinha esse desde sempre).
  ⚠️ **`MAXIMO_PDF = 5000`**: o razão de uma base real tem centenas de milhares de movimentos,
  e o PDF disso é um arquivo de milhares de páginas que ninguém abre e que estoura o tempo da
  requisição. Acima do teto a resposta é uma FRASE mandando usar a planilha, que não tem teto —
  e a janela desabilita o botão antes do clique, em vez de deixar a surpresa para depois.
  ⚠️ **`int` é contagem e não leva casa decimal no PDF**: o resumo dizia "Linhas 2,00". O tipo
  já separa os dois na origem — contagem chega de um `len()`, dinheiro chega como `Decimal`.
  ⚠️ E o número sai formatado **diferente** do CSV de propósito: a planilha precisa de vírgula
  decimal SEM separador de milhar (com ponto de milhar o Excel lê como texto e não soma); o PDF
  é para o olho, e "1.284.532,10" se lê enquanto "1284532,1" não.
  ⚠️ **A apuração do CMV passou a sair em centavos**, e é arredondamento de APRESENTAÇÃO: ela
  encadeia custo unitário de 6 casas, e o arquivo do contador dizia "56.138,035", que não é um
  valor em reais. Quem arredonda é a linha do relatório, nunca o motor.
  ⚠️ **Nem todo relatório filtra pelo banco**: a movimentação e os vencimentos são motores cuja
  consulta prova uma identidade (`inicial + entradas − saídas = final`) ou alimenta o alerta da
  tela inicial. Neles o corte é feito sobre as linhas devolvidas — daí o de-para de id para
  nome. Remodelar o SQL deles arriscaria a propriedade que o relatório existe para provar.
  ⚠️ **Toda exportação vai para a auditoria com o FILTRO que a gerou**: sem ele o registro diria
  "fulano exportou o estoque", e a pergunta que se faz depois é sempre *o quê, exatamente*.
  ⚠️ **A folha de contagem existia desde a etapa 4 sem botão em tela nenhuma** — só se chegava a
  ela pela URL, e ela é o caminho previsto para quem conta no papel. Ganhou o botão em
  `/inventario/[id]`, no modo "avulso" da janela (um registro só: pergunta o formato e mais
  nada). Em contagem CEGA aberta o servidor continua tirando as colunas do sistema.

- 🔑 **Todo PDF sai em papel TIMBRADO, e com o carimbo de quem o emitiu** (29/08/2026).
  O PDF sai da tela e circula: vira anexo de e-mail, papel na mesa do contador, foto no grupo.
  Sem o timbre ele não diz de que casa é; sem o rodapé não diz quem o emitiu nem quando — e um
  relatório sem essas duas coisas não se confere contra nada.
  Cabeçalho: logo + nome + CNPJ/IE + endereço + contato (`exportacao_catalogo.papel_timbrado`).
  Rodapé, em três partes: **título** à esquerda (uma página solta na mesa precisa dizer de que
  relatório é), **"emitido por Fulano em dd/mm/aaaa hh:mm"** ao centro, **"Página X de Y"** à
  direita.
  ⚠️ **Monta com o que EXISTE.** A base tem razão social, nome fantasia e UF, e mais nada. Uma
  linha reservada e vazia anuncia o que falta em cada página impressa; montar só o que tem sai
  limpo hoje e completo depois, sem ninguém tocar em nada.
  ⚠️ **A UF só aparece ATRÁS da cidade** — sozinha, virava uma linha de endereço escrita "SC".
  Nesse par a informação é o conjunto, não cada metade.
  ⚠️ **A logo vem do DISCO, por `arquivos.caminho_local`** — o PDF desenha a imagem, não a
  busca por HTTP. Mora naquele módulo pela mesma razão que `remover`: é o único que sabe onde
  os arquivos ficam, e é ele que muda no dia do Spaces. Altura fixa e largura pela PROPORÇÃO:
  logo esticada é pior que logo nenhuma.
  ⚠️ **Logo ausente ou ilegível NÃO derruba o relatório** — no App Platform `api/uploads/` é
  efêmera e some a cada deploy, então "sem logo" é estado normal, não erro.
  ⚠️ **O carimbo é calculado UMA vez, fora do rodapé**: `_CanvasNumerado` redesenha o rodapé de
  cada página no fim, e chamar `now()` ali daria horários diferentes entre a página 1 e a 40 do
  mesmo arquivo.
  ⚠️ **O timbre sai só na PRIMEIRA página** (é um flowable, não um `onPage`): repetido em 16
  páginas viraria ruído, e quem identifica as outras é o rodapé.
  ⚠️ Com o timbre em cima, o subtítulo padrão saiu — ele repetia o nome da casa e a data, e a
  data agora mora no rodapé. Dado repetido em dois lugares envelhece num deles.
  ⚠️ O **CSV não mudou** no timbre: ele já leva a linha "Botané Deli e Café — gerado em…".
  ⚠️ Mas o carimbo é do ARQUIVO, não de cada quadro: os anexos vinham com essa linha repetida
  embaixo de cada título, e a folha de um produto ficava com ela três vezes (`com_carimbo`).

- ⚠️ **Relatório cortado no topo esconde o registro que se procura.** `/cmv/margem` sai ordenado
  por receita e cortado no `limite` (50). Assim que a base ganhou 464 pratos e R$ 187 mil de
  venda real, o prato de R$ 500 de uma suíte saiu do topo — e "não está na lista" leu como
  "margem zero", um bug que não existia. O endpoint ganhou `id_produto`, que responde por UM
  prato sem depender do corte; a suíte pergunta pelo id dela. Vale para todo relatório com
  `LIMIT`: quem quer olhar um item específico precisa de um caminho que não passe pelo ranking.

## Armadilhas já pagas

- ⚠️ **O rodapé do relatório soma as linhas ARREDONDADAS**, de propósito — o total tem de
  fechar com a coluna que a pessoa confere a mão. Em centenas de produtos isso dá centavos de
  diferença na identidade "inicial + entradas − saídas = final", que **não são erro de razão**.
  A folga acompanha o tamanho do relatório (meio centavo por linha), na tela e nos testes: com
  folga fixa, uma base real acusava "a conta não fecha" toda vez, e alarme que sempre toca
  ninguém escuta.

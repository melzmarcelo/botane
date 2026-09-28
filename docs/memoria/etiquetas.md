# Etiquetas

> Etiquetas de validade do que se produz, abre e descongela.
> Leia antes de mexer neste módulo. Estudo em [`docs/etiquetas-estudo.md`](../etiquetas-estudo.md).

## O que já existe

- 🔑 **O módulo inteiro** (28/09/2026, pedido do dono: *"um novo módulo, o de Etiquetas, para
  controlar validade, quantidade e demais coisas úteis, em produtos produzidos e abertos para
  consumo. Algo integrado, que controlamos de forma simples e rápida"* — e, depois do estudo,
  *"pode implementar"*). Migração `100_etiquetas.sql`, `services/etiquetas.py`,
  `routers/etiquetas.py`, telas em `web/app/(app)/etiquetas/`, suíte `smoke_etiquetas` (58).

- 🔑 **A PRODUÇÃO passou a nascer com lote e validade** (`estoque.produzir`). Era o furo que o
  estudo achou: o que a cozinha fazia entrava sem data, e o FEFO e o alerta de vencimento só
  enxergavam o que veio de nota. O lote é `P<id da produção>`; a validade sai da regra de
  PRODUÇÃO padrão do produto, senão do `produtos.validade_dias`.
  ⚠️ **Só com `controla_lote` E com validade conhecida.** Sem `controla_lote`, `lancar` nem mexe
  em lote (regra antiga); sem validade, lote sem data não ajuda o FEFO e mudaria a produção de
  quem nunca cadastrou nada. Quem não tem regra continua produzindo exatamente como antes.
  ⚠️ O lote guarda a validade da conservação PADRÃO. A etiqueta de um pote congelado vence
  depois, mas o lote do estoque continua com a data padrão — a data do lote é a conservadora.

- 🔑 **Validade por EVENTO e CONSERVAÇÃO** (`produto_validades`): produção, abertura,
  descongelamento × refrigerado, congelado, ambiente, em HORAS ou DIAS. Um padrão por evento
  (o servidor garante; sem marcado, a primeira regra vira padrão).
  Ordem de quem responde: data informada > regra > `validade_dias` (só produção) > nada
  (a emissão recusa e diz "informe a validade").
  ⚠️ **Aberto nunca vale mais que o fabricante**: `validade_fabricante` vira teto às 23:59
  daquele dia; embalagem já vencida é recusada.
  ⚠️ **Prazo em dias conta do instante, não do fim do dia**: feito 28/09 13:58 com 3 dias vence
  01/10 13:58, e a etiqueta imprime data E hora. É o conservador, e deixa "vence hoje" coerente
  com o que está impresso.

- 🔑 **A etiqueta é registro** (`etiquetas`): código de 6 sem letras ambíguas (é digitado quando
  o QR não lê), situação ATIVA → USADA / DESCARTADA / SUBSTITUIDA. A situação de exibição
  (`VENCIDA`, `HOJE`, `AMANHA`, `EM_DIA`) é calculada na consulta, nunca gravada.
  - **Da produção** (`id_producao`): produto, lote, local e data vêm dela; sem quantidade, a
    produção é dividida pelas cópias (o porcionamento: 10 em 5 potes = 5 × 2).
  - **Descongelar** (`id_origem` + DESCONGELAMENTO): prazo novo da regra, nunca além do pote
    antigo; a antiga vira SUBSTITUIDA.
  - ⚠️ **Reetiquetar/dividir** (`id_origem` com qualquer outro evento) **NÃO renova a
    validade**: herda evento, data e vencimento. Senão dividir o pote seria o jeito de ganhar
    três dias. Pote vencido não se reetiqueta — o caminho é descartar.

- 🔑 **Descartar é PERDA no razão** (`SAIDA_PERDA`, `origem_tipo = 'ETIQUETA'`, via
  `estoque.lancar` — regra 3). Sai do lote da produção quando ele ainda tem a quantidade; senão
  o FEFO escolhe (lote negativo seria controle mentindo). "Não lançar perda" existe para quando
  ela já foi lançada por outro caminho. **"Usei tudo" não mexe no estoque**: o consumo já entrou
  pela venda ou pela produção que usou o pote.

- 🔑 **Impressão**: PDF no tamanho do rolo, UMA PÁGINA POR ETIQUETA (a térmica com o driver no
  mesmo tamanho imprime página a página); A4 = folha 3×7 de 60×40. `api.abrir` abre o PDF numa
  aba — ⚠️ a aba abre ANTES do `await`, senão o navegador bloqueia como popup. Reimpressão
  conta em `impressoes` (etiqueta reimpressa demais é pote duplicado).
  O QR aponta para `WEB_URL/etiquetas/e/<código>`, que exige login.

- 🔑 **A baixa vale na loja DA ETIQUETA**, não na do seletor: quem lê o QR no celular pode estar
  com outra loja escolhida. Quem não enxerga aquela loja recebe 404.

- Alertas no Início: `etiquetas.vencidas` (crítico) e `etiquetas.hoje` (atenção), levando ao
  painel já filtrado.
- Permissões (100): Administrador/Gerente tudo; Cozinha e Conferente imprimem e descartam;
  Salão só imprime. ⚠️ Concedidas na própria 100 (ver 091): a 002 redefine os papéis de sistema.
- Limpeza: `etiquetas` e `produto_validades` em OPERACAO (apontam para produto e razão);
  `etiqueta_config` em PRESERVADAS (é a impressora da loja).

## ⏳ Decidido sem o dono — validar

As perguntas do estudo ficaram sem resposta e a implementação seguiu com o padrão mais simples:
1. **Impressora/rolo**: 60×40 por padrão, trocável na Configuração (40×40, 50×30, 100×50, A4).
2. **Responsável**: quem está logado; campo livre opcional para o tablet de todos (nome, sem PIN).
   Se o dono quiser PIN por pessoa, é a evolução natural.
3. **Descarte com perda desde o início**, com a opção de não lançar.
4. **Todas as lojas** (modelo por loja; validade por produto vale na rede).
5. Nenhuma carga inicial de validades: a tabela da responsável técnica ainda precisa ser digitada.
6. Sem visualização no navegador (extensão desconectada): telas validadas só por `tsc` e
   compilação — falta o teste visual e o teste com a impressora real.

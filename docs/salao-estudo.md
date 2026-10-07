# Salão — análise do cadastro e proposta de ajuste

> Estudo de 06/10/2026, pedido do dono: *"fazer um protótipo e análise para ajustar o cadastro
> de Salão em reservas"*. Protótipo navegável: [`apresentacao/salao-prototipo.html`](../apresentacao/salao-prototipo.html)
> (arquivo local; nada nele é gravado). A memória do módulo é [`docs/memoria/reservas.md`](memoria/reservas.md).

## 1. Como está hoje

A tela `/reservas/salao` tem quatro números no topo, uma aba por salão e, dentro da aba, uma
tabela de mesas editável na própria linha (nome, lugares, máximo, "junta com", ativa).

Em produção, em 06/10/2026: **um salão ("Externo") com duas mesas de 6 lugares**, sem junta.
O cadastro ainda está no começo — é a hora barata de mexer no desenho dele.

O que a tela faz bem e a proposta **mantém**:

- um salão de cada vez, em abas, com a aba no endereço;
- `lugares` (confortável) e `máximo` (cadeira extra) como dois números;
- "+ várias mesas", que monta o salão de uma vez;
- desligar o salão tira as mesas da disponibilidade sem apagar nada;
- salão com mesa não se exclui; mesa que já recebeu reserva também não.

## 2. O que atrapalha

| # | Problema | Efeito |
|---|---|---|
| 1 | **Cada campo grava ao sair dele.** Não há botão Salvar nem Desfazer. | Um número digitado errado já vale para a disponibilidade no instante em que o cursor sai do campo. Ninguém percebe que gravou. |
| 2 | **A junta é só em PAR.** Cada mesa aponta para uma vizinha (`mesas.junta_com`). | O maior grupo possível é o de duas mesas. Três mesas de 4 em fila não viram uma de 12. E a capacidade da junta é sempre a soma — juntar duas de 4 "dá 8" mesmo quando na prática dá 6. |
| 3 | **Não se vê o salão.** Só uma tabela; `pos_x`/`pos_y` existem no banco e ninguém usa. | Para saber quais mesas encostam é preciso conhecer a casa de cabeça. Quem cadastra a junta erra o par. |
| 4 | **O salão só sabe "ligado/desligado".** | O mezanino que abre de sexta a domingo depende de alguém lembrar de ligar na sexta e desligar na segunda. E não há como ter um salão que a recepção usa mas o site não oferece. |
| 5 | **A mesa não tem característica.** | "Mesa perto da janela", "precisa de cadeirão", "cadeirante" chegam na observação da reserva e a recepção resolve de memória. |
| 6 | **Nada confere o cadastro.** | O alerta "o site aceita mais gente do que cabe" (`maior_grupo` × `teto_online`) existe na resposta da API, mas a tela do salão não mostra. E não há como perguntar "onde um grupo de 7 sentaria?" sem criar uma reserva de teste. |

## 3. A proposta — seis mudanças

1. **Salvar é um botão.** A mesa abre num painel ao lado, com Salvar e Desfazer e o aviso
   "alterações não salvas". Lugares e máximo viram botões de −/+ (não se digita "60" por engano).
2. **A planta do salão.** As mesas desenhadas na posição em que estão, arrastáveis, com tamanho
   e formato do cadastro. A **lista continua** num botão ao lado, para quem prefere tabela e
   para o celular.
3. **Junta vira CONJUNTO.** Duas, três ou quatro mesas, com capacidade própria (sugerida pela
   soma, ajustável). Marca-se na planta e cria. Uma mesa pode estar em mais de um conjunto
   (05+06 e 05+06+07).
4. **O salão diz quando abre.** Dias da semana em que funciona, "aceita reserva pelo site"
   separado de "atende", e um texto opcional para o cliente ("área externa coberta").
5. **Características da mesa.** Uma lista curta e fixa (janela, sofá, acessível, cadeirão,
   tomada, coberta) e o formato (redonda, quadrada, retangular).
6. **Conferir antes de abrir.** O aviso do teto do site na própria tela, e um simulador
   "onde um grupo de N sentaria?" usando a MESMA regra da disponibilidade.

## 4. O que cada mudança custa

| Mudança | Banco | Regra de disponibilidade | Tela | Risco |
|---|---|---|---|---|
| 1. Salvar explícito | nada | nada | média | baixo |
| 2. Planta | nada (`pos_x`/`pos_y` já existem); `formato` é coluna nova | nada | alta (arrastar, toque) | baixo — é só desenho |
| 3. Conjuntos | **tabela nova** (`mesa_conjuntos` + itens) e migração do `junta_com` atual | **muda** — a alocação passa a considerar conjuntos de N mesas | média | **médio** — é a regra que decide se há mesa |
| 4. Salão com dias e site | colunas novas em `saloes` | **muda** — `_mesas_vivas` passa a olhar o dia e a origem do pedido | baixa | médio |
| 5. Características | coluna nova em `mesas` | nada (só informa a recepção) | baixa | baixo |
| 6. Conferência | nada | nada — reaproveita a regra | baixa | baixo |

⚠️ **As mudanças 3 e 4 mexem na regra que responde "tem mesa?".** A suíte
`smoke_reservas_disponibilidade` precisa ganhar os casos novos ANTES de a regra mudar, e a
migração do par atual para conjunto tem de ser idempotente (hoje em produção não há nenhuma
junta gravada, então ela não converte nada — mas tem de estar certa para a base de teste).

## 5. Decisões que são suas

1. **A junta com capacidade própria**: quando o conjunto 05+06 "acomoda 8", ele recebe um grupo
   de 8 mesmo se a soma dos máximos for 10? (A proposta: sim — a casa sabe quantos cabem.)
2. **O cliente escolhe o salão no site?** Hoje não. Com a descrição do salão dá para oferecer
   "Área externa" × "Salão interno" na reserva. É recurso novo, não ajuste — fica fora, a menos
   que você queira.
3. **Dias em que o salão abre**: por dia da semana basta, ou precisa de horário (o mezanino só
   no jantar)? A proposta começa pelo dia.
4. **Lista de características**: as seis do protótipo servem, ou a casa tem outras? Fixa (como
   proposto) ou editável?
5. **A planta é para montar ou também para operar?** No protótipo ela é do CADASTRO. Mostrar na
   agenda quais mesas estão ocupadas às 20h é outro passo, maior.

## 6. Ordem sugerida

- **Primeira entrega (sem mexer na regra):** 1 (salvar explícito), 6 (conferência e aviso do
  teto) e 5 (características). Resolve o que mais incomoda no uso e não tem risco. ✅ **Feita em 06/10/2026** (migração 106).
- **Segunda:** 2 (planta), com a lista mantida. ✅ **Feita em 07/10/2026** (migração 108).
- **Terceira:** 3 (conjuntos) e 4 (dias e site), juntas, com a suíte de disponibilidade
  estendida primeiro.

## 7. O que fica de fora, de propósito

- Planta com paredes, portas e escala real — a grade de 30 em 30 basta para dizer o que encosta
  em quê.
- Ocupação ao vivo na planta (ver item 5 das decisões).
- Mesa que muda de salão arrastando entre abas.

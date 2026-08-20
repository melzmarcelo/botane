# O que pedir ao cliente para ligar as integrações

Documento de trabalho: o que falta para o Omie e o PDV Legal saírem do modo de
demonstração. Atualizado em 19/08/2026.

---

## 1. Omie — o cliente consegue gerar sozinho

**Sim, com o login dele.** Só o **usuário administrador** da conta consegue, e
não há custo nem contratação — a chave já vem com a conta.

### O caminho (dois jeitos, o mesmo resultado)

**Pelo próprio Omie**
1. Entrar no Omie com o usuário administrador
2. Tela **"Meus Aplicativos"** → localizar o cartão do aplicativo
3. Ícone de engrenagem → **"Resumo do App"**
4. Rolar até **"Chave de Integração (API)"**
5. Clicar em **"exibir"** para revelar o `App Secret`

**Pelo portal do desenvolvedor**
1. Acessar <https://developer.omie.com.br/> e entrar com **o mesmo e-mail e senha
   do ERP**
2. Clicar em **"Aplicativos"**
3. Abrir o aplicativo desejado — a `App Key` e a `App Secret` aparecem ali

> ⚠️ Existe um botão **"Gerar nova chave de acesso"** na mesma tela. **Não usar**:
> ele invalida todas as integrações que já usam a chave antiga (contador, outros
> apps). Só serve se a chave vazar.

### O que preciso receber

| Item | Exemplo do formato |
|---|---|
| `app_key` | `1234567890123` (numérico, ~13 dígitos) |
| `app_secret` | `a1b2c3d4e5f6...` (alfanumérico longo) |
| Nome do aplicativo de onde saiu | para sabermos qual chave é qual |

### Três perguntas que valem mais que a chave

Elas definem se vai dar trabalho ou não. Melhor perguntar junto:

1. **As notas de compra são lançadas como "Nota de Entrada" no Omie, ou só
   chega o XML do fornecedor?** São dois lugares diferentes na API; hoje leio o
   primeiro.
1b. **De quando o cliente quer o histórico?** A busca comum vai desde a última
   sincronização; a carga inicial é uma escolha dele (o CMV dos meses passados
   depende dela).
2. **O Omie dele já controla estoque?** Se sim, precisamos decidir quem é o dono
   do saldo — senão a mesma compra baixa dos dois lados.
3. **Ele consegue exportar uma resposta de exemplo** de uma nota pelo portal do
   desenvolvedor (a tela de teste online devolve o JSON)? Com esse arquivo eu
   ajusto o sistema **antes** de a chave chegar, e a virada vira só o cadastro.

### Uma dúvida que só a conta real resolve

⚠️ **Qual data o `dDtInicial` filtra** — emissão ou entrada? Importa porque a
janela da busca é por data: se filtrar pela emissão, uma nota emitida há 90 dias
e lançada no Omie hoje precisa de uma carga com data escolhida para entrar. O
sistema já tem o botão para isso e a conferência que **nomeia** as notas que
faltam, mas vale confirmar o comportamento na primeira semana de uso real.

### O que acontece depois que a chave chegar

- Cadastro na tela **Integrações**, modo "real", botão **"Testar conexão"**.
- Ajuste fino do tradutor de campos, se algum nome vier diferente do previsto:
  **meio dia a um dia**, num arquivo só.
- Nada mais muda: de-para, rateio de frete, conversão de unidade e lançamento no
  estoque já estão prontos e testados.

### Mensagem pronta para o cliente

> Preciso da chave de integração do Omie para o sistema puxar as notas de compra
> automaticamente. Quem consegue gerar é o **usuário administrador** da conta,
> sem custo:
>
> Entre em developer.omie.com.br com o mesmo e-mail e senha do Omie → clique em
> **Aplicativos** → abra o aplicativo → copie a **App Key** e a **App Secret**.
> (Se preferir, dá pelo próprio Omie: Meus Aplicativos → engrenagem → Resumo do
> App → Chave de Integração (API) → exibir.)
>
> ⚠️ Não clique em "Gerar nova chave de acesso" — isso derruba as integrações
> que já existem.
>
> Aproveitando, três dúvidas rápidas:
> 1. As notas de compra são lançadas como **Nota de Entrada** no Omie, ou vocês
>    só recebem o XML do fornecedor?
> 2. Vocês usam o **controle de estoque** do Omie hoje?
> 3. Consegue me mandar o **JSON de exemplo** de uma nota (a tela de teste do
>    portal do desenvolvedor mostra)? Com ele eu adianto metade do trabalho.

---

## 2. PDV Legal — depende do suporte deles

Aqui **o cliente sozinho não resolve**: a credencial existe, mas o catálogo de
endereços da API fica no portal de parceiros, fechado. Sem a documentação não dá
para escrever o código — só adivinhar.

### O que preciso receber

| Item | Observação |
|---|---|
| `username` e `password` | de um usuário de integração, fornecidos pelo responsável da conta |
| `client_id` | é o **código do grupo econômico** |
| `client_secret` | é o **token do grupo econômico** |
| **Documentação dos endpoints** | o item que realmente trava — vem do portal de parceiros |

Detalhe técnico já confirmado: a autenticação é `POST` em
`https://api.tabletcloud.com.br/token`, e o token vale ~6 horas.

### O que preciso saber junto

1. Quais **endpoints de vendas** existem (vendas do dia, itens, cancelamentos).
2. Se dá para puxar o **cadastro de itens do cardápio** — é o que permite ligar
   cada item vendido ao prato com ficha técnica.
3. Se o PDV Legal deles já usa **ficha técnica e estoque** — se sim, vale alinhar
   com o cliente qual dos dois manda, para não haver dois controles.

### Enquanto não vem

As vendas entram por **planilha**, colando o relatório da Retaguarda na tela de
Vendas. O destino é o mesmo que a integração vai preencher: quando a API abrir,
muda a fonte e nada mais.

### E-mail pronto para o suporte do PDV Legal

> Assunto: Acesso à API de integração — [nome do estabelecimento]
>
> Olá,
>
> Sou responsável pela conta do PDV Legal do **[nome do estabelecimento]**
> (CNPJ [xx]). Estamos integrando o PDV a um sistema próprio de controle de
> custo e preciso de dois itens:
>
> 1. **Credenciais de integração**: `username`, `password`, `client_id` (código
>    do grupo econômico) e `client_secret` (token do grupo econômico).
> 2. **Documentação dos endpoints** da API (api.tabletcloud.com.br) — em especial
>    os de **vendas do período** (com itens, valores e cancelamentos) e o de
>    **cadastro de itens do cardápio**.
>
> O uso será **somente de leitura**: puxar as vendas para apurar o custo de
> mercadoria vendida. Não vamos escrever nada no PDV.
>
> Podem me orientar sobre o caminho para liberar esse acesso?
>
> Obrigado,
> [nome] — [telefone] — [e-mail]

---

## 3. Como me enviar as credenciais

Chave de integração é senha. O melhor caminho, em ordem:

1. **O próprio cliente cadastra** na tela Integrações do Botané, com você junto —
   assim ela nunca circula. É o caminho preferido.
2. Se precisar passar por mim: mande `app_key` e `app_secret` **em mensagens
   separadas**, e não por e-mail.
3. Nunca em anexo de planilha nem em grupo de WhatsApp.

No sistema elas ficam **cifradas** e não voltam pela tela — só os últimos
dígitos aparecem, para você reconhecer qual está lá.

---

## 4. Resumo para cobrar

| | Omie | PDV Legal |
|---|---|---|
| Quem resolve | **o cliente**, com login de admin | **o suporte do PDV Legal** |
| Custo | nenhum | nenhum (a conta já dá direito) |
| Prazo esperado | minutos | dias — depende deles responderem |
| Trabalho aqui depois | ajuste fino, ~1 dia | desenvolvimento, 2-3 dias |
| Trava real | nome dos campos da resposta | **falta a documentação** |
| Sem isso, hoje | notas de demonstração | vendas por planilha |

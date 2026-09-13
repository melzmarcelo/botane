import io

# ============================================================ 1. excluir rascunho
p = "app/(app)/fichas/[id]/page.tsx"
s = io.open(p, encoding="utf-8").read()

A = '''  const [confirmandoCusto, setConfirmandoCusto] = useState(false);'''
B = '''  const [confirmandoCusto, setConfirmandoCusto] = useState(false);
  /**
   * 🔑 **Rascunho se EXCLUI** (13/09/2026, pedido do dono). Arquivar existe para
   * não quebrar o passado — ficha publicada apurou custo e o histórico aponta
   * para ela. Rascunho não tem passado nenhum, e uma lista cheia de tentativas
   * arquivadas é ruído que ninguém pode limpar.
   *
   * ⚠️ **O servidor é quem decide**, e faz as duas coisas no mesmo `DELETE`: em
   * rascunho exclui, em homologada arquiva, e recusa quando o dado trava (usada
   * como sub-ficha, produção registrada). A tela só oferece o botão onde ele faz
   * sentido — mas não é ela a guarda.
   */
  const [excluindo, setExcluindo] = useState(false);'''
assert A in s
s = s.replace(A, B, 1)

A = '''  const opcoesSubficha = useMemo('''
B = '''  async function excluirRascunho() {
    setExcluindo(false);
    try {
      const r = await api.delete<{ message: string }>(`/fichas/${id}`);
      aviso.sucesso(r.message);
      router.push("/fichas");
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível excluir");
    }
  }

  const opcoesSubficha = useMemo('''
assert A in s
s = s.replace(A, B, 1)

A = '''          {!nova && podeEditar && ficha && (
            <DuplicarFicha'''
B = '''          {/* ⚠️ Só em RASCUNHO: em ficha publicada o mesmo endpoint arquiva, e
              oferecer "excluir" ali faria a tela prometer o que o servidor não
              faz. */}
          {!nova && podeEditar && ficha?.status === "RASCUNHO" && (
            <button
              type="button"
              className="btn btn-secundario"
              onClick={() => setExcluindo(true)}
            >
              Excluir rascunho
            </button>
          )}
          {!nova && podeEditar && ficha && (
            <DuplicarFicha'''
assert A in s
s = s.replace(A, B, 1)

A = '''      {confirmandoCusto && ('''
B = '''      {excluindo && (
        <Confirmacao
          titulo="Excluir este rascunho?"
          perigo
          rotuloConfirmar="Sim, excluir"
          aoConfirmar={excluirRascunho}
          aoCancelar={() => setExcluindo(false)}
        >
          <p>
            A receita e os destinos dela somem, e <b>não há como desfazer</b>. Rascunho nunca
            foi homologado nem produziu nada, então nenhum custo apurado depende dele.
          </p>
          <p className="mt-2">
            Se este rascunho for usado como <b>sub-ficha</b> em outra receita, o servidor
            recusa e diz onde está o vínculo.
          </p>
        </Confirmacao>
      )}

      {confirmandoCusto && ('''
assert A in s
s = s.replace(A, B, 1)

# A `Confirmacao` ja e importada? (ela e usada na janela do custo)
assert "Confirmacao" in s.split("export default")[0], "Confirmacao nao esta importada"
io.open(p, "w", encoding="utf-8", newline="\n").write(s)
print("ficha: excluir rascunho")

# ============================================================ 2. custo provisorio
p = "app/(app)/produtos/[id]/custo.tsx"
s = io.open(p, encoding="utf-8").read()

A = '''  atual: number | null;
  origem: string;
  origem_texto: string;'''
B = '''  atual: number | null;
  origem: string;
  origem_texto: string;
  /** 🔑 **O que a FICHA prevê, quando ninguém mais sabe** (13/09/2026, pedido do
   *  dono: "caso a ficha não tenha sido produzida, a ficha está sem custo, levar
   *  este custo provisório para a tela do cadastro de produto"). Vem só quando o
   *  apurado é nulo — dois números para a mesma pergunta é pior que um. */
  provisorio: {
    custo: number;
    id_ficha: number;
    versao: number;
    status: string;
    rendimento_qtd: number;
    rendimento_um: string | null;
    custo_total: number;
    itens_sem_custo: number;
    completo: boolean;
  } | null;'''
assert A in s
s = s.replace(A, B, 1)

A = '''            {c.atual === null ? "—" : custo(c.atual)}
          </p>
          <p className="mt-1.5 text-[13px] text-suave">
            {c.atual === null
              ? "Ninguém sabe quanto custa: não há entrada no estoque, preço de fornecedor nem referência."
              : c.origem_texto}
          </p>'''
B = '''            {c.atual !== null
              ? custo(c.atual)
              : c.provisorio
                ? custo(c.provisorio.custo)
                : "—"}
          </p>
          <p className="mt-1.5 text-[13px] text-suave">
            {c.atual !== null
              ? c.origem_texto
              : c.provisorio
                ? `o que a ficha v${c.provisorio.versao} prevê — ainda não foi produzido`
                : "Ninguém sabe quanto custa: não há entrada no estoque, preço de fornecedor nem referência."}
          </p>'''
assert A in s
s = s.replace(A, B, 1)

A = '''      {c.origem === "referencia" && ('''
B = '''      {/* 🔑 **O provisório da ficha, com a etiqueta grudada nele.** Produto
          produzido só ganha custo médio quando uma produção entra no razão; antes
          disso a cascata responde "ninguém sabe" enquanto a receita, ali do lado,
          sabe somar os ingredientes. ⚠️ O aviso é o que impede o número de virar
          apurado aos olhos de quem olha: o custo de verdade é o que SAIU do
          estoque, e ingrediente mais caro no dia faz o lote custar mais. */}
      {c.atual === null && c.provisorio && (
        <div className="mt-3">
          <Aviso tipo={c.provisorio.completo ? "info" : "erro"}>
            Custo <b>provisório</b>, calculado pela ficha v{c.provisorio.versao}
            {c.provisorio.status === "RASCUNHO" && " (em rascunho)"}:{" "}
            {custo(c.provisorio.custo_total)} de ingredientes para{" "}
            {c.provisorio.rendimento_qtd} {c.provisorio.rendimento_um ?? "un"}. O custo de
            verdade nasce na primeira produção — é o que saiu do estoque no dia, não o que a
            receita prevê.
            {!c.provisorio.completo && (
              <span className="mt-1 block">
                ⚠️ {c.provisorio.itens_sem_custo} item(ns) da ficha estão{" "}
                <b>sem preço conhecido</b>, então este número está por baixo.
              </span>
            )}
          </Aviso>
        </div>
      )}

      {c.origem === "referencia" && ('''
assert A in s
s = s.replace(A, B, 1)
io.open(p, "w", encoding="utf-8", newline="\n").write(s)
print("produto: custo provisorio na tela")

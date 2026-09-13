import io

# ============================================================ 1. a ficha
p = "app/(app)/fichas/[id]/page.tsx"
s = io.open(p, encoding="utf-8").read()

A = '''import DuplicarFicha from "./duplicar";'''
B = '''import DuplicarFicha from "./duplicar";
import DestinosDaFicha from "./destinos";'''
assert A in s
s = s.replace(A, B, 1)

# O cartao entra depois do de ingredientes, antes do modo de preparo. Ancora no
# fechamento do cartao de ingredientes (o resumo de custo vem dentro dele).
A = '''      <Cartao
        titulo="Ingredientes"'''
assert A in s
# Acha o proximo `</Cartao>` depois do cartao de ingredientes e insere apos ele.
i = s.find(A)
j = s.find("\n      </Cartao>", i)
assert j > i, "fim do cartao de ingredientes nao encontrado"
fim = j + len("\n      </Cartao>")
NOVO = '''

      {/* 🔑 **Os destinos da receita** (migração 066, pedido do dono). Só em
          ficha que já existe: o destino aponta para uma prateleira e precisa do
          id da ficha para ser gravado — numa ficha nova não há onde pendurá-lo.
          ⚠️ Fica DEPOIS dos ingredientes: o rendimento por destino só faz sentido
          quando já se sabe o que a receita leva. */}
      {!nova && ficha && (
        <DestinosDaFicha
          idFicha={ficha.id}
          rendimentoDaFicha={Number(ficha.rendimento_qtd ?? 1)}
          um={ficha.rendimento_um}
          editavel={editavel}
          aoGravar={() => void carregar()}
        />
      )}'''
s = s[:fim] + NOVO + s[fim:]
io.open(p, "w", encoding="utf-8", newline="\n").write(s)
print("ficha: cartao de destinos")

# ============================================================ 2. o produto
p = "app/(app)/produtos/[id]/page.tsx"
s = io.open(p, encoding="utf-8").read()

# O campo no formulario: ao lado do local padrao.
import re
m = re.search(r'<Campo\s+rotulo="Local padrão"[\s\S]{0,1400}?</Campo>', s)
assert m, "campo do local padrao nao encontrado"
bloco = m.group(0)
NOVO = bloco + '''
          {/* 🔑 **De onde a VENDA baixa** (migração 066, pedido do dono: "podemos
              criar no produto mais de um local, qual seria o local de estoque que
              o PDV consome"). Antes o `id_local_padrao` fazia três papéis — a
              venda, o consumo de insumo e o destino da produção —, e pôr a vitrine
              nele fazia a receita da pizza comer a massa da vitrine.
              ⚠️ Vazio é o normal: sem escolha, a venda segue no local padrão. */}
          <Campo
            rotulo="Local da venda"
            dica="de onde o PDV baixa; vazio = o local padrão"
          >
            <select
              className="campo"
              disabled={!podeEditar}
              aria-label="Local da venda"
              value={f.id_local_venda}
              onChange={(e) => set("id_local_venda", e.target.value)}
            >
              <option value="">o local padrão</option>
              {locais.map((l) => (
                <option key={l.id} value={l.id}>
                  {l.nome}
                </option>
              ))}
            </select>
          </Campo>'''
s = s.replace(bloco, NOVO, 1)

# O estado, o carregamento e o envio.
A = '''    fator_compra: "1", id_local_padrao: "",'''
B = '''    fator_compra: "1", id_local_padrao: "", id_local_venda: "",'''
assert A in s, "estado inicial do produto nao encontrado"
s = s.replace(A, B, 1)

A = '''      id_local_padrao: num(f.id_local_padrao),'''
B = '''      id_local_padrao: num(f.id_local_padrao),
      // Vazio vai como NULO: "não escolhi" é diferente de "o local 0".
      id_local_venda: num(f.id_local_venda),'''
assert A in s, "envio do local padrao nao encontrado"
s = s.replace(A, B, 1)
io.open(p, "w", encoding="utf-8", newline="\n").write(s)
print("produto: campo do local da venda")

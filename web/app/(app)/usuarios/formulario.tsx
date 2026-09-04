"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useAviso } from "@/components/aviso-flutuante";
import { Aviso, Campo, Carregando, Cartao } from "@/components/ui";
import { SENHA_MINIMA, dicaSenha } from "@/lib/senha";
import { useSessao } from "@/lib/sessao";
import BuscaCadastro, { rotuloDe } from "@/components/busca-cadastro";
import { fontePessoas, ItemBusca } from "@/lib/busca-cadastro";

/**
 * O cadastro do usuário — a mesma forma para criar e para corrigir.
 *
 * ⚠️ **Saiu da coluna da direita da lista.** A lista de papéis cresce com o
 * sistema (são seis hoje) e cada um tem descrição de duas linhas; espremida em
 * 380 px, ela empurrava o botão de salvar para fora da tela, e quem cadastrava
 * marcava as caixinhas sem ver o que estava marcando. Mesmo corte de Compras,
 * Vendas e Fornecedores: consultar e cadastrar são telas diferentes.
 *
 * ⚠️ **O papel decide o que a pessoa vê, e quem confere é o SERVIDOR.** A tela
 * escondendo um menu é conforto; a permissão é do backend.
 *
 * 🔑 **Em que loja a pessoa trabalha.** `usuario_papeis.id_unidade` existe desde
 * o primeiro script — nulo quer dizer "todas" —, e esta tela mandava nulo
 * SEMPRE. Com uma loja era a resposta certa; assim que a casa abriu a filial,
 * todo mundo passou a enxergar as duas, e o `ve_unidade` que protege saldo,
 * venda, inventário e remessa virou enfeite. O bloco só aparece com mais de uma
 * loja: numa casa só, perguntar seria atrito sem ganho.
 */

const PESSOAS = fontePessoas();

export type Papel = { id: number; nome: string; descricao: string | null; sistema: boolean };
export type Vinculo = {
  id_papel: number;
  papel: string;
  id_unidade: number | null;
  unidade: string | null;
};

type Form = {
  nome: string;
  email: string;
  telefone: string;
  senha: string;
  papeis: number[];
  /** Nulo = todas as lojas, que é o padrão e o que vale numa casa só. */
  unidades: number[] | null;
  /**
   * Nulo = todos os setores.
   *
   * ⚠️ **Nulo e lista vazia são coisas DIFERENTES aqui**, e o servidor lê os
   * dois: nulo é "não mexi", lista vazia é a escolha explícita de "todos". A
   * tela nunca manda lista vazia — ela manda nulo, que é o mesmo resultado com
   * a intenção declarada.
   */
  setores: number[] | null;
  /**
   * Quem esta pessoa é — o cadastro, separado da credencial.
   *
   * 🔑 Duas portas, nunca as duas: vincular uma que existe, ou criar uma aqui
   * com nome e e-mail. O servidor recusa as duas juntas, porque não haveria como
   * saber qual vale.
   */
  id_pessoa: number | null;
  /** Só para a tela: o nome da pessoa já vinculada, para a busca abrir com ela. */
  pessoa_rotulo: string | null;
  pessoa_nova: { nome: string; email: string } | null;
};

export const VAZIO: Form = {
  nome: "", email: "", telefone: "", senha: "", papeis: [], unidades: null,
  setores: null, id_pessoa: null, pessoa_rotulo: null, pessoa_nova: null,
};

/**
 * Em que lojas estes vínculos põem a pessoa.
 *
 * ⚠️ Nulo = todas. Basta **um** vínculo sem loja para valer em todas: é assim
 * que o servidor lê (`todas = any(id_unidade is None)`), e a tela tem de ler
 * igual, senão as duas discordariam sobre o alcance da mesma pessoa.
 */
export function lojasDosVinculos(vinculos: Vinculo[]): number[] | null {
  if (!vinculos.length || vinculos.some((v) => v.id_unidade === null)) return null;
  return [...new Set(vinculos.map((v) => v.id_unidade as number))];
}

/**
 * O mesmo papel está em lojas diferentes de outros?
 *
 * 🔑 **A tela simplifica, e precisa DIZER quando a simplificação perde algo.**
 * O modelo permite "Cozinha na matriz e Gerente na filial"; este formulário
 * aplica as lojas escolhidas a TODOS os papéis marcados. Salvar por cima de um
 * arranjo misto alargaria o acesso da pessoa sem ninguém pedir — então quando
 * ele existe, o aviso aparece antes do botão.
 */
export function arranjoMisto(vinculos: Vinculo[]): boolean {
  const porPapel = new Map<number, string>();
  for (const v of vinculos) {
    const antes = porPapel.get(v.id_papel) ?? "";
    porPapel.set(v.id_papel, `${antes}|${v.id_unidade ?? "todas"}`);
  }
  return new Set(porPapel.values()).size > 1;
}

export default function FormularioUsuario({
  inicial,
  id,
  aoGravar,
  misto = false,
}: {
  inicial: Form;
  id?: number;
  aoGravar: () => void;
  /** O arranjo atual põe papéis em lojas diferentes — ver `arranjoMisto`. */
  misto?: boolean;
}) {
  const aviso = useAviso();
  const { eu } = useSessao();
  const [form, setForm] = useState<Form>(inicial);
  const [papeis, setPapeis] = useState<Papel[] | null>(null);
  const [salvando, setSalvando] = useState(false);
  // "Vincular uma existente" está escolhido, mesmo antes de a pessoa ser
  // achada — senão o rádio saltaria de volta para "sem vínculo" a cada clique.
  // ⚠️ **Abre JÁ vinculando quando o usuário tem pessoa**, senão editar alguém
  // vinculado mostraria "sem vínculo" e salvar o desvincularia sem ninguém pedir.
  const [vinculando, setVinculando] = useState(!!inicial.id_pessoa);

  // 🔑 **As lojas oferecidas são as de QUEM ESTÁ CADASTRANDO**, e vêm da sessão
  // — não de uma chamada a `/unidades`, que exigiria `admin.unidades` de quem
  // só administra usuários. É também a lista certa: o servidor recusa dar acesso
  // a loja que quem edita não enxerga, e oferecer o que vai levar 403 seria
  // ensinar o erro.
  const lojas = eu?.unidades ?? [];
  const varias = lojas.length > 1;

  // 🔑 **Os setores oferecidos são os de QUEM ESTÁ CADASTRANDO**, pela mesma
  // razão das lojas: o servidor recusa dar um setor que quem edita não tem, e
  // oferecer o que vai levar 403 seria ensinar o erro. Vêm do `/auth/me`, que
  // toda tela já carrega — e com `todos_setores` a lista chega inteira.
  const setores = eu?.setores ?? [];

  // 🔑 **A pessoa se ESCOLHE pela janela de pesquisa**, a mesma do produto
  // (04/09/2026, relato do dono: com combobox fica ruim a visualização). Uma
  // lista de 800 nomes num `<select>` não se percorre.
  // ⚠️ Guardado como {id, rotulo} porque a janela devolve isso, e o rótulo é o
  // que fica na tela depois de escolher.
  const [pessoaEscolhida, setPessoaEscolhida] = useState<{ id: number; rotulo: string } | null>(
    inicial.id_pessoa
      ? { id: inicial.id_pessoa, rotulo: inicial.pessoa_rotulo ?? `pessoa ${inicial.id_pessoa}` }
      : null,
  );

  const carregar = useCallback(async () => {
    try {
      setPapeis(await api.get<Papel[]>("/papeis"));
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Falha ao carregar os papéis");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  async function salvar(e: FormEvent) {
    e.preventDefault();
    setSalvando(true);
    // Lista vazia com "escolher lojas" marcado é um estado sem resposta: a
    // pessoa não trabalharia em lugar nenhum e não veria nada. Melhor recusar
    // aqui, com a frase, do que gravar o vazio.
    if (varias && form.unidades !== null && form.unidades.length === 0) {
      aviso.erro('Escolha ao menos uma loja — ou marque "todas as lojas".');
      setSalvando(false);
      return;
    }
    // Mesma armadilha das lojas, pela outra ponta: "só estes setores" sem
    // marcar nenhum é um estado sem resposta.
    if (form.setores !== null && form.setores.length === 0) {
      aviso.erro('Escolha ao menos um setor — ou marque "todos os setores".');
      setSalvando(false);
      return;
    }
    // ⚠️ **O produto cartesiano papéis × lojas.** `id_unidade` nulo vale em
    // todas — é o caso comum e o de quem tem uma loja só. Escolhendo lojas, cada
    // papel nasce uma vez por loja, que é exatamente como a tabela guarda.
    const escopos: (number | null)[] = form.unidades?.length ? form.unidades : [null];
    const vinculos = form.papeis.flatMap((x) =>
      escopos.map((u) => ({ id_papel: x, id_unidade: u })));
    try {
      if (id) {
        const corpo: Record<string, unknown> = {
          nome: form.nome,
          email: form.email,
          telefone: form.telefone || null,
          papeis: vinculos,
          // ⚠️ Nulo vira lista VAZIA na API: lá, vazio é "todos" e nulo é "não
          // mexi". A tela sempre mexe, então sempre declara.
          setores: form.setores ?? [],
          // ⚠️ `0` DESVINCULA: nulo já quer dizer "não mexi" no PUT, e sem um
          // valor para "tire o vínculo" não haveria como desfazer, só trocar.
          ...(form.pessoa_nova
            ? { pessoa_nova: form.pessoa_nova }
            : { id_pessoa: form.id_pessoa ?? 0 }),
        };
        // ⚠️ Senha em branco MANTÉM a que está: exigir redigitá-la para mudar um
        // papel é o caminho mais curto para alguém escolher uma senha fraca.
        if (form.senha) corpo.senha = form.senha;
        await api.put(`/usuarios/${id}`, corpo);
        aviso.sucesso("Usuário atualizado.");
      } else {
        await api.post("/usuarios", {
          nome: form.nome,
          email: form.email,
          telefone: form.telefone || null,
          senha: form.senha,
          papeis: vinculos,
          setores: form.setores ?? [],
          ...(form.pessoa_nova
            ? { pessoa_nova: form.pessoa_nova }
            : form.id_pessoa
              ? { id_pessoa: form.id_pessoa }
              : {}),
        });
        aviso.sucesso("Usuário criado. A senha precisa ser trocada no primeiro acesso.");
      }
      aoGravar();
    } catch (err) {
      aviso.erro(err instanceof Error ? err.message : "Não foi possível salvar");
    } finally {
      setSalvando(false);
    }
  }

  if (!papeis) return <Carregando />;

  return (
    <form onSubmit={salvar} className="flex flex-col gap-6">
      <Cartao titulo="A pessoa">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <Campo rotulo="Nome">
            <input
              className="campo"
              required
              value={form.nome}
              onChange={(e) => setForm({ ...form, nome: e.target.value })}
            />
          </Campo>
          <Campo rotulo="E-mail" dica="é com ele que a pessoa entra">
            <input
              className="campo"
              type="email"
              required
              value={form.email}
              onChange={(e) => setForm({ ...form, email: e.target.value })}
            />
          </Campo>
          <Campo rotulo="Telefone">
            <input
              className="campo"
              value={form.telefone}
              onChange={(e) => setForm({ ...form, telefone: e.target.value })}
            />
          </Campo>
          <Campo
            rotulo={id ? "Nova senha" : "Senha"}
            dica={
              id
                ? "Em branco mantém. Trocar aqui obriga nova senha no próximo acesso."
                : `${dicaSenha} A pessoa troca no primeiro acesso.`
            }
          >
            <input
              className="campo"
              type="password"
              minLength={SENHA_MINIMA}
              required={!id}
              value={form.senha}
              onChange={(e) => setForm({ ...form, senha: e.target.value })}
            />
          </Campo>
        </div>
      </Cartao>

      <Cartao
        titulo="Papéis"
        descricao="O papel decide o que a pessoa vê. Quem confere é o servidor, não a tela."
      >
        <ul className="grid gap-3 sm:grid-cols-2">
          {papeis.map((p) => (
            <li key={p.id} className="flex items-start gap-2 rounded border border-linha p-3">
              <input
                id={`papel-${p.id}`}
                type="checkbox"
                className="mt-1 h-4 w-4 accent-erva"
                checked={form.papeis.includes(p.id)}
                onChange={(e) =>
                  setForm({
                    ...form,
                    papeis: e.target.checked
                      ? [...form.papeis, p.id]
                      : form.papeis.filter((x) => x !== p.id),
                  })
                }
              />
              <label htmlFor={`papel-${p.id}`} className="cursor-pointer">
                <span className="text-[14.5px] font-semibold">{p.nome}</span>
                {p.descricao && (
                  <span className="block text-[12.5px] leading-snug text-suave">
                    {p.descricao}
                  </span>
                )}
              </label>
            </li>
          ))}
        </ul>
      </Cartao>

      {/* ⚠️ **Só com mais de uma loja.** Numa casa só a resposta é sempre
          "todas", e perguntar seria um campo a mais para responder sempre igual. */}
      {varias && (
        <Cartao
          titulo="Onde trabalha"
          descricao="Limita o que a pessoa enxerga: saldo, venda, contagem, remessa e apuração são de uma loja de cada vez."
        >
          <div className="flex flex-col gap-3">
            <label className="flex items-start gap-2">
              <input
                type="radio"
                className="mt-1 h-4 w-4 accent-erva"
                checked={form.unidades === null}
                onChange={() => setForm({ ...form, unidades: null })}
              />
              <span>
                <span className="text-[14.5px] font-semibold">Todas as lojas</span>
                <span className="block text-[12.5px] leading-snug text-suave">
                  Vale também para as que a casa abrir depois.
                </span>
              </span>
            </label>
            <label className="flex items-start gap-2">
              <input
                type="radio"
                className="mt-1 h-4 w-4 accent-erva"
                checked={form.unidades !== null}
                onChange={() => setForm({ ...form, unidades: [] })}
              />
              <span>
                <span className="text-[14.5px] font-semibold">Só estas lojas</span>
                <span className="block text-[12.5px] leading-snug text-suave">
                  A pessoa não vê nem escolhe as outras no seletor do topo.
                </span>
              </span>
            </label>

            {form.unidades !== null && (
              <ul className="ml-6 grid gap-2 sm:grid-cols-2">
                {lojas.map((u) => (
                  <li key={u.id} className="flex items-center gap-2 rounded border border-linha p-2.5">
                    <input
                      id={`loja-${u.id}`}
                      type="checkbox"
                      className="h-4 w-4 accent-erva"
                      checked={form.unidades?.includes(u.id) ?? false}
                      onChange={(e) =>
                        setForm({
                          ...form,
                          unidades: e.target.checked
                            ? [...(form.unidades ?? []), u.id]
                            : (form.unidades ?? []).filter((x) => x !== u.id),
                        })
                      }
                    />
                    <label htmlFor={`loja-${u.id}`} className="cursor-pointer text-[14.5px]">
                      {u.apelido ?? u.nome}
                      {u.matriz && <span className="text-suave"> · matriz</span>}
                    </label>
                  </li>
                ))}
              </ul>
            )}

            {/* 🔑 A tela aplica as lojas escolhidas a TODOS os papéis marcados.
                Quando o arranjo guardado é mais fino que isso, dizer antes do
                botão — salvar por cima alargaria o acesso sem ninguém pedir. */}
            {misto && (
              <Aviso tipo="info">
                Hoje esta pessoa tem <strong>papéis em lojas diferentes</strong>. Esta tela aplica
                as lojas escolhidas a todos os papéis marcados — salvar aqui vai substituir o
                arranjo atual.
              </Aviso>
            )}
          </div>
        </Cartao>
      )}

      {/* 🔑 **De que parte da casa a pessoa cuida** (pedido do dono, 03/09/2026).
          A tabela `usuario_setores` existe desde o script 004 e nunca foi usada
          por nada — é a mesma história da loja, que também esperou a tela
          aparecer. ⚠️ Hoje isto recorta o PAINEL e a agenda de produção, não o
          sistema inteiro: quem é da Confeitaria abre o Início já vendo o que a
          Confeitaria tem para assar, em vez de percorrer a agenda do Bar junto. */}
      {!!setores.length && (
        <Cartao
          titulo="De que setor cuida"
          descricao="Recorta o painel e a agenda de produção — a pessoa abre o Início já vendo o que é dela."
        >
          <div className="flex flex-col gap-3">
            <label className="flex items-start gap-2">
              <input
                type="radio"
                className="mt-1 h-4 w-4 accent-erva"
                checked={form.setores === null}
                onChange={() => setForm({ ...form, setores: null })}
              />
              <span>
                <span className="text-[14.5px] font-semibold">A casa toda</span>
                <span className="block text-[12.5px] leading-snug text-suave">
                  Vale também para os setores que a casa criar depois.
                </span>
              </span>
            </label>
            <label className="flex items-start gap-2">
              <input
                type="radio"
                className="mt-1 h-4 w-4 accent-erva"
                checked={form.setores !== null}
                onChange={() => setForm({ ...form, setores: [] })}
              />
              <span>
                <span className="text-[14.5px] font-semibold">Só estes setores</span>
                <span className="block text-[12.5px] leading-snug text-suave">
                  O painel mostra só a produção destes — o resto continua acessível pelo menu.
                </span>
              </span>
            </label>

            {form.setores !== null && (
              <ul className="ml-6 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                {setores.map((st) => (
                  <li
                    key={st.id}
                    className="flex items-center gap-2 rounded border border-linha p-2.5"
                  >
                    <input
                      id={`setor-${st.id}`}
                      type="checkbox"
                      className="h-4 w-4 accent-erva"
                      checked={form.setores?.includes(st.id) ?? false}
                      onChange={(e) =>
                        setForm({
                          ...form,
                          setores: e.target.checked
                            ? [...(form.setores ?? []), st.id]
                            : (form.setores ?? []).filter((x) => x !== st.id),
                        })
                      }
                    />
                    <label htmlFor={`setor-${st.id}`} className="cursor-pointer text-[14.5px]">
                      {st.nome}
                    </label>
                  </li>
                ))}
              </ul>
            )}

            {/* ⚠️ **Setor NÃO é permissão, e a tela precisa dizer isso.** Quem
                lesse "só estes setores" como bloqueio deixaria de configurar o
                papel — e a pessoa continuaria abrindo as telas pelo menu. */}
            <Aviso tipo="info">
              Isto <b>não é permissão</b>: diz de que parte da casa a pessoa cuida, para o painel
              dela abrir no que interessa. Quem decide o que ela pode <i>fazer</i> é o papel,
              acima.
            </Aviso>
          </div>
        </Cartao>
      )}

      {/* 🔑 **Quem esta pessoa É** (04/09/2026, pedido do dono). O usuário é a
          credencial; a pessoa é o cadastro. Sem o vínculo, o funcionário que
          compra com desconto e o usuário que abre o sistema são dois registros
          que ninguém liga. */}
      <Cartao
        titulo="Quem é esta pessoa"
        descricao="Liga o login a um cadastro de Pessoas — é ele que carrega a política de cupom."
      >
        <div className="flex flex-col gap-3">
          <label className="flex items-start gap-2">
            <input
              type="radio"
              className="mt-1 h-4 w-4 accent-erva"
              checked={!form.pessoa_nova && !form.id_pessoa && !vinculando}
              onChange={() => {
                setVinculando(false);
                setPessoaEscolhida(null);
                setForm({ ...form, id_pessoa: null, pessoa_nova: null });
              }}
            />
            <span>
              <span className="text-[14.5px] font-semibold">Sem vínculo</span>
              <span className="block text-[12.5px] leading-snug text-suave">
                É o caso comum: quem só usa o sistema não precisa de cadastro de pessoa.
              </span>
            </span>
          </label>

          <label className="flex items-start gap-2">
            <input
              type="radio"
              className="mt-1 h-4 w-4 accent-erva"
              checked={vinculando}
              onChange={() => {
                setVinculando(true);
                setForm({ ...form, pessoa_nova: null });
              }}
            />
            <span className="text-[14.5px] font-semibold">Vincular uma pessoa que já existe</span>
          </label>
          {vinculando && (
            <div className="ml-6 max-w-[420px]">
              <BuscaCadastro
                fonte={PESSOAS}
                selecionado={pessoaEscolhida}
                aoEscolher={(item: ItemBusca | null) => {
                  setPessoaEscolhida(item ? { id: item.id, rotulo: rotuloDe(item) } : null);
                  setForm({ ...form, pessoa_nova: null, id_pessoa: item ? item.id : null });
                }}
              />
            </div>
          )}

          <label className="flex items-start gap-2">
            <input
              type="radio"
              className="mt-1 h-4 w-4 accent-erva"
              checked={!!form.pessoa_nova}
              onChange={() => {
                setVinculando(false);
                setPessoaEscolhida(null);
                setForm({
                  ...form,
                  id_pessoa: null,
                  // ⚠️ Nasce com o nome e o e-mail do usuário: é quase sempre a
                  // mesma pessoa, e redigitá-los seria pedir duas vezes o que
                  // acabou de ser dito.
                  pessoa_nova: { nome: form.nome, email: form.email },
                });
              }}
            />
            <span>
              <span className="text-[14.5px] font-semibold">Criar uma pessoa agora</span>
              <span className="block text-[12.5px] leading-snug text-suave">
                Só nome e e-mail. Ela nasce <b>sem</b> a marca de fornecedor — o resto se
                completa em Pessoas.
              </span>
            </span>
          </label>
          {form.pessoa_nova && (
            <div className="ml-6 grid gap-4 sm:grid-cols-2">
              <Campo rotulo="Nome da pessoa">
                <input
                  className="campo"
                  value={form.pessoa_nova.nome}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      pessoa_nova: { ...form.pessoa_nova!, nome: e.target.value },
                    })}
                />
              </Campo>
              <Campo rotulo="E-mail da pessoa">
                <input
                  className="campo"
                  value={form.pessoa_nova.email}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      pessoa_nova: { ...form.pessoa_nova!, email: e.target.value },
                    })}
                />
              </Campo>
            </div>
          )}
        </div>
      </Cartao>

      <div className="flex flex-wrap gap-2">
        <button className="btn btn-primario" type="submit" disabled={salvando}>
          {salvando ? "Salvando…" : id ? "Salvar" : "Criar usuário"}
        </button>
        <Link href="/usuarios" className="btn btn-secundario">
          Cancelar
        </Link>
      </div>
    </form>
  );
}

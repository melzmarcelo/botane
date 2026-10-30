"use client";

import { useMemo, useState } from "react";
import { useAviso } from "@/components/aviso-flutuante";
import { Confirmacao, Etiqueta } from "@/components/ui";
import { UnidadeMedida, juntarUnidade, previaJuntarUnidade, type PreviaJuntar } from "@/lib/cadastros";

import { plural } from "@/lib/numeros";
/**
 * Unidades repetidas: juntar a que veio do Omie na que a casa usa.
 *
 * 🔑 **Pedido do dono (23/10/2026):** *"no Omie tem vários cadastros de unidades
 * representando a mesma unidade. Exemplo: 1UNID/UN/UN1 é tudo UN … gostaria de um
 * DE/PARA … e considerar somente uma no nosso sistema"*.
 * ⚠️ **O de-para da fila abaixo não alcança esse caso**: ele traduz o texto que NÃO
 * é unidade, e `UN1` e `1UNID` foram cadastradas como unidades. Juntar move produtos,
 * fichas, compras e etiquetas para a que fica, tira a outra do cadastro e a deixa
 * como TRADUÇÃO — a próxima nota ou catálogo do Omie com "UN1" já entra em UN.
 * 🔑 **As sugestões são as que se DENUNCIAM**: mesma grandeza, mesmo fator e mesmo
 * nome ("UNIDADE" quatro vezes). A escolha livre fica embaixo, para o caso que o
 * nome não entrega (PT e PACOTE).
 */
export default function JuntarUnidades({
  ums,
  podeEditar,
  aoJuntar,
}: {
  ums: UnidadeMedida[];
  podeEditar: boolean;
  aoJuntar: () => void;
}) {
  const aviso = useAviso();
  const [absorvida, setAbsorvida] = useState("");
  const [principal, setPrincipal] = useState("");
  const [previa, setPrevia] = useState<PreviaJuntar | null>(null);
  const [ocupado, setOcupado] = useState(false);

  // Mesma grandeza, mesmo fator e mesmo nome: é a mesma unidade com outra sigla.
  const grupos = useMemo(() => {
    const g = new Map<string, UnidadeMedida[]>();
    for (const u of ums) {
      const chave = `${u.grandeza}|${Number(u.fator_base)}|${u.nome.trim().toUpperCase()}`;
      g.set(chave, [...(g.get(chave) ?? []), u]);
    }
    return [...g.values()].filter((x) => x.length > 1);
  }, [ums]);

  const daAbsorvida = ums.find((u) => u.sigla === absorvida);
  // ⚠️ Só oferece como destino o que é a MESMA medida: o servidor recusa o resto, e
  // oferecer KG para juntar UN1 seria convidar o erro.
  const destinos = daAbsorvida
    ? ums.filter((u) => u.sigla !== absorvida && u.ativo && u.grandeza === daAbsorvida.grandeza
        && Number(u.fator_base) === Number(daAbsorvida.fator_base))
    : [];

  async function verPrevia(a: string, p: string) {
    setOcupado(true);
    try {
      setPrevia(await previaJuntarUnidade(a, p));
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível ver o que muda");
    } finally {
      setOcupado(false);
    }
  }

  async function confirmar() {
    if (!previa) return;
    setOcupado(true);
    try {
      const r = await juntarUnidade(previa.absorvida.sigla, previa.principal.sigla);
      aviso.sucesso(r.message);
      setPrevia(null);
      setAbsorvida("");
      setPrincipal("");
      aoJuntar();
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível juntar");
    } finally {
      setOcupado(false);
    }
  }

  return (
    <div className="flex flex-col gap-5">
      <p className="max-w-[75ch] text-[13px] leading-snug prosa text-suave">
        Quando a mesma unidade existe com siglas diferentes (<b>UN</b>, <b>UN1</b>,
        <b> 1UNID</b>), o custo não passa de uma para a outra. Junte a repetida na que a casa
        usa: produtos, fichas e compras passam para ela, e a sigla repetida vira{" "}
        <b>tradução</b> — o que chegar com ela pelo Omie ou pela nota já entra certo.
      </p>

      {!!grupos.length && (
        <div className="flex flex-col gap-2">
          <p className="rotulo">Parecem a mesma unidade</p>
          {grupos.map((g) => (
            <div key={g.map((u) => u.sigla).join("-")}
                 className="flex flex-wrap items-center gap-2 text-[13.5px]">
              <span className="text-suave">{g[0].nome.toLowerCase()}:</span>
              {g.map((u) => <Etiqueta key={u.sigla} cor="neutro">{u.sigla}</Etiqueta>)}
            </div>
          ))}
        </div>
      )}

      {podeEditar && (
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
          <label>
            <span className="rotulo-campo">Juntar</span>
            <select id="juntar-absorvida" className="campo mt-1.5 w-[200px]" value={absorvida}
                    onChange={(e) => { setAbsorvida(e.target.value); setPrincipal(""); }}>
              <option value="">— a repetida —</option>
              {ums.map((u) => (
                <option key={u.sigla} value={u.sigla}>{u.sigla} — {u.nome}</option>
              ))}
            </select>
          </label>
          <label>
            <span className="rotulo-campo">em</span>
            <select id="juntar-principal" className="campo mt-1.5 w-[200px]" value={principal}
                    disabled={!absorvida} onChange={(e) => setPrincipal(e.target.value)}>
              <option value="">— a que fica —</option>
              {destinos.map((u) => (
                <option key={u.sigla} value={u.sigla}>{u.sigla} — {u.nome}</option>
              ))}
            </select>
          </label>
          <button id="juntar-ver" type="button" className="btn btn-secundario"
                  disabled={!absorvida || !principal || ocupado}
                  onClick={() => void verPrevia(absorvida, principal)}>
            Ver o que muda
          </button>
        </div>
      )}

      {previa && (
        <Confirmacao
          titulo={`Juntar ${previa.absorvida.sigla} em ${previa.principal.sigla}?`}
          rotuloConfirmar={previa.pode ? "Juntar" : "Entendi"}
          ocupado={ocupado}
          aoConfirmar={() => (previa.pode ? void confirmar() : setPrevia(null))}
          aoCancelar={() => setPrevia(null)}
        >
          {previa.pode ? (
            <>
              <ul className="ml-4 list-disc text-[14px]">
                <li>{plural(previa.produtos_estoque, "produto", "produtos")} passam a contar em {previa.principal.sigla}</li>
                <li>{plural(previa.produtos_compra, "unidade", "unidades")} de compra</li>
                <li>{plural(previa.fichas, "linha", "linhas")} de ficha técnica</li>
                {!!previa.etiquetas && <li>{plural(previa.etiquetas, "etiqueta", "etiquetas")}</li>}
                {!!previa.apelidos_que_mudam.length && (
                  <li>as traduções {previa.apelidos_que_mudam.join(", ")} passam a valer como{" "}
                    {previa.principal.sigla}</li>
                )}
              </ul>
              <p className="mt-3 text-[13.5px] text-suave">
                <b>{previa.absorvida.sigla}</b> sai do cadastro e vira tradução de{" "}
                <b>{previa.principal.sigla}</b>.
                {!!previa.movimentos_no_razao && (
                  <> Os {plural(previa.movimentos_no_razao, "movimento", "movimentos")} já lançados continuam
                    mostrando {previa.absorvida.sigla} — o razão não se reescreve —, e valem
                    como {previa.principal.sigla}.</>
                )}
              </p>
            </>
          ) : (
            <>
              <p>Não dá para juntar ainda: estes produtos compram nas duas unidades com
                fatores diferentes. Acerte a unidade de compra deles antes.</p>
              <ul className="ml-4 mt-2 list-disc text-[14px]">
                {previa.conflitos.map((c) => (
                  <li key={c.id}>{c.nome} ({c.fator_absorvida} × {c.fator_principal})</li>
                ))}
              </ul>
            </>
          )}
        </Confirmacao>
      )}
    </div>
  );
}

"use client";

/**
 * Exceções por salão ou mesa (decisão do dono): a mais específica vence — mesa → salão → loja.
 * Campo em branco herda. Ex.: a varanda só em vitrine; a mesa 12 aceita pedido até mais tarde.
 */

import { useEffect, useState } from "react";
import { useAviso } from "@/components/aviso-flutuante";
import { Cartao, Vazio } from "@/components/ui";
import { CardapioVivoService, type Excecao, type MesaAcesso } from "@/lib/cardapio-vivo";

const VAZIO = { alvo: "", modo: "", exige: "", de: "", ate: "" };

export default function Excecoes({ podeEditar }: { podeEditar: boolean }) {
  const aviso = useAviso();
  const [lista, setLista] = useState<Excecao[]>([]);
  const [mesas, setMesas] = useState<MesaAcesso[]>([]);
  const [f, setF] = useState(VAZIO);

  const carregar = () => CardapioVivoService.excecoes().then(setLista).catch(() => setLista([]));
  useEffect(() => {
    void carregar();
    // As mesas vêm do acesso das mesas; sem `reservas.configurar`, só se lê o que já existe.
    CardapioVivoService.mesas().then((r) => setMesas(r.mesas.filter((m) => m.ativo))).catch(() => setMesas([]));
  }, []);

  const saloes = [...new Map(mesas.map((m) => [m.id_salao, m.salao])).entries()];

  async function gravar() {
    const [tipo, id] = f.alvo.split(":");
    try {
      const r = await CardapioVivoService.salvarExcecao({
        id_salao: tipo === "s" ? Number(id) : null, id_mesa: tipo === "m" ? Number(id) : null,
        modo: f.modo || null, exige_confirmacao: f.exige === "" ? null : f.exige === "sim",
        pedido_hora_de: f.de || null, pedido_hora_ate: f.ate || null,
      });
      aviso.sucesso(r.message);
      setF(VAZIO);
      void carregar();
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível gravar a exceção.");
    }
  }

  async function excluir(e: Excecao) {
    try {
      const r = await CardapioVivoService.excluirExcecao(e.id);
      aviso.sucesso(r.message);
      void carregar();
    } catch (err) {
      aviso.erro(err instanceof Error ? err.message : "Não foi possível excluir.");
    }
  }

  const herda = (v: unknown) => (v === null || v === undefined ? <span className="text-suave">herda</span> : String(v));
  return (
    <Cartao titulo="Exceções por salão ou mesa"
            descricao="A mais específica vence: mesa, depois salão, depois a loja. Campo em branco herda.">
      {lista.length === 0 ? <Vazio>Nenhuma exceção — todas as mesas seguem a loja.</Vazio> : (
        <div className="overflow-x-auto">
          <table className="tabela">
            <thead><tr><th>Onde</th><th>Modo</th><th>Confirmação</th><th>Horário do pedido</th><th /></tr></thead>
            <tbody>
              {lista.map((e) => (
                <tr key={e.id}>
                  <td>{e.mesa ? `Mesa ${e.mesa} · ${e.salao}` : `Salão ${e.salao}`}</td>
                  <td>{herda(e.modo)}</td>
                  <td>{e.exige_confirmacao === null ? herda(null) : e.exige_confirmacao ? "exige" : "não exige"}</td>
                  <td className="mono">{e.pedido_hora_de ? `${e.pedido_hora_de.slice(0, 5)}–${e.pedido_hora_ate?.slice(0, 5)}` : herda(null)}</td>
                  <td className="text-right">{podeEditar && <button className="link-acao link-acao-erro" onClick={() => void excluir(e)}>tirar</button>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {podeEditar && mesas.length > 0 && (
        <div className="mt-4 flex flex-wrap items-end gap-2 text-[14px]">
          <select className="campo !w-auto" value={f.alvo} onChange={(e) => setF({ ...f, alvo: e.target.value })} aria-label="Onde">
            <option value="">— salão ou mesa —</option>
            <optgroup label="Salões">{saloes.map(([id, nome]) => <option key={`s${id}`} value={`s:${id}`}>{nome}</option>)}</optgroup>
            <optgroup label="Mesas">{mesas.map((m) => <option key={`m${m.id}`} value={`m:${m.id}`}>Mesa {m.nome} · {m.salao}</option>)}</optgroup>
          </select>
          <select className="campo !w-auto" value={f.modo} onChange={(e) => setF({ ...f, modo: e.target.value })} aria-label="Modo">
            <option value="">modo: herda</option><option value="VITRINE">Vitrine</option><option value="PEDIDO">Pedido</option>
          </select>
          <select className="campo !w-auto" value={f.exige} onChange={(e) => setF({ ...f, exige: e.target.value })} aria-label="Confirmação">
            <option value="">confirmação: herda</option><option value="sim">exige</option><option value="nao">não exige</option>
          </select>
          <input type="time" className="campo mono !w-auto" value={f.de} onChange={(e) => setF({ ...f, de: e.target.value })} aria-label="Pedido das" />
          <input type="time" className="campo mono !w-auto" value={f.ate} onChange={(e) => setF({ ...f, ate: e.target.value })} aria-label="Pedido até" />
          <button className="btn btn-secundario" disabled={!f.alvo} onClick={() => void gravar()}>Gravar exceção</button>
        </div>
      )}
    </Cartao>
  );
}

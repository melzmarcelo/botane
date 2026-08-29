"use client";

import { ChangeEvent, FormEvent, useEffect, useRef, useState } from "react";
import { api, ErroApi, urlArquivo } from "@/lib/api";
import { useAviso } from "@/components/aviso-flutuante";
import { useSessao } from "@/lib/sessao";
import { avisarEmpresaMudou } from "@/lib/eventos";
import { Aviso, Campo, Carregando, Cartao } from "@/components/ui";

type Empresa = Record<string, string | null>;

const REGIMES = ["SIMPLES", "PRESUMIDO", "REAL", "MEI"];

export default function PaginaEmpresa() {
  const aviso = useAviso();
  const { pode } = useSessao();
  const podeEditar = pode("admin.empresa");

  const [dados, setDados] = useState<Empresa | null>(null);
  const [erro, setErro] = useState("");
  const [salvando, setSalvando] = useState(false);
  const [enviandoLogo, setEnviandoLogo] = useState(false);
  const seletor = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api
      .get<Empresa>("/empresa")
      .then(setDados)
      .catch((e) => setErro(e.message));
  }, []);

  function set(campo: string, valor: string) {
    setDados((d) => (d ? { ...d, [campo]: valor } : d));
  }

  async function salvar(e: FormEvent) {
    e.preventDefault();
    if (!dados) return;
    setSalvando(true);
    setErro("");
    try {
      const { id, ...resto } = dados as Empresa & { id?: number };
      // string vazia vira null: campo em branco não é "vazio", é sem informação
      const limpo = Object.fromEntries(
        Object.entries(resto).map(([k, v]) => [k, v === "" ? null : v]),
      );
      await api.put("/empresa", limpo);
      avisarEmpresaMudou();
      aviso.sucesso("Dados da empresa salvos.");
    } catch (err) {
      aviso.erro(err instanceof Error ? err.message : "Não foi possível salvar");
    } finally {
      setSalvando(false);
    }
  }

  async function enviarLogo(e: ChangeEvent<HTMLInputElement>) {
    const arquivo = e.target.files?.[0];
    if (!arquivo) return;
    setEnviandoLogo(true);
    setErro("");
    try {
      const corpo = new FormData();
      corpo.append("arquivo", arquivo);
      const r = await api.upload<{ logo_url: string }>("/empresa/logo", corpo);
      setDados((d) => (d ? { ...d, logo_url: r.logo_url } : d));
      avisarEmpresaMudou();
      aviso.sucesso("Logo enviada.");
    } catch (err) {
      aviso.erro(err instanceof ErroApi ? err.message : "Não foi possível enviar a imagem");
    } finally {
      setEnviandoLogo(false);
      if (seletor.current) seletor.current.value = "";
    }
  }

  async function removerLogo() {
    setErro("");
    try {
      await api.delete("/empresa/logo");
      setDados((d) => (d ? { ...d, logo_url: null } : d));
      avisarEmpresaMudou();
      aviso.sucesso("Logo removida.");
    } catch (err) {
      aviso.erro(err instanceof Error ? err.message : "Não foi possível remover");
    }
  }

  if (erro && !dados) return <Aviso tipo="erro">{erro}</Aviso>;
  if (!dados) return <Carregando />;

  const t = (campo: string) => (dados[campo] ?? "") as string;
  const entrada = (campo: string, extra: Record<string, unknown> = {}) => ({
    className: "campo",
    value: t(campo),
    disabled: !podeEditar,
    onChange: (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
      set(campo, e.target.value),
    ...extra,
  });

  return (
    <form onSubmit={salvar} className="flex flex-col gap-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="rotulo">Administração</p>
          <h1 className="mt-1 text-[30px] font-bold tracking-tight">Empresa</h1>
          <p className="mt-1 max-w-[62ch] text-suave">
            Os dados daqui aparecem nos relatórios, nos PDFs e nas integrações. Preencher uma
            vez basta.
          </p>
        </div>
        {podeEditar && (
          <button className="btn btn-primario" type="submit" disabled={salvando}>
            {salvando ? "Salvando…" : "Salvar"}
          </button>
        )}
      </header>

      {!podeEditar && <Aviso tipo="info">Você tem acesso de leitura a esta tela.</Aviso>}
      {erro && <Aviso tipo="erro">{erro}</Aviso>}

      <Cartao titulo="Identificação fiscal">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <Campo rotulo="Razão social" className="lg:col-span-2">
            <input {...entrada("razao_social")} />
          </Campo>
          <Campo rotulo="Nome fantasia">
            <input {...entrada("nome_fantasia")} />
          </Campo>
          <Campo rotulo="CNPJ">
            <input {...entrada("cnpj")} placeholder="00.000.000/0000-00" />
          </Campo>
          <Campo rotulo="Inscrição estadual">
            <input {...entrada("inscricao_estadual")} />
          </Campo>
          <Campo rotulo="Inscrição municipal">
            <input {...entrada("inscricao_municipal")} />
          </Campo>
          <Campo rotulo="CNAE principal">
            <input {...entrada("cnae_principal")} placeholder="5611201" />
          </Campo>
          <Campo rotulo="Regime tributário">
            <select {...entrada("regime_tributario")}>
              <option value="">—</option>
              {REGIMES.map((r) => (
                <option key={r} value={r}>
                  {r}
                </option>
              ))}
            </select>
          </Campo>
          <Campo rotulo="Data de abertura">
            <input {...entrada("data_abertura")} type="date" />
          </Campo>
        </div>
      </Cartao>

      <Cartao titulo="Endereço">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Campo rotulo="CEP">
            <input {...entrada("cep")} placeholder="00000-000" />
          </Campo>
          <Campo rotulo="Logradouro" className="lg:col-span-2">
            <input {...entrada("logradouro")} />
          </Campo>
          <Campo rotulo="Número">
            <input {...entrada("numero")} />
          </Campo>
          <Campo rotulo="Complemento">
            <input {...entrada("complemento")} />
          </Campo>
          <Campo rotulo="Bairro">
            <input {...entrada("bairro")} />
          </Campo>
          <Campo rotulo="Cidade">
            <input {...entrada("cidade")} />
          </Campo>
          <div className="grid grid-cols-2 gap-4">
            <Campo rotulo="UF">
              <input {...entrada("uf")} maxLength={2} />
            </Campo>
            <Campo rotulo="Cód. IBGE">
              <input {...entrada("codigo_ibge")} />
            </Campo>
          </div>
        </div>
      </Cartao>

      <Cartao titulo="Contato">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <Campo rotulo="Telefone">
            <input {...entrada("telefone")} />
          </Campo>
          <Campo rotulo="WhatsApp">
            <input {...entrada("whatsapp")} />
          </Campo>
          <Campo rotulo="E-mail">
            <input {...entrada("email")} type="email" />
          </Campo>
          <Campo rotulo="Site">
            <input {...entrada("site")} />
          </Campo>
          <Campo rotulo="Instagram">
            <input {...entrada("instagram")} placeholder="@botane" />
          </Campo>
        </div>
      </Cartao>

      <Cartao
        titulo="Responsável e contabilidade"
        descricao="Quem responde pela empresa e o escritório que recebe os relatórios."
      >
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <Campo rotulo="Responsável">
            <input {...entrada("responsavel_nome")} />
          </Campo>
          <Campo rotulo="CPF do responsável">
            <input {...entrada("responsavel_cpf")} />
          </Campo>
          <Campo rotulo="E-mail do responsável">
            <input {...entrada("responsavel_email")} type="email" />
          </Campo>
          <Campo rotulo="Escritório contábil">
            <input {...entrada("contador_nome")} />
          </Campo>
          <Campo rotulo="CRC">
            <input {...entrada("contador_crc")} />
          </Campo>
          <Campo rotulo="E-mail do contador">
            <input {...entrada("contador_email")} type="email" />
          </Campo>
          <Campo rotulo="Telefone do contador">
            <input {...entrada("contador_telefone")} />
          </Campo>
        </div>
      </Cartao>

      <Cartao
        titulo="Marca"
        descricao="A logo aparece no topo do sistema e nos relatórios que saem daqui."
      >
        <div className="flex flex-col gap-6 sm:flex-row sm:items-start">
          <div className="flex items-center gap-4">
            <div className="flex h-24 w-24 shrink-0 items-center justify-center overflow-hidden rounded border border-linha bg-papel">
              {t("logo_url") ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={urlArquivo(t("logo_url")) ?? ""}
                  alt="Logo da empresa"
                  className="h-full w-full object-contain p-1.5"
                />
              ) : (
                <span className="rotulo text-center leading-tight">sem
                  <br />
                  logo
                </span>
              )}
            </div>
            {podeEditar && (
              <div className="flex flex-col items-start gap-2">
                <input
                  ref={seletor}
                  type="file"
                  accept="image/png,image/jpeg,image/webp"
                  className="hidden"
                  onChange={enviarLogo}
                />
                <button
                  type="button"
                  className="btn btn-secundario"
                  disabled={enviandoLogo}
                  onClick={() => seletor.current?.click()}
                >
                  {enviandoLogo ? "Enviando…" : t("logo_url") ? "Trocar imagem" : "Enviar imagem"}
                </button>
                {t("logo_url") && (
                  <button type="button" className="link-acao link-acao-erro" onClick={removerLogo}>
                    remover
                  </button>
                )}
                <span className="text-[12.5px] text-suave">PNG, JPG ou WEBP, até 2 MB.</span>
              </div>
            )}
          </div>

          <div className="sm:ml-auto">
            <Campo rotulo="Cor principal" dica="Usada nos títulos dos relatórios.">
              <div className="flex items-center gap-3">
                <input
                  {...entrada("cor_primaria")}
                  type="color"
                  className="h-[38px] w-[58px] cursor-pointer rounded border border-linha2 bg-superficie p-1"
                />
                <span className="mono text-[13px] text-suave">{t("cor_primaria") || "—"}</span>
              </div>
            </Campo>
          </div>
        </div>
      </Cartao>

      {podeEditar && (
        <div className="flex justify-end">
          <button className="btn btn-primario" type="submit" disabled={salvando}>
            {salvando ? "Salvando…" : "Salvar"}
          </button>
        </div>
      )}
    </form>
  );
}

"""O que as suítes de fumaça precisam ter antes de testar o que testam.

Base recém-instalada — ou recém-limpa pelo `limpar_dados.py` — não tem local de
estoque nem setor. Sem local, nenhum movimento entra; sem setor, o relatório por
grupo não tem grupo. Supor que existem fazia a suíte quebrar num ponto que não
tem nada a ver com o que ela prova, e escondia o resultado de tudo o mais.

Cada suíte **garante** o que precisa, do mesmo jeito que já cria os próprios
produtos. Rodar contra uma instalação virgem passou a ser parte do contrato.
"""


def garantir_local(chamar, token) -> dict:
    """O local principal, criando um se não houver nenhum.

    Devolve o registro completo (e não o `{id, message}` do POST): quem chama
    costuma precisar de `principal` e `nome` também.
    """
    st, locais = chamar("GET", "/locais", token=token)
    if locais:
        return next((l for l in locais if l["principal"]), locais[0])
    chamar("POST", "/locais",
           {"nome": "Estoque seco", "tipo": "SECO", "principal": True}, token=token)
    st, locais = chamar("GET", "/locais", token=token)
    return next((l for l in locais if l["principal"]), locais[0])


def garantir_locais(chamar, token, quantos: int = 2) -> list[dict]:
    """Pelo menos `quantos` locais — para transferência, que precisa de dois."""
    st, locais = chamar("GET", "/locais", token=token)
    faltam = quantos - len(locais or [])
    for i in range(faltam):
        chamar("POST", "/locais",
               {"nome": f"Local {len(locais or []) + i + 1}", "tipo": "SECO",
                "principal": not locais and i == 0},
               token=token)
    st, locais = chamar("GET", "/locais", token=token)
    return locais


def garantir_setores(chamar, token, quantos: int = 2) -> list[dict]:
    """Pelo menos `quantos` setores — o CMV por grupo precisa de mais de um
    para provar que cada grupo fica com o seu."""
    st, setores = chamar("GET", "/setores", token=token)
    padrao = ["Cozinha", "Bar", "Confeitaria", "Salão"]
    for i in range(quantos - len(setores or [])):
        chamar("POST", "/setores", {"nome": padrao[i % len(padrao)], "ordem": i}, token=token)
    st, setores = chamar("GET", "/setores", token=token)
    return setores


def garantir_fornecedor(chamar, token, nome: str, cnpj: str) -> int:
    """O fornecedor do cenário, reaproveitando o que já existir com aquele CNPJ.

    A busca é pelo **CNPJ**, não pelo nome: o CNPJ é a chave única no banco, e
    procurar por nome já falhou quando o importador simulado do Omie criou um
    fornecedor com o mesmo documento e outro nome — a suíte não achava, tentava
    criar e levava 409.
    """
    digitos = "".join(c for c in cnpj if c.isdigit())
    st, achados = chamar("GET", f"/fornecedores?incluir_inativos=true&busca={digitos}",
                         token=token)
    existente = next(
        (f for f in (achados or [])
         if "".join(c for c in (f.get("cnpj") or "") if c.isdigit()) == digitos),
        None,
    )
    if existente:
        chamar("PUT", f"/fornecedores/{existente['id']}", {"ativo": True}, token=token)
        return existente["id"]

    st, r = chamar("POST", "/fornecedores", {"nome": nome, "cnpj": cnpj}, token=token)
    if r.get("id"):
        return r["id"]
    # 409: alguém criou entre a busca e o POST, ou o CNPJ está com outro nome.
    st, achados = chamar("GET", f"/fornecedores?incluir_inativos=true&busca={digitos}",
                         token=token)
    return (achados or [{}])[0].get("id")

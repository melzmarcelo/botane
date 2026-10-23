import { redirect } from "next/navigation";

/**
 * O antigo "Períodos de consumo" — desde 22/10/2026, Contas a receber.
 *
 * ⚠️ Fica como redirecionamento: é endereço que estava no menu, em favoritos e no
 * manual, e um 404 ali faria parecer que o recurso sumiu.
 */
export default function AntigosPeriodos() {
  redirect("/receber");
}

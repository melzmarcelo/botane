import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

/**
 * O site do cliente e o sistema no MESMO app, separados pelo domínio.
 *
 * 🔑 **Pedido do dono (15/10/2026):** *"o site de reserva e cardápio ficou parecendo dois
 * sistemas separados… gostaria que esta parte fosse toda no reservas."* O site (`public/portal`)
 * e o feed do Cardápio Vivo (`/c/...`) são servidos por este app; no domínio do cliente
 * (`app.*`; o antigo `reservas.*` só redireciona para ele):
 *   - `/` abre o site;
 *   - `/c/...` (o feed), `/portal/...` e o que o Next serve (`/_next`, ícones) passam;
 *   - qualquer tela INTERNA redireciona ao início — o cliente não tropeça no login da equipe.
 * Em qualquer outro domínio (o do sistema, e em casa) `/portal` também abre o site, para testar.
 * ⚠️ A API não passa por aqui: no App Platform `/api` é outro componente, roteado antes.
 */

/**
 * O domínio do CLIENTE. 🔑 **25/11/2026 — pedido do dono:** o site passa de `reservas.*` para
 * `app.*`, e só o `app` deve aparecer. O `reservas` fica vivo SÓ para redirecionar: QR impresso e
 * link divulgado com o endereço antigo caem no mesmo caminho em `app.*` (308, permanente).
 */
const DO_CLIENTE = /^\/(c\/|portal\/|_next\/|favicon|icone|apple-touch|manifest|robots)/;

export function proxy(request: NextRequest) {
  const { pathname, search } = request.nextUrl;
  const host = (request.headers.get("host") ?? "").toLowerCase();
  const site = new URL("/portal/index.html", request.url);

  if (host.startsWith("reservas.")) {
    // ⚠️ Mesmo caminho e mesma consulta (`?loja=`): o QR antigo abre a MESMA tela no `app`.
    return NextResponse.redirect(`https://app.${host.slice("reservas.".length)}${pathname}${search}`, 308);
  }
  if (host.startsWith("app.")) {
    if (pathname === "/" || pathname === "/portal" || pathname === "/portal/") return NextResponse.rewrite(site);
    if (DO_CLIENTE.test(pathname)) return NextResponse.next();
    // ⚠️ O destino sai do DOMÍNIO pedido, não de `request.url`: atrás do roteador do App
    // Platform (e em casa) a URL interna é outra, e o cliente seria mandado para ela.
    const protocolo = request.headers.get("x-forwarded-proto") ?? "https";
    return NextResponse.redirect(`${protocolo}://${host}/`);
  }
  if (pathname === "/portal" || pathname === "/portal/") return NextResponse.rewrite(site);
  return NextResponse.next();
}

export const config = {
  // Só o que é página: o estático do Next e os arquivos com extensão passam direto.
  matcher: ["/((?!_next/static|_next/image|.*\\.[a-z0-9]+$).*)"],
};

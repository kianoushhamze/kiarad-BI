import { createReadStream, existsSync, statSync } from "node:fs";
import { createServer, request as httpRequest } from "node:http";
import { request as httpsRequest } from "node:https";
import { extname, join, normalize } from "node:path";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL(".", import.meta.url));
const port = Number.parseInt(process.env.KIARAD_SITE_PORT ?? "8081", 10);
const apiOrigin = process.env.KIARAD_API_URL ?? "http://127.0.0.1:8000";

const mimeTypes = new Map([
  [".css", "text/css; charset=utf-8"],
  [".html", "text/html; charset=utf-8"],
  [".ico", "image/x-icon"],
  [".jpeg", "image/jpeg"],
  [".jpg", "image/jpeg"],
  [".js", "text/javascript; charset=utf-8"],
  [".json", "application/json; charset=utf-8"],
  [".png", "image/png"],
  [".svg", "image/svg+xml"],
  [".webp", "image/webp"],
  [".woff", "font/woff"],
  [".woff2", "font/woff2"],
]);

// Minimal proxy for the public, read-only catalog endpoints and the site-customer
// auth endpoints — lets the local preview show the live dashboard connection
// exactly like production.
function proxyPublicApi(request, response) {
  // The dashboard's Next proxy strips the /api prefix; mirror that here so the
  // backend sees its canonical paths.
  const upstreamUrl = request.url.replace(/^\/api\//, "/");
  const headers = { Accept: "application/json", ...request.headers };
  delete headers.host;
  const target = new URL(apiOrigin + upstreamUrl);
  const send = target.protocol === "https:" ? httpsRequest : httpRequest;
  const upstream = send(target, { method: request.method, headers }, (api) => {
    response.writeHead(api.statusCode ?? 502, { "Content-Type": api.headers["content-type"] ?? "application/json; charset=utf-8", "Cache-Control": "no-store" });
    api.pipe(response);
  });
  upstream.on("error", () => {
    if (response.headersSent) { response.destroy(); return; }
    response.writeHead(502, { "Content-Type": "application/json; charset=utf-8" });
    response.end('{"detail":"dashboard api unreachable"}');
  });
  upstream.setTimeout(30_000, () => upstream.destroy(new Error("upstream timeout")));
  request.pipe(upstream);
}

createServer((request, response) => {
  let requestPath;
  try {
    requestPath = decodeURIComponent(new URL(request.url ?? "/", "http://localhost").pathname);
  } catch {
    response.writeHead(400, { "Content-Type": "text/plain; charset=utf-8" });
    response.end("Invalid request path");
    return;
  }
  if (request.method === "GET" && requestPath.startsWith("/api/public/")) {
    proxyPublicApi(request, response);
    return;
  }
  if (request.method === "POST" && requestPath.startsWith("/api/site-auth/")) {
    proxyPublicApi(request, response);
    return;
  }
  if (request.method === "GET" && requestPath.startsWith("/api/site-auth/me")) {
    proxyPublicApi(request, response);
    return;
  }
  if (request.method === "GET" && requestPath.startsWith("/api/site-banners")) {
    proxyPublicApi(request, response);
    return;
  }
  if (request.method === "GET" && requestPath.startsWith("/api/site-orders/mine")) {
    proxyPublicApi(request, response);
    return;
  }
  if (request.method === "POST" && requestPath.startsWith("/api/site-orders")) {
    proxyPublicApi(request, response);
    return;
  }
  if (!["GET", "HEAD"].includes(request.method)) {
    response.writeHead(405, { Allow: "GET, HEAD" });
    response.end();
    return;
  }
  const relativePath = requestPath === "/" ? "index.html" : requestPath.replace(/^\/+/, "");
  const normalizedPath = normalize(relativePath);
  const fullPath = join(root, normalizedPath);

  if (!fullPath.startsWith(root) || !existsSync(fullPath) || !statSync(fullPath).isFile()) {
    response.writeHead(404, { "Content-Type": "text/plain; charset=utf-8" });
    response.end("Not found");
    return;
  }

  response.writeHead(200, {
    "Cache-Control": "no-store",
    "Content-Type": mimeTypes.get(extname(fullPath).toLowerCase()) ?? "application/octet-stream",
  });
  if (request.method === "HEAD") { response.end(); return; }
  createReadStream(fullPath).on("error", () => response.destroy()).pipe(response);
}).listen(port, "0.0.0.0", () => {
  console.log(`Kiarad shop: http://127.0.0.1:${port}`);
});

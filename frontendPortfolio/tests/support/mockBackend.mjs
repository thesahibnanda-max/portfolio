import { readFile } from "node:fs/promises";
import { createServer } from "node:http";

const PORT = Number(process.env.MOCK_BACKEND_PORT ?? "8080");
const FIXTURES = new URL("../fixtures/api/", import.meta.url);
const DETAILS = new Set(["profile", "personality", "professional", "leetcode", "codeforces", "github"]);
const HEADERS = { "content-type": "application/json", "access-control-allow-origin": "*" };

function envelope(status, data) {
  return JSON.stringify({ status, timestamp: new Date().toISOString(), data });
}

const server = createServer(async (request, response) => {
  const path = new URL(request.url ?? "/", "http://localhost").pathname;
  if (path === "/health") {
    response.writeHead(200, HEADERS).end(envelope(200, { status: "UP" }));
    return;
  }
  const name = path.startsWith("/details/") ? path.slice("/details/".length) : "";
  if (request.method === "GET" && DETAILS.has(name)) {
    const data = JSON.parse(await readFile(new URL(`${name}.json`, FIXTURES), "utf8"));
    response.writeHead(200, HEADERS).end(envelope(200, data));
    return;
  }
  response.writeHead(404, HEADERS).end(JSON.stringify({ status: 404, error: "NOT_FOUND", message: path, details: [] }));
});

server.listen(PORT, () => {
  console.log(`Mock backend serving fixtures on http://localhost:${PORT}`);
});

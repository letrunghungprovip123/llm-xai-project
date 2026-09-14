import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const DEFAULT_BASE = "http://127.0.0.1:8000";
const ALLOWED_ROOTS = new Set(["healthz", "readyz", "version", "api"]);

function baseUrl() {
  return (process.env.RESEARCHOPS_FASTAPI_BASE_URL || DEFAULT_BASE).replace(/\/$/, "");
}

async function proxy(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const { path } = await context.params;
  if (!path.length || !ALLOWED_ROOTS.has(path[0])) {
    return NextResponse.json({ error: { code: "BFF_PATH_DENIED", message: "Unsupported ResearchOps path", request_id: "nextjs", details: {} } }, { status: 404 });
  }

  const target = new URL(`${baseUrl()}/${path.map(encodeURIComponent).join("/")}`);
  request.nextUrl.searchParams.forEach((value, key) => target.searchParams.append(key, value));

  const headers = new Headers();
  headers.set("accept", "application/json");
  const contentType = request.headers.get("content-type");
  if (contentType) headers.set("content-type", contentType);
  const idempotency = request.headers.get("idempotency-key");
  if (idempotency) headers.set("idempotency-key", idempotency);
  const incomingRequestId = request.headers.get("x-request-id");
  if (incomingRequestId) headers.set("x-request-id", incomingRequestId);
  const incomingAuth = request.headers.get("authorization");
  const serverToken = process.env.RESEARCHOPS_API_BEARER_TOKEN;
  if (incomingAuth) headers.set("authorization", incomingAuth);
  else if (serverToken) headers.set("authorization", `Bearer ${serverToken}`);

  let body: ArrayBuffer | undefined;
  if (!["GET", "HEAD"].includes(request.method)) body = await request.arrayBuffer();

  try {
    const upstream = await fetch(target, {
      method: request.method,
      headers,
      body,
      cache: "no-store",
      signal: AbortSignal.timeout(Number(process.env.RESEARCHOPS_BFF_TIMEOUT_MS || 30000)),
    });
    const responseHeaders = new Headers();
    responseHeaders.set("content-type", upstream.headers.get("content-type") || "application/json");
    responseHeaders.set("cache-control", "no-store");
    const requestId = upstream.headers.get("x-request-id");
    if (requestId) responseHeaders.set("x-request-id", requestId);
    return new NextResponse(await upstream.arrayBuffer(), { status: upstream.status, headers: responseHeaders });
  } catch (error) {
    return NextResponse.json({
      error: {
        code: "CONTROL_PLANE_UNREACHABLE",
        message: "FastAPI ResearchOps control plane is unreachable",
        request_id: "nextjs-bff",
        details: { type: error instanceof Error ? error.name : "UnknownError" },
      },
    }, { status: 503, headers: { "cache-control": "no-store" } });
  }
}

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const PATCH = proxy;
export const DELETE = proxy;

import { NextRequest, NextResponse } from "next/server";
import {
  ADMIN_SESSION_COOKIE,
  verifyAdminSession,
} from "../../../../lib/admin-session";


const BACKEND_URL =
  process.env.SEATBELT_BACKEND_URL ?? "http://127.0.0.1:8080";

type RouteContext = {
  params: Promise<{ path: string[] }>;
};

async function handle(
  request: NextRequest,
  context: RouteContext
): Promise<NextResponse> {
  const { path = [] } = await context.params;
  const incomingUrl = new URL(request.url);

  const backendBase = BACKEND_URL.replace(/\/$/, "");
  const backendPath = path.map(encodeURIComponent).join("/");
  const targetUrl = `${backendBase}/${backendPath}${incomingUrl.search}`;

  const headers = new Headers();
  const contentType = request.headers.get("content-type");
  const accept = request.headers.get("accept");

  if (contentType) headers.set("content-type", contentType);
  if (accept) headers.set("accept", accept);

  const isAdminRequest =
    request.headers.get("x-seatbelt-admin-request") === "true";

  if (isAdminRequest) {
    const session = request.cookies.get(ADMIN_SESSION_COOKIE)?.value;

    if (!verifyAdminSession(session)) {
      return NextResponse.json(
        { detail: "Admin session required. Sign in and try again." },
        { status: 401 }
      );
    }

    const adminKey = process.env.SEATBELT_ADMIN_API_KEY;

    if (!adminKey) {
      return NextResponse.json(
        { detail: "Admin API key is not configured on the frontend server." },
        { status: 500 }
      );
    }

    headers.set("authorization", `Bearer ${adminKey}`);
  } else {
    const authorization = request.headers.get("authorization");
    if (authorization) headers.set("authorization", authorization);
  }

  const method = request.method.toUpperCase();
  const body =
    method === "GET" || method === "HEAD"
      ? undefined
      : await request.text();

  try {
    const backendResponse = await fetch(targetUrl, {
      method,
      headers,
      body,
      cache: "no-store",
      redirect: "manual",
    });

    const responseHeaders = new Headers();
    const responseType = backendResponse.headers.get("content-type");
    const location = backendResponse.headers.get("location");

    if (responseType) responseHeaders.set("content-type", responseType);
    if (location) responseHeaders.set("location", location);

    const responseBody =
      backendResponse.status === 204 || backendResponse.status === 304
        ? null
        : await backendResponse.text();

    return new NextResponse(responseBody, {
      status: backendResponse.status,
      headers: responseHeaders,
    });
  } catch {
    return NextResponse.json(
      { detail: "Seatbelt backend is unavailable. Check that it is running." },
      { status: 502 }
    );
  }
}

export {
  handle as GET,
  handle as POST,
  handle as PUT,
  handle as PATCH,
  handle as DELETE,
};

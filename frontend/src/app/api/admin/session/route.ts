import { NextRequest, NextResponse } from "next/server";
import {
  ADMIN_SESSION_COOKIE,
  ADMIN_SESSION_SECONDS,
  createAdminSession,
  verifyAdminApiKey,
  verifyAdminSession,
} from "@/lib/admin-session";


function originIsValid(request: NextRequest): boolean {
  return request.headers.get("origin") === request.nextUrl.origin;
}

export async function GET(request: NextRequest) {
  const authenticated = verifyAdminSession(
    request.cookies.get(ADMIN_SESSION_COOKIE)?.value
  );

  return NextResponse.json(
    { authenticated },
    {
      headers: { "Cache-Control": "no-store" },
    }
  );
}

export async function POST(request: NextRequest) {
  if (!originIsValid(request)) {
    return NextResponse.json(
      { detail: "Invalid request origin." },
      { status: 403 }
    );
  }

  let body: { key?: unknown };

  try {
    body = await request.json();
  } catch {
    return NextResponse.json(
      { detail: "Invalid request body." },
      { status: 400 }
    );
  }

  if (
    typeof body.key !== "string" ||
    body.key.length === 0 ||
    body.key.length > 4096
  ) {
    return NextResponse.json(
      { detail: "Enter a valid admin API key." },
      { status: 400 }
    );
  }

  try {
    if (!verifyAdminApiKey(body.key)) {
      return NextResponse.json(
        { detail: "Invalid admin API key." },
        { status: 401 }
      );
    }

    const response = NextResponse.json(
      { authenticated: true },
      { headers: { "Cache-Control": "no-store" } }
    );

    response.cookies.set({
      name: ADMIN_SESSION_COOKIE,
      value: createAdminSession(),
      httpOnly: true,
      secure: process.env.NODE_ENV === "production",
      sameSite: "strict",
      path: "/",
      maxAge: ADMIN_SESSION_SECONDS,
    });

    return response;
  } catch {
    return NextResponse.json(
      { detail: "Admin authentication is not configured on the server." },
      { status: 500 }
    );
  }
}

export async function DELETE(request: NextRequest) {
  if (!originIsValid(request)) {
    return NextResponse.json(
      { detail: "Invalid request origin." },
      { status: 403 }
    );
  }

  const response = NextResponse.json(
    { authenticated: false },
    { headers: { "Cache-Control": "no-store" } }
  );

  response.cookies.set({
    name: ADMIN_SESSION_COOKIE,
    value: "",
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "strict",
    path: "/",
    maxAge: 0,
  });

  return response;
}

import { createHmac, randomBytes, timingSafeEqual } from "node:crypto";

export const ADMIN_SESSION_COOKIE = "seatbelt_admin_session";
export const ADMIN_SESSION_SECONDS = 30 * 60;

function getAdminKey(): string {
  const key = process.env.SEATBELT_ADMIN_API_KEY;
  if (!key) throw new Error("SEATBELT_ADMIN_API_KEY is not configured.");
  return key;
}

function sign(value: string): string {
  return createHmac("sha256", getAdminKey())
    .update(value)
    .digest("base64url");
}

export function verifyAdminApiKey(candidate: string): boolean {
  const expected = Buffer.from(getAdminKey(), "utf8");
  const supplied = Buffer.from(candidate, "utf8");

  return expected.length === supplied.length &&
    timingSafeEqual(expected, supplied);
}

export function createAdminSession(): string {
  const payload = Buffer.from(
    JSON.stringify({
      exp: Math.floor(Date.now() / 1000) + ADMIN_SESSION_SECONDS,
      nonce: randomBytes(16).toString("base64url"),
    }),
    "utf8"
  ).toString("base64url");

  return `${payload}.${sign(payload)}`;
}

export function verifyAdminSession(value?: string): boolean {
  if (!value) return false;

  const parts = value.split(".");
  if (parts.length !== 2) return false;

  const [payload, suppliedSignature] = parts;
  if (!payload || !suppliedSignature) return false;

  let expectedSignature: Buffer;
  let actualSignature: Buffer;

  try {
    expectedSignature = Buffer.from(sign(payload), "base64url");
    actualSignature = Buffer.from(suppliedSignature, "base64url");
  } catch {
    return false;
  }

  if (
    expectedSignature.length !== actualSignature.length ||
    !timingSafeEqual(expectedSignature, actualSignature)
  ) {
    return false;
  }

  try {
    const decoded = JSON.parse(
      Buffer.from(payload, "base64url").toString("utf8")
    ) as { exp?: unknown; nonce?: unknown };

    return (
      typeof decoded.exp === "number" &&
      decoded.exp > Math.floor(Date.now() / 1000) &&
      typeof decoded.nonce === "string" &&
      decoded.nonce.length >= 16
    );
  } catch {
    return false;
  }
}

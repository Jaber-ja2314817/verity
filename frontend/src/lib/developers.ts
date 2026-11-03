/** Example requests shown on the /developers page. Kept here so they can be tested. */

export function checkExample(origin: string, text: string, key = "vrt_YOUR_KEY"): string {
  const body = JSON.stringify({ text, mode: "auto" });
  return [
    `curl -X POST "${origin}/v1/checks?wait=true" \\`,
    `  -H "Authorization: Bearer ${key}" \\`,
    `  -H "Content-Type: application/json" \\`,
    `  -d '${body.replace(/'/g, "'\\''")}'`,
  ].join("\n");
}

export function usageExample(origin: string, key = "vrt_YOUR_KEY"): string {
  return `curl ${origin}/v1/usage \\\n  -H "Authorization: Bearer ${key}"`;
}

/** Human text for the admin page's error messages. */
export function adminErrorMessage(status: number, fallback: string): string {
  if (status === 401) return "Wrong admin secret.";
  if (status === 404) return "Key management is turned off on this server (ADMIN_SECRET is not set).";
  if (status === 429) return "Too many attempts. Wait a few minutes and try again.";
  return fallback;
}

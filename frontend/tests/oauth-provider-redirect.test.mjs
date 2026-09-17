import assert from "node:assert/strict";
import test from "node:test";
import { providerCallbackUrl } from "../src/features/auth/oauth-callback/providerRedirect.ts";

for (const path of ["/auth/google/callback", "/oauth/github/callback"]) {
  test(`${path}: preserves encoded code/state and ignores API prefix`, () => {
    const query = "?code=a%2Fb%2Bc&state=one%2Btwo&scope=openid+email";
    assert.equal(
      providerCallbackUrl(`https://frontend.example${path}${query}`, "https://backend.example/api"),
      `https://backend.example${path}${query}`,
    );
  });
  test(`${path}: forwards cancellation to the configured backend`, () => {
    assert.equal(
      providerCallbackUrl(`https://frontend.example${path}?error=access_denied&redirect_uri=https://untrusted.example`, "https://backend.example/api/"),
      `https://backend.example${path}?error=access_denied&redirect_uri=https://untrusted.example`,
    );
  });
}
test("rejects unknown paths and a redirect loop", () => {
  assert.throws(() => providerCallbackUrl("https://frontend.example/elsewhere", "https://backend.example/api"));
  assert.throws(() => providerCallbackUrl("https://frontend.example/auth/google/callback", "/api"));
});

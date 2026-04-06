# GaleFling OAuth Relay — Context for Claude CLI

## Summary

Meta's Threads use case settings panel now enforces HTTPS on all redirect callback URLs,
including localhost. The `http://localhost` exemption that the plan assumed no longer
works, and neither does `http://127.0.0.1`. This means the localhost HTTP redirect
strategy described in `docs/plans/META_REFACTORING.md` cannot be used as written.

The fix is an HTTPS relay endpoint added to the **existing** log-upload Lambda and API
Gateway stack (`infrastructure/galefling-log-upload.yaml` /
`infrastructure/lambda_function.py`). A new `GET /oauth/callback` route is added to the
existing HTTP API; the existing Lambda function gains a new handler branch for that
route. No new stack, no new function, no new domain — the relay lives at
`https://galefling.jasmer.tools/oauth/callback`.

The relay accepts the Meta OAuth callback, extracts `code` and `state`, decodes the
GaleFling listening port from `state`, and issues a 302 redirect to
`http://localhost:{port}/oauth/callback`. Meta's validator sees HTTPS; GaleFling's
temporary local HTTP server still receives the code unchanged.

---

## Current phase

**Phase 3 — OAuth connect flows** (per META_REFACTORING.md).

Phases 1 and 2 are complete. The three connect flows (Threads, Instagram, Facebook) are
being built now. The relay must be deployed and registered with Meta before any of these
flows can be tested end-to-end.

---

## What needs to change

### 1. `infrastructure/galefling-log-upload.yaml` — minimal additions

Three changes only:

**a) Add `GET /oauth/callback` route** pointing at the existing `HttpApiIntegration`:

```yaml
OAuthCallbackRoute:
  Type: AWS::ApiGatewayV2::Route
  Properties:
    ApiId: !Ref HttpApi
    RouteKey: GET /oauth/callback
    Target: !Sub integrations/${HttpApiIntegration}
```

**b) Extend `CorsConfiguration` on the `HttpApi` resource** to allow GET (currently
only POST and OPTIONS are listed):

```yaml
CorsConfiguration:
  AllowOrigins:
    - '*'
  AllowMethods:
    - GET
    - POST
    - OPTIONS
  AllowHeaders:
    - Content-Type
```

**c) Add the relay URL to the `Outputs` section:**

```yaml
OAuthRelayCallbackUrl:
  Description: OAuth relay callback URL to register in Meta app dashboards
  Value: !Sub https://${DomainName}/oauth/callback
```

No new Lambda permission resource is needed — the existing `LambdaApiPermission` uses a
wildcard `SourceArn` (`${HttpApi}/*`) that already covers any route on this API.

### 2. `infrastructure/lambda_function.py` — new handler branch

Add a dispatch check at the top of `lambda_handler` before the existing log-upload
logic:

```python
raw_path = event.get('rawPath', '')

if raw_path == '/oauth/callback':
    return _handle_oauth_callback(event)
```

New function to add (uses only stdlib — no new dependencies):

```python
def _handle_oauth_callback(event: dict) -> dict:
    """Relay Meta OAuth callback to GaleFling's local HTTP server.

    Meta redirects the browser here after the user authorises the app.
    We decode the port from the state param and issue a 302 to localhost
    so GaleFling's temporary callback server receives the auth code.
    """
    import base64

    params = event.get('queryStringParameters') or {}

    code = params.get('code', '')
    state_raw = params.get('state', '')
    error = params.get('error', '')
    error_description = params.get('error_description', '')

    port = 8765  # fallback if state cannot be decoded
    try:
        decoded = json.loads(base64.urlsafe_b64decode(state_raw.encode()).decode())
        port = int(decoded.get('port', 8765))
    except Exception:
        pass

    if error:
        local_url = (
            f'http://localhost:{port}/oauth/callback'
            f'?error={error}&error_description={error_description}&state={state_raw}'
        )
    else:
        local_url = (
            f'http://localhost:{port}/oauth/callback'
            f'?code={code}&state={state_raw}'
        )

    return {
        'statusCode': 302,
        'headers': {'Location': local_url},
        'body': '',
    }
```

Note: `base64` is imported inside the function to avoid touching the existing
module-level imports. `json` is already imported at module level.

### 3. Port encoding in the `state` param

The plan originally communicated the active port via the redirect URI itself (registering
multiple `http://localhost:{port}/oauth/callback` URIs). With the relay, only one fixed
HTTPS URL is registered. The port must be carried out-of-band.

**Use the OAuth `state` param.** GaleFling already generates a `state` value for CSRF
protection. Encode the port into it:

```python
import json
import secrets
import base64

def make_state(port: int) -> str:
    payload = {'csrf': secrets.token_hex(16), 'port': port}
    return base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()

def parse_state(state: str) -> dict:
    return json.loads(base64.urlsafe_b64decode(state.encode()).decode())
```

The relay Lambda decodes the port from `state` and issues the redirect. The full `state`
value is forwarded unchanged so GaleFling can still verify the CSRF token on receipt.

### 4. Redirect URI registered with Meta

Register exactly **one** redirect URI per app (same URL for all three apps):

```
https://galefling.jasmer.tools/oauth/callback
```

Remove the six `http://localhost:{port}/oauth/callback` entries that the plan originally
specified. The port range approach is no longer needed for URI registration.

### 5. GaleFling app setting — `oauth_redirect_uri`

GaleFling needs to know the relay URL at runtime in order to construct the `redirect_uri`
parameter it passes to Meta's authorization endpoint and in the token exchange call
(Meta requires the value to match exactly in both). Expose it as a user-facing setting
and support it in the credential JSON import.

Add it as a field under `meta` in the import schema:

```json
{
  "version": 1,
  "meta": {
    "oauth_redirect_uri": "https://galefling.jasmer.tools/oauth/callback",
    "threads": { "app_id": "...", "app_secret": "..." },
    "instagram": { "app_id": "...", "app_secret": "..." },
    "facebook": { "app_id": "...", "app_secret": "..." }
  }
}
```

All three Meta platforms share the same relay URL. The setting should be visible and
editable in the advanced settings UI alongside the other Meta credentials so it can be
updated without a full re-import if the domain ever changes.

### 6. OAuth connect flow changes (Phase 3)

The flow described in META_REFACTORING.md Phase 3 remains structurally the same, with
these adjustments:

**Old step 3:** Construct redirect URI from dynamic port
→ **New step 3:** Use fixed relay URL from the `oauth_redirect_uri` setting as
  `redirect_uri`; encode the active port into `state` using `make_state(port)` above

**Old step 5:** Meta redirects browser to `http://localhost:{port}/oauth/callback`
→ **New step 5:** Meta redirects browser to `https://galefling.jasmer.tools/oauth/callback`;
  relay decodes port from `state` and issues 302 to `http://localhost:{port}/oauth/callback`;
  browser follows redirect to GaleFling's local server

All other steps (find free port, start local server, catch callback, exchange code,
store token, shut down server) are unchanged.

### 7. Token exchange call

When exchanging the auth code for a token, Meta requires the `redirect_uri` in the POST
body to exactly match what was used in the authorization request. Pass the relay URL
(`oauth_redirect_uri` setting value), not a localhost URL.

### 8. Environment variables / config

The env vars described in META_REFACTORING.md are no longer needed in their original
form. Replace:

```env
# No longer needed for URI construction (port range kept internally for find_free_port() only):
# META_OAUTH_REDIRECT_BASE
# META_OAUTH_PORT_RANGE_START
# META_OAUTH_PORT_RANGE_END

# New — also importable via credential JSON:
META_OAUTH_REDIRECT_URI=https://galefling.jasmer.tools/oauth/callback
```

---

## Required META_REFACTORING.md updates

The following sections need updating to reflect the relay approach. Phases 1 and 2 are
complete and must not be modified.

### "OAuth redirect URIs and localhost callback handling" section

- Replace the strategy description: the relay HTTPS URL is registered with Meta, not
  localhost URLs; the relay is an additional route on the existing
  `galefling-log-upload` stack at `galefling.jasmer.tools`
- Remove the six `http://localhost:{port}/oauth/callback` entries; replace with the
  single relay URL `https://galefling.jasmer.tools/oauth/callback`
- Update the port handling subsection: `find_free_port()` is still used, but the port
  is now encoded into `state` via `make_state(port)`, not embedded in the redirect URI
- Update the user experience subsection: the relay 302 is transparent; experience is
  otherwise unchanged

### "Setting up the three Meta apps" section (Apps 1, 2, 3)

- Steps referring to "Add OAuth redirect URIs" now mean registering
  `https://galefling.jasmer.tools/oauth/callback` — the same URL for all three apps
- Add a note that all three apps share the same relay redirect URI

### "Credential JSON import format" section

- Add `"oauth_redirect_uri"` field under `"meta"` in the JSON schema (see section 5
  above for the updated schema)
- Update the credentials table: source for `oauth_redirect_uri` is the fixed value
  `https://galefling.jasmer.tools/oauth/callback`

### "Config/environment variables" section

- Remove `META_OAUTH_REDIRECT_BASE`
- Remove `META_OAUTH_PORT_RANGE_START` / `META_OAUTH_PORT_RANGE_END` or note they are
  internal-only and no longer used for URI construction
- Add `META_OAUTH_REDIRECT_URI`

### "Implementation phases" section — Phase 3 only

Add relay deployment as prerequisite steps at the start of Phase 3:
- Add `GET /oauth/callback` route and CORS GET method to `galefling-log-upload.yaml`
- Add `_handle_oauth_callback` branch to `lambda_function.py`
- Redeploy the existing log-upload stack and Lambda function code
- Register `https://galefling.jasmer.tools/oauth/callback` in all three Meta app
  dashboards (replacing localhost entries)
- Add `oauth_redirect_uri` to credential JSON import file and re-import
- Add `oauth_redirect_uri` as an editable field in the advanced settings UI
- Implement `make_state(port)` / `parse_state(state)` helpers in GaleFling
- Update connect flows to encode port into `state` and use relay URL as `redirect_uri`
- Update token exchange calls to pass relay URL as `redirect_uri`

### "Things not to assume" section

Add:
- Do not assume `http://localhost` redirect URIs are accepted by Meta's app dashboard
  validator — they are not; use `https://galefling.jasmer.tools/oauth/callback`
- Do not construct `redirect_uri` dynamically from the active port; the relay URL is
  fixed and must match the registered URI exactly in both the authorization request and
  the token exchange call
- Do not create a new Lambda function or CloudFormation stack for the OAuth relay; it is
  an additional route on the existing `galefling-log-upload` stack

---

## Deployment checklist (Phase 3 prerequisites)

- [ ] Add `OAuthCallbackRoute` to `infrastructure/galefling-log-upload.yaml`
- [ ] Add `GET` to `CorsConfiguration.AllowMethods` in `galefling-log-upload.yaml`
- [ ] Add `OAuthRelayCallbackUrl` output to `galefling-log-upload.yaml`
- [ ] Add `_handle_oauth_callback` function to `infrastructure/lambda_function.py`
- [ ] Add `rawPath` dispatch check to `lambda_handler` in `lambda_function.py`
- [ ] Deploy CFN stack update (`aws cloudformation deploy ...`)
- [ ] Deploy updated Lambda code (`aws lambda update-function-code ...`)
- [ ] Register `https://galefling.jasmer.tools/oauth/callback` in Threads app dashboard
- [ ] Register `https://galefling.jasmer.tools/oauth/callback` in Instagram app dashboard
- [ ] Register `https://galefling.jasmer.tools/oauth/callback` in Facebook app dashboard
- [ ] Add `oauth_redirect_uri` to credential JSON import file and re-import into GaleFling
- [ ] Expose `oauth_redirect_uri` as an editable field in advanced settings UI
- [ ] Implement `make_state(port)` / `parse_state(state)` helpers
- [ ] Update OAuth connect flows to encode port into `state` and use relay URL as `redirect_uri`
- [ ] Update token exchange calls to pass relay URL as `redirect_uri`
- [ ] Test end-to-end OAuth flow for each of the three platforms

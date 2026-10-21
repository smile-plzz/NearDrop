# Architecture and threat model

NearDrop is a local Python application with a static browser client. It listens on TCP 47821 and opens an owner dashboard on the loopback interface. There are no production external services, paid APIs, accounts, or environment secrets.

## Data flow

1. Launcher opens a high-entropy, one-use bootstrap capability in a URL fragment on loopback.
2. The browser exchanges it for an HttpOnly, SameSite=Strict owner session cookie. A remote client cannot bootstrap the owner session.
3. Owner generates a one-use 192-bit invitation. QR rendering happens locally through Segno. The invitation remains in the URL fragment until the browser posts it, preventing HTTP URL/log/referrer leakage.
4. Phone exchanges the invitation for a device session. All authenticated devices share the completed file and note board.
5. Upload start validates size, sanitizes filename, reserves capacity, and allocates a random file ID. Upload chunks append only at the expected offset and only for the authenticated owner of that upload.
6. Finish verifies length, hashes bytes, and atomically renames the partial file into Received. SQLite marks it completed. Downloads are authenticated and forced as attachments, never executed inline.
7. Notes render through textContent. Links only become clickable for HTTP/HTTPS URLs.

## Defensive measures

- Exact Host allowlist rejects DNS rebinding hosts.
- Mutations require a non-simple custom header and reject foreign Origin values; no CORS grants.
- Authenticated static same-origin application, restrictive CSP, no framing, no referrers, no sniffing.
- Pairing attempt rate limits, 16-session cap, invitation expiry, 24-hour sessions, restart revocation.
- Bounded request bodies, 1 MiB upload chunks, 30-second socket timeout, 64 unfinished-upload cap, free-space checks.
- Filename normalization covers path separators, control characters, Windows device names and duplicate names.
- Filesystem operations use generated IDs and normalized names, never arbitrary client paths.
- Errors avoid tracebacks and system details; request logging is suppressed to avoid leaking names and tokens.

## Deliberate boundaries

This is a trusted-LAN utility, not an internet service. HTTP exposes traffic to local observers; capability tokens are not encryption. The Python threaded server is not designed to resist hostile-network denial of service. All paired users are trusted room participants. Do not forward the port or deploy this process publicly.

A global reentrant lock serializes mutation operations, including disk append/finalization and SQLite writes. Downloads stream outside that lock. Finalizing very large files can delay management requests. An OS-held lock prevents concurrent app instances from sharing the same data folder. In-memory sessions are intentionally not persisted. Completed content is persisted without a retention timer; owner deletion is explicit.

Crash between rename and SQLite completion can leave an unlisted file in Received. This file remains recoverable from the folder, but is not automatically listed. Partial records and chunks are cleared after restart. Directory permission protections rely on the user's operating-system profile.

## Release format

Windows x64 portable ZIP, bundled official embeddable Python runtime, application, license notices, launcher, tests, and documentation. No administrator installation, registry modification, scheduled task, startup entry, or automatic firewall change. Windows Firewall access is granted interactively by the user if needed.

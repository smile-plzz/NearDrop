# Validation — NearDrop 1.0.0

Prepared 21 October 2026.

## Executed successfully

Seven backend integration tests, each using a live HTTP server and disposable storage:

1. Phone pairing, one-use invitations, authenticated QR rendering, owner-only operations, unauthenticated access denial.
2. Bidirectional binary delivery, exact byte comparisons, HTTP Range downloads, SHA-256 correctness.
3. Partial upload resumption, wrong offsets, incomplete finalization rejection, wrong-owner rejection, idempotent finish.
4. Host and Origin validation, CSRF custom-header enforcement, traversal rejection, Windows reserved filename normalization.
5. Note persistence/rendering input, owner-only deletion, device revocation.
6. Zero-byte files, duplicate names without overwrite, size bounds, cancellation cleanup, file deletion.
7. Completed file/note persistence across State recreation, invitation and session expiration.

Browser end-to-end suite executed with headless Chromium 134 and isolated laptop and mobile browser contexts:

- Owner bootstrap and QR link generation.
- Phone pairing and dashboard rendering.
- 2.5 MB binary file upload and multi-file queue.
- Forced interruption at the second chunk, followed by automatic resume.
- Byte-for-byte verification of downloaded content.
- Laptop upload → phone browser download.
- Shared notes and safe link rendering.
- HTML-like note text is displayed literally, without creating executable markup.
- File search, phone viewport without horizontal overflow, device revocation.
- No JavaScript page errors.

Desktop (1440 px) and phone (390 px) screenshots were visually inspected. Test screenshots are internal QA evidence, not part of the distributed application.

Native launcher cross-compiled for Windows x86-64 using Zig 0.13, with embedded icon and version information. Official CPython 3.14.7 Windows x64 embeddable ZIP downloaded and ZIP integrity checked. Release ZIP checked for expected files and archive integrity; SHA-256 manifest included.

## Not verified here

- Execution of the Windows launcher and bundled runtime on an actual Windows 10/11 computer.
- Real Windows Defender/SmartScreen and private-network firewall prompts; the launcher is unsigned.
- Safari on a physical iPhone, camera QR scanning, iOS file-picker conversion, screen locking, and background suspension behavior.
- Transfers across actual Wi-Fi routers, guest-network isolation, VPNs, or multiple network adapters.
- Multi-gigabyte stress transfers, low-memory devices, power-loss recovery, or hostile-network penetration testing.
- Physical Windows user interaction and iPhone acceptance testing remain separate from CI. The repository workflow runs the integration suite and extracted portable-runtime smoke test on a Windows runner before publishing; the Actions run is authoritative for its current result.

Browser mobile emulation is not a substitute for physical iPhone testing. The executable is packaged for testing, not claimed hardware-certified.

## First-run acceptance

1. Extract the ZIP and run NearDrop.exe on Windows.
2. Allow its runtime on the private home network if Windows prompts.
3. Pair an iPhone via the laptop QR code.
4. Send a small document and a large video in both directions; compare file size and open the result.
5. Interrupt Wi-Fi during an upload, reconnect, and use Retry / resume if needed.
6. Share a link, copy it on the other device, disconnect the phone, and confirm access is removed.
7. Stop and restart NearDrop. Confirm completed files remain and re-pair the phone.

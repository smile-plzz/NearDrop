# NearDrop 1.0.0

Move original files, text, and links between a Windows laptop and a phone browser over the same trusted Wi-Fi. No phone installation, account, subscription, or cloud relay.

**[Download the latest Windows release](https://github.com/smile-plzz/NearDrop/releases/latest)** · [Build status](https://github.com/smile-plzz/NearDrop/actions)

## Start in three steps

1. Extract **NearDrop-1.0.0-Windows-x64.zip** completely into a folder you control.
2. Double-click **NearDrop.exe**. Your laptop dashboard opens in your default browser. Keep the console window open.
3. Click **Pair a device** and scan the QR code using your phone camera. Give the phone a name and tap **Connect to laptop**.

When Windows asks about network access, allow the bundled Python runtime on your **private home network**. Both devices must be on the same Wi-Fi. Never enable router port forwarding for NearDrop.

Choose files on either device. Every paired device can download completed files and copy shared notes. On iPhone, use the browser's download action and the Files app; images downloaded as files may need **Share → Save Image/Video** to appear in Photos. Original bytes are preserved as provided by the browser; an iPhone photo picker can convert the source before upload. Select from Files when original format matters.

## Included

- Portable Windows x64 runtime: Python/Node installation is not required.
- Responsive desktop and phone interface, drag-and-drop, and multi-file queue.
- Sequential 1 MiB chunk uploads, progress, transfer speed, cancellation, automatic retry, and manual resume.
- Up to 20 GiB per file, subject to free laptop storage and browser constraints.
- Download ranges for browser-managed resumption.
- One-use 5-minute QR pairing links, per-device sessions, and laptop-controlled disconnection.
- Shared text and links with explicit copying; no automatic clipboard reading.
- Persistent received files and notes, file search, SHA-256 calculated after upload.
- Open received folder and delete shared files/notes from the laptop dashboard.
- Stop sharing from the dashboard; saved content remains on disk.
- Fully local QR generation; no analytics, remote fonts, or runtime CDN dependencies.

## Where files live

`%LOCALAPPDATA%\NearDrop\Received` contains completed files. Names have an internal unique ID prefix on disk so duplicates never overwrite each other. Downloads restore the display filename. The SQLite database and unfinished chunks are in sibling locations under `%LOCALAPPDATA%\NearDrop`.

Deleting a file in NearDrop removes the stored copy permanently. It does not remove the original file you selected for upload or any copies already downloaded elsewhere. Notes and completed files are kept until you delete them. The dashboard shows the latest 500 files and 100 notes; older files remain accessible through the received folder.

## Important operating limits

- **Local HTTP is not encrypted.** Pairing controls access but does not protect traffic from a network observer. Use only a trusted private network. Do not use for secrets or sensitive documents on public/shared Wi-Fi.
- Every paired device sees all completed files and notes. This is one shared room, not private device-to-device folders.
- A pairing link works once and expires after five minutes. Generating another invalidates the previous unused link. Scan again for each additional device.
- Sessions expire after 24 hours and are discarded when NearDrop restarts. Restart and pair again to restore access.
- Keep the phone browser foregrounded and the laptop awake during transfers. iOS can suspend background tabs or screen-locked uploads. Retry when back in the foreground.
- Upload retries resume within the same page and running session. Reloading the page loses its file selection; select it again to start a new upload. Restarting the server discards unfinished transfers.
- Completed files have a server-calculated checksum; this is not an independently verified sender-side cryptographic integrity proof.
- File finalization hashes the file before showing it as complete. A very large file can briefly delay other management operations.
- Device disconnection blocks subsequent requests. It cannot erase downloaded copies or reliably stop a download response already streaming.
- This release is unsigned and has no automatic updater, native system tray, HTTPS certificate setup, remote internet transfer, or automatic clipboard synchronization.

## Troubleshooting

**Phone cannot connect:** verify same Wi-Fi, turn off a VPN temporarily if it changes local routing, avoid guest networks with client isolation, and allow the runtime through Windows Firewall on the private network. In Pair a device, choose the correct laptop address if several adapters appear.

**Camera cannot open the link:** type the displayed network address in the phone browser and paste the full pairing link. A plain address opens the pairing screen but does not grant access.

**Laptop dashboard says not paired:** close NearDrop's console and launch it again. Open the newly launched dashboard; the old bootstrap link is single-use.

**Port already in use:** close the previous console, or run `runtime\python.exe app\server.py --port 47822`.

**Upload interrupted:** leave the page open and use Retry / resume. If storage is low, delete unwanted stored files or free space outside NearDrop.

**Downloaded file does not appear in Photos:** check the browser downloads and Files app, then use the iOS share sheet.

**Browser closes:** NearDrop continues running in the console until you close it or press Ctrl+C.

**Uninstall:** close the console and delete the extracted application folder. To remove saved transfers too, separately delete `%LOCALAPPDATA%\NearDrop` after backing up anything you want to keep.

## Development

Python 3.11+ is required for source execution. Segno 1.6.6 is vendored under `app/vendor` with its license.

```sh
python app/server.py
python -m unittest discover -s tests -v
```

The native launcher can be built with Zig 0.13: `zig cc -target x86_64-windows-gnu -Os -municode -Wl,--subsystem,windows tools/launcher.c tools/launcher.rc -o NearDrop.exe -luser32`. The fallback `NearDrop.cmd` starts the same runtime.

The optional browser suite uses Node.js and Playwright. Install Playwright and its Chromium browser, then run `node tests/browser.cjs`. The test uses isolated laptop/phone browser sessions and disposable data.

`python tools/package.py --runtime-zip path/to/python-3.14.7-embed-amd64.zip` creates the portable ZIP and SHA-256 manifest. The Windows GitHub Actions workflow runs the backend tests and packages a downloadable build. Successful main-branch builds publish the application version as a GitHub release if that version does not already exist. Existing release assets are preserved. Version tags must match the application version. The workflow also tests the extracted portable package using its bundled runtime on Windows.

See `docs/ARCHITECTURE.md` and `docs/VALIDATION.md` for design and test boundaries.

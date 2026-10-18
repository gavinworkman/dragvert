# Dragvert

A native Linux recreation of the **interaction shown in the supplied recording**:
drop a file on a radial tool wheel, convert it, crop it, or frame it with a background.
Built with Python, Qt 5, Pillow, Poppler and FFmpeg. Processing is local. No accounts,
uploads, telemetry or remote services. GPL-3.0, matching this repository's license.

## Install on Debian / ParrotOS

Download `dragvert_0.1.0_all.deb`, open a terminal in its folder, and run:

```sh
sudo apt install ./dragvert_0.1.0_all.deb
dragvert
```

Supported target: Debian 12/13 and compatible ParrotOS installations with Python 3.9+
and Qt 5 packages. The package is architecture-independent; apt installs native
dependencies. Actual ParrotOS desktop interaction still needs testing on the target.
Optional Office conversion: `sudo apt install libreoffice`.

Restart Dolphin after installing. Select files, right-click, and choose **Open in
Dragvert** (possibly inside **Actions**, depending on Dolphin version). If hidden,
enable Dragvert in Dolphin's **Configure Dolphin → Context Menu** settings. Both
the modern KIO and legacy KF5 service-menu locations are included.

## Use

- **X11:** keep Dragvert running. Start dragging a file in Dolphin, then hold Shift.
  Move onto a wheel segment and release the mouse. Dropping on the center selects
  the files; then click a tool. The app requests a copy drop; it never moves originals.
- **Wayland:** use the Dolphin context menu, or drag files into Dragvert's window.
  Global Shift-drag detection is intentionally disabled, including under XWayland.
- **Any session:** choose files from the main window, then click a wheel segment.
  Right-click the wheel to dismiss it; it also times out. Escape works when focused.
- Closing the main window keeps the app in the system tray when a tray is available.
  Use the tray's **Quit** action to exit. `dragvert --tray` starts minimized when possible.
  Without a tray, the main window stays accessible and closing it exits.
- Start at login by adding `dragvert --tray` in your desktop's Autostart settings.
  Installation does not silently enable autostart.

Files are saved **next to their source** with a new name. Existing files are never
replaced; collisions get `(1)`, `(2)`, etc. The source folder must be writable.
Batch errors are reported individually. Use **Show last output in Dolphin** to find
results. A second launch passes its files to the running app.

## Tools and scope

| Tool | Implemented behavior |
| --- | --- |
| Convert | Images → PNG/JPG/WEBP/PDF/TIFF/BMP; PDF → PNG/JPG (all pages, 150 DPI) or TXT; audio/video → MP4/WEBM/MP3/WAV/FLAC when source streams permit; Office → PDF via optional LibreOffice |
| Crop | Draw a rectangle; apply, reset, save PNG copy |
| Compress | JPG at quality 75, or WEBP for WEBP sources; output is not guaranteed smaller; JPG flattens transparency to white |
| Add BG | Two-color gradient, adjustable padding, corner radius and shadow, live preview; PNG export |
| Redact | Apply opaque black rectangles repeatedly; save a flattened PNG without original metadata |
| Annotate | Click a position, enter text, select size, apply repeatedly; PNG export |
| Edit | Rotate 90°, adjust brightness and contrast; PNG export |
| Metadata | File location/size, image dimensions/format/frame count and EXIF display |

Image tools accept one image at a time. Batch conversion/compression accepts multiple
files. Animated GIF and multipage TIFF inputs use **only the first frame**; a PDF
exports **every page**. EXIF orientation is applied and source metadata is stripped
from new image exports. JPG, BMP and image-to-PDF flatten alpha onto white. TXT
extraction requires a PDF text layer; there is no OCR. Direct PDF-to-DOCX, editable
PDF redaction, arbitrary external editor integration and metadata editing are not
implemented. To redact a PDF page, convert to PNG first and share only the flattened
redacted export. Review all sensitive areas before sharing.

Global X11 monitoring detects Shift + left-button, not Dolphin's internal drag state,
so the wheel can also appear during other Shift-drags. Disable the checkbox if that
conflicts with another application. The actual drop must contain local file URLs;
remote KIO locations must be copied locally first. Wayland does not grant portable
global pointer/drag access. The app does not install compositor-specific hooks.

## Run from source / build

```sh
sudo apt install python3-pyqt5 python3-pil poppler-utils ffmpeg fonts-dejavu-core libx11-6
./bin/dragvert
./scripts/build-deb.sh
```

The launcher deliberately uses Debian's `/usr/bin/python3` so apt-provided Qt/Pillow
are used rather than an unrelated virtual environment. The `.deb` installs under
`/usr/share/dragvert` with a `/usr/bin/dragvert` launcher. Build requires `dpkg-deb`
and standard Unix tools; no package downloads or root access are needed to build.

```sh
QT_QPA_PLATFORM=offscreen /usr/bin/python3 -m unittest discover -s tests -v
```

Tests cover output collision handling, source preservation, orientation, alpha
flattening, image edits, real PDF/media conversions, Qt geometry/drop handling and
editor export. Offscreen tests do not establish real Dolphin/X11/Wayland behavior.
Before release, test: multiple-file context menu; Shift-drag onto each wheel segment;
cancelled drags; tray reopen/quit; HiDPI/multiple monitors; filenames with spaces and
non-ASCII characters; Wayland drop fallback. Large image edits run on the UI thread
and may pause the editor; conversions run in a worker. External converters have a
10-minute per-process timeout. Cancelling a running conversion is not yet supported.

Uninstall: `sudo apt remove dragvert`. Exported files are retained.

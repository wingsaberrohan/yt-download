# Building installable applications

This project can be built as a proper **installable application** on both Windows and macOS.

---

## macOS: .app + .dmg (already installable)

On Mac, the build produces **YT-Downloader.app**, which users install by dragging to **Applications**.

1. **Build the app**
   ```bash
   pip install -r requirements.txt pyinstaller
   pyinstaller build.spec
   ```
   Output: `dist/YT-Downloader.app`

2. **Optional: create a .dmg for distribution**
   ```bash
   brew install create-dmg
   create-dmg \
     --volname "YT Downloader" \
     --icon "YT-Downloader.app" 120 180 \
     --app-drop-link 360 180 \
     "dist/YT-Downloader.dmg" \
     "dist/YT-Downloader.app"
   ```
   Users download the .dmg, open it, and drag the app to Applications.

**Install for yourself:** Copy `dist/YT-Downloader.app` to `/Applications` (or open the .dmg and drag it there).

---

## Windows: .exe folder vs installer

By default, PyInstaller produces a **folder** (`dist/YT-Downloader/`) with `YT-Downloader.exe` inside. You can zip and share it (portable — no install). To get a **proper installer** that installs like other Windows apps (Program Files, Start Menu, Add/Remove Programs), use Inno Setup.

### Step 1: Build the app with PyInstaller

```powershell
cd "c:\path\to\Youtube download"
pip install -r requirements.txt pyinstaller
pyinstaller build.spec
```

You get: `dist\YT-Downloader\` (folder with YT-Downloader.exe and dependencies).

### Step 2: Create the Windows installer (Inno Setup)

1. **Install Inno Setup** (free): https://jrsoftware.org/isinfo.php  
   Download and install the standard version.

2. **Compile the installer**
   - Open **Inno Setup Compiler**
   - File → Open → select `installer\YouTube-Downloader.iss`
   - Build → Compile  

   Or from command line (if `iscc` is in PATH):
   ```powershell
   cd "c:\path\to\Youtube download\installer"
   & "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" YouTube-Downloader.iss
   ```

3. **Output**
   - Installer is created at: `dist\YouTube-Downloader-Setup-3.0.exe` (or the version in the .iss file).

**What the installer does**
- Installs the app to `C:\Program Files\YouTube Downloader\` (or user choice)
- Adds **Start Menu** shortcut (YouTube Downloader)
- Optional **Desktop** shortcut (checkbox during install)
- Adds an entry in **Settings → Apps** (Add/Remove Programs) so users can uninstall cleanly

**Install for yourself:** Run `YouTube-Downloader-Setup-3.0.exe` and follow the wizard. The app will appear in the Start Menu like any other installed program.

---

## Summary

| Platform | Build output           | Installable form                          |
|----------|------------------------|-------------------------------------------|
| **macOS**  | `YT-Downloader.app`    | Drag to Applications (or use .dmg)       |
| **Windows** | `YT-Downloader\` folder | Run **YouTube-Downloader-Setup-3.0.exe** to install like a normal app |

The GitHub Actions workflow (on tag push) currently produces the **zip** (Windows) and **.dmg** (Mac). To publish the **Windows installer** from CI, you would add an Inno Setup step (e.g. install Inno Setup and run `iscc`); the script in `installer/YouTube-Downloader.iss` is ready for that if you want to add it later.

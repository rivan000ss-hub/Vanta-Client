# VANTA Launcher 0.5

Qt-based Minecraft Java launcher with selectable game directory and direct launch through Microsoft authentication.

## Features
- Select a custom Minecraft game directory; the selection is saved in VANTA settings.
- Download and verify official Minecraft Java 1.21.11 files into that directory.
- Install Fabric Loader, Fabric API, and Sodium in the selected directory.
- Sign in through the system browser using Microsoft OAuth (PKCE).
- Launch the installed Fabric profile directly from VANTA after Microsoft confirms Minecraft: Java Edition ownership.
- Manage local JAR mods by enabling/disabling them.

## Microsoft app setup (required for direct launch)
VANTA does not embed a third-party OAuth client ID. Provide the Application (client) ID of your own Microsoft Entra app in Settings.

Configure the app as a public desktop/mobile client and add the loopback redirect URI `http://localhost`. Microsoft requires an app registration and Minecraft Services permission for the OAuth client. Do not paste your Microsoft password or access token into VANTA; sign-in happens in the system browser.

The Microsoft account must own Minecraft: Java Edition. No offline/cracked authentication is provided.

## Install and run
1. Select a folder in Settings (for example `D:\\Games\\VANTA\\Minecraft`).
2. Click Install / Restore VANTA. The launcher downloads official game files, then Fabric and the two base mods.
3. Set the Microsoft Client ID in Settings.
4. Sign in through Microsoft in the browser.
5. Click Play. VANTA launches the Fabric profile directly.

## Build Windows
GitHub Actions builds an onedir package. Download the `VANTA-Launcher-Windows` artifact, extract the complete folder, and run `VANTA-Launcher.exe`. Do not move the EXE separately from its runtime files.

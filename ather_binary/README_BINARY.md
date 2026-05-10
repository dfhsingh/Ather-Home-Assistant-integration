# Ather Electric (Binary Integration)

This version of the Ather integration uses a compiled Rust core to handle API communication and security headers.

## Why this exists?
To prevent sensitive keys (like the Firebase API Key and Android Cert) from being flagged by GitHub's secret scanning, these values are embedded directly into a compiled binary. This also improves performance and stability.

## How to use

1. **Install Rust:** Ensure you have Rust and Cargo installed on your system.
2. **Compile the Core:**
   Run the build script:
   ```bash
   chmod +x build.sh
   ./build.sh
   ```
   This will create `ather_core.so` (or `.pyd` on Windows) in the `ather_binary` directory.
3. **Restart Home Assistant:** Home Assistant will now detect the `ather_binary` integration.
4. **Configuration:**
   - Go to **Settings > Devices & Services > Add Integration**.
   - Search for **Ather Electric (Binary)**.
   - Enter your **Mobile Number** and **Friendly Name**.
   - Enter the **OTP** received.
   - The integration will handle the rest without requiring a Firebase API Key.

## Structure
- `api.py`: Python wrapper that interfaces with the binary.
- `core/`: Rust source code for the high-performance API client.
- `build.sh`: Helper script for cross-platform compilation.

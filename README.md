
# Ather Electric Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

An unofficial Home Assistant integration for Ather Energy electric scooters (450X, 450 Plus, etc.). Monitor and manage your scooter's data directly within your smart home dashboard.

## The Backstory

This project started with a simple goal: **Automated Charging.** I wanted to park my Ather, plug it in, and let Home Assistant decide when to start or stop charging based on the Battery SoC. Once I cracked the API, I couldn't stop—and this full-fledged integration was born. It is now stable and part of my daily routine.

> [!TIP]
> While developed and tested on an **Ather 450X**, the shared API architecture should support other models like the 450 Plus, 450S, Rizta and Apex.

<img width="1052" height="533" alt="image" src="https://github.com/user-attachments/assets/abd06bb0-2237-44f3-a375-1045ed84ac3e" />

## 🚀 Features

* **Real-time Diagnostics**: State of Charge (SoC), Battery Health, and Charging Status.
* **Dynamic Range**: Live estimates for Eco, Ride, Sport, and Warp/Apex modes.
* **Location Tracking**: Integrated `device_tracker` to monitor your scooter’s position.
* **Advanced Sensors**: Odometer, trip details, and "Time to Full" estimates.
* **Remote Controls (Experimental)**: Ping, Remote Charge, and Shutdown (hardware/account dependent).

> [!TIP]
> The diagnostic entities will let you know which all 'features' are active (and inactive) based on the model and subscriptions

## 🛠 Installation

### Option 1: HACS (Recommended)

1. Open **HACS** > **Integrations**.
2. Select **Custom repositories** from the top-right menu.
3. Paste this repository URL and select **Integration** as the category.
4. Click **Install** and restart Home Assistant.

### Option 2: Manual

1. Download the `custom_components/ather_electric` folder.
2. Copy it into your Home Assistant `/config/custom_components/` directory.
3. Restart Home Assistant.

## ⚙️ Configuration

1. Navigate to **Settings** > **Devices & Services**.
2. Click **Add Integration** and search for **Ather Electric**.
3. Enter your registered phone number, Firebase Key*, and the OTP received.

> [!IMPORTANT]
> **Regarding the Firebase Key:** To communicate with Ather’s servers, a specific application key is required. This is typically retrieved by decompiling the official mobile app.

## 📊 Entities

| Entity | Description |
| --- | --- |
| `sensor.ather_soc` | Current battery percentage |
| `sensor.ather_range_*` | Range estimates for all ride modes |
| `binary_sensor.ather_charging` | Indicates if the charger is active |
| `device_tracker.ather_scooter` | GPS location of the vehicle |

---

## 📖 Documentation & Support

Check out the **[Wiki](https://github.com/dfhsingh/Ather-Home-Assistant-integration/wiki)** for:

* Sample Automation configs (like the Auto-Charging setup).
* Frequently Asked Questions.
* Advanced troubleshooting.

## Disclaimer

This is an unofficial community project. It is not affiliated with, endorsed by, or supported by Ather Energy. Use this integration at your own risk.

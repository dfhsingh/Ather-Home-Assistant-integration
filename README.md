# README.md

A custom component for Home Assistant designed for Ather electric scooters, featuring a high-performance binary core and dedicated time series storage.

---

## Key Features

* **VictoriaMetrics Integration**: Utilizes VictoriaMetrics TSDB to efficiently store and manage ride data.


* **Hybrid Architecture**: Built as a Python wrapper around a binary core to ensure high performance.


* **Multi-Platform Support**: Provides native support for both **aarch64** and **x86_64** architectures.



## Installation

To install the component, follow these steps:

1. Navigate to your Home Assistant configuration directory.


2. Locate or create the `custom_components` folder.


3. Copy the `ather_binary` folder into that directory.



**Path Structure:**
`<home assistant config folder>/custom_components/ather_binary/`

## Setup

1. Ensure you have a **VictoriaMetrics** instance reachable by Home Assistant.


2. Restart Home Assistant.


3. Configure the integration via the Home Assistant UI or `configuration.yaml`.

<div align="center">

# PicoLimbo Integration Tests

**A Docker-based test harness for verifying [PicoLimbo](https://github.com/Quozul/PicoLimbo) against real Minecraft clients**

*Supporting 81 Minecraft versions from 1.7.2 through 26.1.2*

[![Docker](https://img.shields.io/badge/Docker-Ready-blue)](https://www.docker.com/)
[![Python](https://img.shields.io/badge/Python-3.12+-blue)](https://www.python.org/)

[💬 Join the conversation](https://discord.gg/M2a9dxJPRy) • [📖 PicoLimbo](https://github.com/Quozul/PicoLimbo)

![PicoLimbo Tester UI](docs/PicoLimbo_Tester.png)

</div>

---

## Introduction

PicoLimbo is an ultra-lightweight, multi-version Minecraft limbo server written in Rust. This sidecar project was built specifically to test PicoLimbo against **real Minecraft clients** across dozens of versions.

It builds PicoLimbo from source, launches the server, runs Minecraft clients for each requested version inside a virtual desktop, and captures screenshots confirming successful connections. The entire system runs inside a single Docker container with a virtual display, making it suitable for CI/CD pipelines or headless environments.

---

## Features

### 🏗️ Automated Build Pipeline

Clones the PicoLimbo repository, builds the Rust binary, and caches artifacts. Supports specifying a branch name or commit hash.

### 🎮 Multi-Version Client Testing

Launches real Minecraft clients for each requested version, from **1.7.2 to 26.1.2**, connecting them all to the same PicoLimbo server instance.

### 📸 Screenshot Verification

Each client's screen is captured via virtual display (Xvfb/Xorg). Screen region matching against reference images confirms the game is fully loaded before disconnecting.

### 🖥️ Embedded Web UI

A React-based dashboard is embedded in the Docker image, served at port 8000, providing a three-column layout for job creation, VNC viewing, and job history.

### 📡 REST API

A FastAPI backend exposes endpoints for creating jobs, monitoring progress, and downloading artifacts, all consumable via curl or any HTTP client.

---

## Quick Start

### Prerequisites

- [Docker](https://www.docker.com/) and [Docker Compose](https://docs.docker.com/compose/)
- A machine with at least 2 GB of RAM (more if testing many versions concurrently)

### Running the Project

```shell
# Build and start the container in detached mode
docker compose up --build -d
```

Once running, open the web UI at **http://localhost:8000** to create jobs, monitor progress, and view results.

---

## AI Disclosure

This project is largely vibe-coded. This is mostly fine as it's for internal use only.

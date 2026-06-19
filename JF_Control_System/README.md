# JF Control System

Unified JUNGFRAU detector experiment control system, integrating four major functional modules into a single interface.

## Function Modules

| Module | Function | Hardware Interface |
|--------|----------|--------------------|
| Displacement Stage | ARIES/LYNX stage precision positioning and scanning | RS-232C serial |
| Water Chiller | Temperature monitoring, flow monitoring, parameter setting | MODBUS RTU / RS-485 |
| Detector | JUNGFRAU 500K/4M detector data acquisition | slsDetector SDK (UDP) |
| Data Processing | X-ray sensor calibration (7 processing modes) | .raw file I/O |

## Interface Layout

- **Top Status Bar** -- Brand logo + real-time connection status for all three modules
- **Tab Navigation** -- Experiment Control | Data Analysis
- **Experiment Control** -- Left: displacement + chiller panels (collapsible), Right: full detector acquisition interface
- **Data Analysis** -- 7 processing modes, left parameter panel + right result display

## Quick Start

```bash
# 1. Install backend dependencies
pip install -r requirements.txt

# 2. Install frontend dependencies
cd frontend
npm install
cd ..

# 3. One-click launch
python start.py
```

Backend runs at `http://localhost:8000`, frontend runs at `http://localhost:5173`.

## Project Structure

```
JF_Control_System/
├── start.py                  # One-click launcher
├── run.py                    # Backend entry (uvicorn)
├── requirements.txt          # Python dependencies
│
├── backend/                  # FastAPI backend
│   ├── main.py               # App entry + WebSocket endpoint
│   ├── models.py             # Pydantic data models
│   ├── ws_manager.py         # WebSocket push manager
│   ├── displacement/         # Displacement module
│   │   ├── router.py         # REST API routes (/api/displacement/*)
│   │   └── service.py        # Wrapper around original Displacement
│   ├── chiller/              # Chiller module
│   │   ├── router.py         # REST API routes (/api/chiller/*)
│   │   └── service.py        # Wrapper around original Water Chiller
│   ├── detector/             # Detector module
│   │   ├── router.py         # REST API routes (/api/detector/*)
│   │   └── service.py        # Wrapper around original JF_acquire
│   └── processing/           # Data processing module
│       ├── router.py         # REST API routes (/api/processing/*)
│       └── service.py        # Wrapper around original Data Processing
│
└── frontend/                 # Vue 3 + Naive UI frontend
    ├── package.json
    ├── vite.config.ts
    └── src/
        ├── App.vue           # Root: dark theme + tab navigation
        ├── components/
        │   ├── ConnectionBar.vue   # Live connection status bar
        │   ├── ControlView.vue     # Experiment control tab layout
        │   ├── ProcessingView.vue  # Data analysis tab layout
        │   ├── displacement/
        │   │   └── DisplacementPanel.vue
        │   ├── chiller/
        │   │   └── ChillerPanel.vue
        │   └── detector/
        │       ├── StatusPanel.vue
        │       ├── ParamSettings.vue
        │       ├── AcquisitionControl.vue
        │       ├── HeatmapView.vue
        │       ├── HistoryList.vue
        │       └── FileBrowser.vue
        ├── composables/
        │   ├── useDetector.ts
        │   ├── useDisplacement.ts
        │   ├── useChiller.ts
        │   └── useWebSocket.ts
        ├── api/
        │   ├── client.ts
        │   ├── displacement.ts
        │   └── chiller.ts
        └── types/
            └── detector.ts
```

## Tech Stack

| Layer | Technology |
|-------|------------|
| Frontend framework | Vue 3.5 + TypeScript 6.0 |
| UI component library | Naive UI 2.39 |
| Charts | ECharts 6 (control) / Plotly.js (analysis) |
| Backend framework | FastAPI + uvicorn |
| Real-time communication | WebSocket (500ms push) |
| Hardware communication | pyserial (RS-232C) + pymodbus (RS-485) + slsDetector SDK |

## API Overview

| Endpoint | Description |
|----------|-------------|
| `GET /api/health` | Backend health check |
| `GET /api/config` | System configuration |
| `WS /ws` | WebSocket for live status push |
| `/api/displacement/*` | 15 routes: connect, move, scan, etc. |
| `/api/chiller/*` | 12 routes: status, setpoint, PID, etc. |
| `/api/detector/*` | 13 routes: acquire, config, file browse, etc. |
| `/api/processing/*` | 6 routes: frame read, pixel fit, gain map, etc. |

## Design Principles

- **Don't modify original code** -- All backend `service.py` files import and wrap original module core classes without modification
- **Unified UI style** -- Naive UI dark theme (`#0a1628` background, `#00d4ff` accent color)
- **Modular architecture** -- Each hardware module has an independent backend router and frontend component tree
- **Live connection status** -- WebSocket pushes connection state for all three modules every 500ms

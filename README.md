# SynAptIp Nyquist Analyzer v1.0

A desktop scientific tool for impedance analysis using LCR meter data.

---

## Description

SynAptIp Nyquist Analyzer is a standalone GUI application for processing and visualizing impedance spectroscopy data exported from LCR meters. It generates publication-quality Nyquist and Bode plots, provides a live PNG-based preview inside the application, and exports results in ready-to-use formats — all without requiring manual scripting.

---

## Features

- CSV and TXT processing from LCR meter exports
- Nyquist plot generation with automatic axis scaling
- Bode magnitude and phase plots
- Scientific visualization with clean, styled output
- GUI-based workflow — no scripting required
- PNG-based preview panel for stable, flicker-free display
- Export-ready outputs (PNG plots + processed CSV)

---

## Project Structure

```text
SynAptIp-Nyquist-QuickApp/
├── nyquist_app.py          # Main application
├── requirements.txt        # Python dependencies
├── README.md
├── .gitignore
├── assets/
│   ├── SynAptIp-Nyquist.png    # Application logo
│   └── SynAptIp-Nyquist.ico    # Window and EXE icon
├── sample_data/
│   └── example_lcr_data.csv    # Example LCR meter export
└── screenshots/
    └── app_preview.png         # Application preview image
```

---

## Requirements

- Python 3.10 or later
- Install dependencies:

```bash
pip install -r requirements.txt
```

Dependencies: `pandas`, `matplotlib`, `numpy`, `pillow`

---

## How to Run Locally

```bash
python nyquist_app.py
```

1. Launch the application.
2. Click **Process File** and select an LCR meter CSV or TXT export.
3. The tool processes the data and generates Nyquist and Bode plots automatically.
4. Review the Nyquist preview in the right panel.
5. Find the exported plots and processed CSV in the output folder next to your source file.

---

## How to Build the Executable

Use PyInstaller to create a standalone Windows EXE:

```bash
pyinstaller --clean --name "SynAptIp Nyquist Analyzer v1.0" --onefile --windowed --icon assets/SynAptIp-Nyquist.ico --add-data "assets/SynAptIp-Nyquist.png;assets" nyquist_app.py
```

The resulting executable will be located in the `dist/` folder.

---

## Version

**Version 1.0** — First stable public release.

This version delivers a complete, self-contained desktop workflow for LCR impedance data: file input, scientific processing, plot generation, and GUI preview.

---

## Roadmap

Planned improvements for future versions:

- Multi-mode LCR interpretation (series / parallel circuit models)
- Automated circuit behavior suggestions based on impedance profile
- Equivalent circuit fitting
- Advanced impedance modeling (Randles cell, CPE elements)
- Premium scientific reporting (PDF export)
- Batch processing for multiple files

---

## Screenshot

![Application Preview](screenshots/app_preview.png)

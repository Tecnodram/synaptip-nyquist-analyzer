from pathlib import Path
from typing import Optional
import os
import sys
import traceback
import tkinter as tk
from tkinter import filedialog, messagebox

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from PIL import Image, ImageTk


def resource_path(relative_path):
    """
    Return absolute path to resource for both development and PyInstaller builds.
    """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    resource_full_path = os.path.join(base_path, relative_path)
    if os.path.exists(resource_full_path):
        return resource_full_path

    return os.path.join(base_path, Path(relative_path).name)


def load_measurement_file(file_path: str) -> pd.DataFrame:
    """
    Carga un archivo CSV o TXT exportado por LCR meter.
    Detecta el inicio real de la tabla buscando la cabecera de datos.
    """
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"No se encontró el archivo: {file_path}")

    if path.suffix.lower() not in [".csv", ".txt"]:
        raise ValueError("Solo se permiten archivos .csv o .txt")

    # Buscar la primera fila de cabecera real (evita confundir metadata tipo "Frequency:From ...").
    header_idx = None
    lines = []

    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            lines = f.readlines()
    except UnicodeDecodeError:
        with open(path, "r", encoding="latin-1") as f:
            lines = f.readlines()

    for idx, line in enumerate(lines):
        line_clean = line.strip().lower()
        if line_clean.startswith("frequency,") or line_clean.startswith("frequency\t"):
            header_idx = idx
            break

    if header_idx is None:
        raise ValueError("No se encontró la cabecera de datos del archivo LCR.")

    try:
        df = pd.read_csv(path, skiprows=header_idx, skipinitialspace=True)
    except Exception:
        df = pd.read_csv(path, skiprows=header_idx, sep="\t", skipinitialspace=True)

    df.columns = [str(col).strip() for col in df.columns]
    return df


def standardize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Convierte nombres de columnas de export LCR a nombres estándar.
    """
    rename_map = {}

    for col in df.columns:
        c = str(col).strip().lower()
        normalized = c.replace(" ", "")

        if normalized == "frequency" or "freq" in normalized:
            rename_map[col] = "Frequency_Hz"

        elif normalized in ["z(ohm)", "z", "|z|", "impedance", "impedance(ohm)"]:
            rename_map[col] = "Z_mag_ohm"

        elif normalized in ["td(deg)", "phase", "phase(deg)", "td"]:
            rename_map[col] = "Phase_deg"

        elif c in ["z'", "real", "zr", "z_real", "z real", "resistance", "r"]:
            rename_map[col] = "Z_real_ohm"

        elif c in ["z''", "imag", "zi", "z_imag", "z imag", "reactance", "x"]:
            rename_map[col] = "Z_imag_ohm"

        elif "mag" in c or "|z|" in c:
            rename_map[col] = "Z_mag_ohm"

        elif "phase" in c:
            rename_map[col] = "Phase_deg"

    df = df.rename(columns=rename_map)
    return df


def convert_to_numeric(df: pd.DataFrame) -> pd.DataFrame:
    """
    Convierte a numérico las columnas que normalmente deberían ser numéricas.
    """
    df = df.copy()
    for col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def compute_impedance(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calcula componentes faltantes.
    Acepta:
    - Frequency_Hz + Z_real_ohm + Z_imag_ohm
    o
    - Frequency_Hz + Z_mag_ohm + Phase_deg
    """
    df = df.copy()

    if "Frequency_Hz" not in df.columns:
        raise ValueError(
            "No encontré columna de frecuencia. Revisa que el archivo tenga algo como 'Frequency'."
        )

    has_real_imag = "Z_real_ohm" in df.columns and "Z_imag_ohm" in df.columns
    has_mag_phase = "Z_mag_ohm" in df.columns and "Phase_deg" in df.columns

    if has_real_imag:
        df["Z_real_ohm"] = pd.to_numeric(df["Z_real_ohm"], errors="coerce")
        df["Z_imag_ohm"] = pd.to_numeric(df["Z_imag_ohm"], errors="coerce")
        df["Frequency_Hz"] = pd.to_numeric(df["Frequency_Hz"], errors="coerce")

        df = df.dropna(subset=["Frequency_Hz", "Z_real_ohm", "Z_imag_ohm"])

        df["Z_mag_ohm"] = np.sqrt(df["Z_real_ohm"] ** 2 + df["Z_imag_ohm"] ** 2)
        df["Phase_deg"] = np.degrees(np.arctan2(df["Z_imag_ohm"], df["Z_real_ohm"]))

    elif has_mag_phase:
        df["Z_mag_ohm"] = pd.to_numeric(df["Z_mag_ohm"], errors="coerce")
        df["Phase_deg"] = pd.to_numeric(df["Phase_deg"], errors="coerce")
        df["Frequency_Hz"] = pd.to_numeric(df["Frequency_Hz"], errors="coerce")

        df = df.dropna(subset=["Frequency_Hz", "Z_mag_ohm", "Phase_deg"])

        phase_rad = np.radians(df["Phase_deg"])
        df["Z_real_ohm"] = df["Z_mag_ohm"] * np.cos(phase_rad)
        df["Z_imag_ohm"] = df["Z_mag_ohm"] * np.sin(phase_rad)

    else:
        raise ValueError(
            "El archivo debe tener:\n"
            "1) Frequency + Z_real + Z_imag\n"
            "o\n"
            "2) Frequency + Z_mag + Phase"
        )

    df["minus_Z_imag_ohm"] = -df["Z_imag_ohm"]

    # ordenar por frecuencia descendente si existe
    df = df.sort_values(by="Frequency_Hz", ascending=False).reset_index(drop=True)

    return df


def save_results(df: pd.DataFrame, input_file: str, custom_name: Optional[str] = None) -> Path:
    """
    Guarda CSV procesado y gráficas en una carpeta output.
    """
    input_path = Path(input_file)
    output_dir = input_path.parent / "output"
    output_dir.mkdir(exist_ok=True)

    # Use custom base name when provided; otherwise keep current input-file behavior.
    stem = (custom_name or "").strip() or input_path.stem

    processed_csv = output_dir / f"{stem}_processed.csv"
    nyquist_png = output_dir / f"{stem}_nyquist.png"
    bode_mag_png = output_dir / f"{stem}_bode_magnitude.png"
    bode_phase_png = output_dir / f"{stem}_bode_phase.png"

    df.to_csv(processed_csv, index=False)

    def _apply_scientific_grid(ax):
        ax.minorticks_on()
        ax.grid(True, which="major", linestyle="--", linewidth=0.7, alpha=0.55)
        ax.grid(True, which="minor", linestyle="--", linewidth=0.5, alpha=0.28)

    def _apply_nyquist_display_limits(ax, x_data: pd.Series, y_data: pd.Series):
        # Keep all data; only adjust displayed limits when outliers dominate visual range.
        x = np.asarray(x_data, dtype=float)
        y = np.asarray(y_data, dtype=float)
        mask = np.isfinite(x) & np.isfinite(y)
        x = x[mask]
        y = y[mask]
        if x.size < 5:
            return

        def _robust_bounds(values: np.ndarray):
            vmin = float(np.min(values))
            vmax = float(np.max(values))
            full_span = vmax - vmin
            if full_span <= 0:
                return None

            p_low, p_high = np.percentile(values, [2, 98])
            robust_span = float(p_high - p_low)
            if robust_span <= 0:
                return None

            # Conservative threshold to avoid clipping normal data ranges.
            if full_span / robust_span < 4.5:
                return None

            pad = 0.07 * robust_span
            low = min(float(p_low) - pad, 0.0)
            high = max(float(p_high) + pad, 0.0)
            if high <= low:
                return None
            return low, high

        x_bounds = _robust_bounds(x)
        y_bounds = _robust_bounds(y)
        if x_bounds is not None:
            ax.set_xlim(*x_bounds)
        if y_bounds is not None:
            ax.set_ylim(*y_bounds)

    def _style_nyquist_axis(ax, x_data: pd.Series, y_data: pd.Series):
        ax.plot(x_data, y_data, linestyle="-", linewidth=0.8, alpha=0.6, color="tab:blue")
        ax.scatter(x_data, y_data, s=26, marker="o", color="tab:blue", edgecolors="white", linewidths=0.5, zorder=3)
        ax.set_xlabel("Z' (Ohm)")
        ax.set_ylabel("-Z'' (Ohm)")
        ax.set_title("Nyquist Plot")
        _apply_scientific_grid(ax)
        ax.axis("equal")
        _apply_nyquist_display_limits(ax, x_data, y_data)

    # Nyquist
    fig, ax = plt.subplots(figsize=(8, 6))
    _style_nyquist_axis(ax, df["Z_real_ohm"], df["minus_Z_imag_ohm"])
    fig.tight_layout()
    fig.savefig(nyquist_png, dpi=200)
    plt.close(fig)

    # Bode magnitude
    fig, ax = plt.subplots(figsize=(8, 6))
    ax.plot(df["Frequency_Hz"], df["Z_mag_ohm"], linestyle="-", linewidth=0.9, alpha=0.7, color="tab:orange")
    ax.scatter(df["Frequency_Hz"], df["Z_mag_ohm"], s=22, marker="o", color="tab:orange", edgecolors="white", linewidths=0.5, zorder=3)
    ax.set_xscale("log")
    ax.set_xlabel("Frequency (Hz)")
    ax.set_ylabel("|Z| (Ohm)")
    ax.set_title("Bode Magnitude")
    _apply_scientific_grid(ax)
    fig.tight_layout()
    fig.savefig(bode_mag_png, dpi=200)
    plt.close(fig)

    # Bode phase
    fig, ax = plt.subplots(figsize=(8, 6))
    ax.plot(df["Frequency_Hz"], df["Phase_deg"], linestyle="-", linewidth=0.9, alpha=0.7, color="tab:green")
    ax.scatter(df["Frequency_Hz"], df["Phase_deg"], s=22, marker="o", color="tab:green", edgecolors="white", linewidths=0.5, zorder=3)
    ax.set_xscale("log")
    ax.set_xlabel("Frequency (Hz)")
    ax.set_ylabel("Phase (deg)")
    ax.set_title("Bode Phase")
    _apply_scientific_grid(ax)
    fig.tight_layout()
    fig.savefig(bode_phase_png, dpi=200)
    plt.close(fig)

    return output_dir


def get_dominant_behavior(df: pd.DataFrame) -> str:
    """
    Clasifica el comportamiento dominante según la fase promedio.
    """
    if "Phase_deg" not in df.columns:
        return "Unknown"

    mean_phase = df["Phase_deg"].mean()

    if mean_phase <= -70:
        return "Capacitive"
    elif mean_phase >= 70:
        return "Inductive"
    elif abs(mean_phase) < 20:
        return "Resistive"
    else:
        return "Resistive / Mixed"


def estimate_capacitance(df: pd.DataFrame) -> Optional[str]:
    """
    Estima la capacitancia si el comportamiento es capacitivo.
    Retorna string formateado (F, mF, uF, nF, pF) o None.
    """
    behavior = get_dominant_behavior(df)
    if behavior != "Capacitive":
        return None

    if "Frequency_Hz" not in df.columns or "Z_imag_ohm" not in df.columns:
        return None

    omega = 2 * np.pi * df["Frequency_Hz"]
    C = 1 / (omega * np.abs(df["Z_imag_ohm"]))

    # Filtrar valores válidos y finitos
    C_valid = C[np.isfinite(C)]
    if len(C_valid) == 0:
        return None

    C_median = np.median(C_valid)

    # Formato legible
    if C_median >= 1:
        return f"{C_median:.3e} F"
    elif C_median >= 1e-3:
        return f"{C_median * 1e3:.3f} mF"
    elif C_median >= 1e-6:
        return f"{C_median * 1e6:.3f} uF"
    elif C_median >= 1e-9:
        return f"{C_median * 1e9:.3f} nF"
    else:
        return f"{C_median * 1e12:.3f} pF"


def process_file(custom_name: str = ""):
    # Sanitize optional output name from GUI input.
    custom_name = (custom_name or "").strip()
    if custom_name == "example: sample1":
        custom_name = ""

    file_path = filedialog.askopenfilename(
        title="Selecciona archivo del LCR meter",
        filetypes=[("Archivos CSV o TXT", "*.csv *.txt")]
    )

    if not file_path:
        return

    try:
        df = load_measurement_file(file_path)
        df = standardize_columns(df)
        df = convert_to_numeric(df)
        df = compute_impedance(df)
        # Forward optional GUI name. Empty value preserves default output names.
        output_dir = save_results(df, file_path, custom_name=custom_name)

        messagebox.showinfo(
            "Proceso completado",
            f"Listo.\n\nSe generaron los resultados en:\n{output_dir}"
        )

    except Exception as e:
        error_details = traceback.format_exc()
        print(error_details)
        messagebox.showerror(
            "Error",
            f"Ocurrió un error:\n\n{e}\n\nRevisa la terminal para más detalles."
        )


def main():
    root = tk.Tk()
    root.title("SynAptIp – Nyquist Analyzer")
    try:
        root.state("zoomed")
    except Exception:
        root.geometry("1200x820")
    root.minsize(620, 580)
    root.resizable(True, True)
    root.configure(bg="#eef2f7")
    root.grid_columnconfigure(0, weight=1)
    root.grid_rowconfigure(0, weight=1)

    # Load window icon and visible logo from the same PNG if available.
    icon_path = resource_path("assets/SynAptIp-Nyquist.png")
    if os.path.exists(icon_path):
        try:
            icon_img = tk.PhotoImage(file=icon_path)
            root.iconphoto(True, icon_img)
            # Keep reference to prevent garbage collection.
            root._icon_img = icon_img
        except Exception:
            pass

    # Two-panel content layout: compact left info panel + dominant right preview panel.
    content_frame = tk.Frame(root, bg="#eef2f7")
    content_frame.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
    content_frame.grid_rowconfigure(0, weight=1)
    content_frame.grid_columnconfigure(0, weight=0, minsize=360)
    content_frame.grid_columnconfigure(1, weight=3)

    left_panel = tk.Frame(content_frame, bg="#f8fafc", relief="groove", borderwidth=1)
    left_panel.grid(row=0, column=0, padx=(0, 10), sticky="ns")
    left_panel.grid_rowconfigure(0, weight=1)
    left_panel.grid_columnconfigure(0, weight=1)

    right_panel = tk.Frame(content_frame, bg="#f8fafc", relief="groove", borderwidth=1)
    right_panel.grid(row=0, column=1, sticky="nsew")
    right_panel.grid_rowconfigure(1, weight=1)
    right_panel.grid_columnconfigure(0, weight=1)

    # LEFT PANEL: logo, identity, controls, and analysis summary.
    left_content = tk.Frame(left_panel, bg="#f8fafc")
    left_content.grid(row=0, column=0, padx=18, pady=16)

    logo_label = None
    try:
        logo_path = resource_path("assets/SynAptIp-Nyquist.png")
        logo_img = tk.PhotoImage(file=logo_path)
        logo_img = logo_img.subsample(2, 2)
        root.logo_img = logo_img
        logo_label = tk.Label(left_content, image=root.logo_img, bg="#f8fafc")
        logo_label.pack(anchor="center", pady=(0, 10))
    except Exception as e:
        print("Logo not loaded:", e)

    title_label = tk.Label(
        left_content,
        text="SynAptIp – Nyquist Analyzer",
        font=("Arial", 14, "bold"),
        bg="#f8fafc",
        fg="#1f2937",
        anchor="center",
        justify="center"
    )
    title_label.pack(anchor="center")

    subtitle_label = tk.Label(
        left_content,
        text="Scientific Impedance Analysis Suite",
        font=("Arial", 9),
        bg="#f8fafc",
        fg="#4b5563",
        anchor="center",
        justify="center"
    )
    subtitle_label.pack(anchor="center", pady=(2, 12))

    process_button = tk.Button(
        left_content,
        text="Cargar archivo y generar resultados",
        font=("Arial", 10),
        command=lambda: process_file_with_gui(output_name_entry.get()),
        width=30,
        height=1
    )
    process_button.pack(anchor="center", pady=(0, 10))

    output_name_label = tk.Label(
        left_content,
        text="Optional output name",
        font=("Arial", 9),
        bg="#f8fafc",
        fg="#374151",
        anchor="center",
        justify="center"
    )
    output_name_label.pack(anchor="center")

    output_name_entry = tk.Entry(left_content, width=34, font=("Arial", 9), justify="center")
    output_name_entry.pack(anchor="center", pady=(2, 12))

    summary_title = tk.Label(
        left_content,
        text="Measurement Summary",
        font=("Arial", 10, "bold"),
        bg="#f8fafc",
        fg="#1f2937",
        anchor="center",
        justify="center"
    )
    summary_title.pack(anchor="center", pady=(0, 4))

    summary_label = tk.Label(
        left_content,
        text="No file processed yet.",
        font=("Arial", 9),
        bg="#f8fafc",
        fg="#374151",
        anchor="center",
        justify="center",
        wraplength=300
    )
    summary_label.pack(anchor="center", pady=(0, 10))

    behavior_label = tk.Label(
        left_content,
        text="Dominant behavior: N/A",
        font=("Arial", 9),
        fg="#1d4ed8",
        bg="#f8fafc",
        anchor="center",
        justify="center",
        wraplength=300
    )
    behavior_label.pack(anchor="center", pady=(0, 4))

    capacitance_label = tk.Label(
        left_content,
        text="Estimated capacitance: N/A",
        font=("Arial", 9),
        fg="#047857",
        bg="#f8fafc",
        anchor="center",
        justify="center",
        wraplength=300
    )
    capacitance_label.pack(anchor="center", pady=(0, 12))

    notes_title = tk.Label(
        left_content,
        text="Suggested Analysis / Notes",
        font=("Arial", 10, "bold"),
        bg="#f8fafc",
        fg="#1f2937",
        anchor="center",
        justify="center"
    )
    notes_title.pack(anchor="center", pady=(0, 4))

    notes_label = tk.Label(
        left_content,
        text="Run a measurement to see guidance.",
        font=("Arial", 9),
        bg="#f8fafc",
        fg="#4b5563",
        anchor="center",
        justify="center",
        wraplength=300
    )
    notes_label.pack(anchor="center", pady=(0, 4), fill=tk.X)

    # RIGHT PANEL: wide preview area as the main visual focus.
    preview_label = tk.Label(
        right_panel,
        text="Nyquist Plot Preview",
        font=("Arial", 11, "bold"),
        fg="#1f2937",
        bg="#f8fafc"
    )
    preview_label.grid(row=0, column=0, padx=12, pady=(10, 6), sticky="w")

    preview_frame = tk.Frame(right_panel, bg="white", relief="sunken", borderwidth=1)
    preview_frame.grid(row=1, column=0, padx=12, pady=(0, 12), sticky="nsew")
    preview_frame.grid_rowconfigure(0, weight=1)
    preview_frame.grid_columnconfigure(0, weight=1)

    preview_image_label = tk.Label(
        preview_frame,
        text="Nyquist preview will appear here after processing.",
        bg="white",
        fg="#6b7280",
        anchor="center",
        justify="center"
    )
    preview_image_label.grid(row=0, column=0, padx=8, pady=8, sticky="nsew")

    # Store GUI state for access in process_file.
    root._preview_frame = preview_frame
    root._preview_image_label = preview_image_label
    root._summary_label = summary_label
    root._behavior_label = behavior_label
    root._capacitance_label = capacitance_label
    root._notes_label = notes_label
    root._preview_image_path = None
    root._preview_photo = None
    root._resize_job = None

    def render_preview_image():
        if root._preview_image_path is None:
            return

        frame_width = max(root._preview_frame.winfo_width() - 16, 220)
        frame_height = max(root._preview_frame.winfo_height() - 16, 180)

        try:
            image = Image.open(root._preview_image_path)
            image.thumbnail((frame_width, frame_height), getattr(Image, "Resampling", Image).LANCZOS)
            preview_photo = ImageTk.PhotoImage(image)
            root._preview_image_label.config(image=preview_photo, text="")
            root._preview_image_label.image = preview_photo
            root._preview_photo = preview_photo
        except Exception as exc:
            root._preview_image_label.config(image="", text=f"Preview not available.\n{exc}")
            root._preview_image_label.image = None
            root._preview_photo = None

    def on_preview_resize(_event):
        if root._preview_image_path is None:
            return
        if root._resize_job is not None:
            root.after_cancel(root._resize_job)
        root._resize_job = root.after(120, render_preview_image)

    root._preview_frame.bind("<Configure>", on_preview_resize)

    def process_file_with_gui(custom_name: str = ""):
        """
        Wrapper that calls process_file and updates GUI with results.
        """
        custom_name = (custom_name or "").strip()
        if custom_name == "example: sample1":
            custom_name = ""

        file_path = filedialog.askopenfilename(
            title="Selecciona archivo del LCR meter",
            filetypes=[("Archivos CSV o TXT", "*.csv *.txt")]
        )

        if not file_path:
            return

        try:
            df = load_measurement_file(file_path)
            df = standardize_columns(df)
            df = convert_to_numeric(df)
            df = compute_impedance(df)
            output_dir = save_results(df, file_path, custom_name=custom_name)

            # Compute and display dominant behavior.
            behavior = get_dominant_behavior(df)
            root._behavior_label.config(text=f"Dominant behavior: {behavior}")

            # Compute and display estimated capacitance.
            cap = estimate_capacitance(df)
            if cap:
                root._capacitance_label.config(text=f"Estimated capacitance: {cap}")
            else:
                root._capacitance_label.config(text="Estimated capacitance: N/A")

            # Compact measurement summary and notes on the left panel.
            freq_min = float(df["Frequency_Hz"].min())
            freq_max = float(df["Frequency_Hz"].max())
            root._summary_label.config(
                text=(
                    f"Points: {len(df)}\n"
                    f"Frequency range: {freq_min:.3g} Hz to {freq_max:.3g} Hz"
                )
            )

            if behavior == "Capacitive":
                note_text = "Capacitive response detected. Review low-frequency tail and fitted C estimates."
            elif behavior == "Inductive":
                note_text = "Inductive response detected. Check high-frequency lead effects and wiring parasitics."
            elif behavior == "Resistive":
                note_text = "Resistive-dominant response. Verify near-zero phase region and resistance stability."
            else:
                note_text = "Mixed response. Consider equivalent-circuit fitting to separate overlapping processes."
            root._notes_label.config(text=note_text)

            stem = (custom_name or "").strip() or Path(file_path).stem
            root._preview_image_path = output_dir / f"{stem}_nyquist.png"
            render_preview_image()

            messagebox.showinfo(
                "Proceso completado",
                f"Listo.\n\nSe generaron los resultados en:\n{output_dir}"
            )

        except Exception as e:
            error_details = traceback.format_exc()
            print(error_details)
            messagebox.showerror(
                "Error",
                f"Ocurrió un error:\n\n{e}\n\nRevisa la terminal para más detalles."
            )

    root.mainloop()


if __name__ == "__main__":
    main()
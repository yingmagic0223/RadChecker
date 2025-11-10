# -*- coding: utf-8 -*-
"""
Memory-Enabled Contour QA Dashboard (Improved Version)
Author: S228593
Version: 2.0 - Enhanced with validation, logging, and thread safety
"""

import os
import json
import logging
import tempfile
import shutil
from typing import Dict, Any, List, Tuple
from threading import Lock
from datetime import datetime
from enum import Enum

import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
import dash
from dash import dcc, html, dash_table, Input, Output, State, ctx
import pandas as pd
import plotly.express as px

# -------------------------
# Logging Configuration
# -------------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('qa_dashboard.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# -------------------------
# Configuration
# -------------------------
class QAConfig:
    """Configuration for QA Dashboard"""
    MEMORY_FILE = "qa_memory.json"
    TOP_K_SIMILAR = 5

    # Validation ranges
    PTV_VOLUME_RANGE = (0.1, 2000.0)  # cc
    FRACTIONS_RANGE = (1, 100)

    # Standard values
    STANDARD_FRACTIONS = [15, 20, 25, 30, 35, 39]
    APPROVED_MACHINES = ["Varian TrueBeam", "Elekta VersaHD", "Elekta", "CyberKnife"]
    APPROVED_GRID_SIZES = ["2.5 mm", "3.0 mm", "2.0 mm"]

    # Sites for feature extraction
    KNOWN_SITES = ["Prostate", "Pancreas", "Lung", "Breast", "Head&Neck", "Other"]

    # Site-specific constraints
    SITE_CONSTRAINTS = {
        "Prostate": {
            "typical_ptv_range": (80, 200),
            "typical_fractions": [39, 20],
            "oar_list": ["Rectum", "Bladder", "Femoral_Heads"]
        },
        "Pancreas": {
            "typical_ptv_range": (40, 150),
            "typical_fractions": [25, 15],
            "oar_list": ["Duodenum", "Stomach", "Kidneys"]
        },
        "Lung": {
            "typical_ptv_range": (50, 300),
            "typical_fractions": [30, 15, 5],
            "oar_list": ["Lungs", "Heart", "Esophagus", "Spinal_Cord"]
        }
    }

config = QAConfig()

# -------------------------
# Input Validation
# -------------------------
class ValidationResult:
    """Result of validation with status and message"""
    def __init__(self, is_valid: bool, message: str, severity: str = "info"):
        self.is_valid = is_valid
        self.message = message
        self.severity = severity  # "info", "warning", "error"

def validate_plan_data(data: Dict[str, Any]) -> ValidationResult:
    """
    Validate radiation therapy plan data.

    Args:
        data: Dictionary containing plan parameters

    Returns:
        ValidationResult object with validation status and message
    """
    # Patient ID validation
    if not data.get("patient_id") or not str(data.get("patient_id")).strip():
        return ValidationResult(False, "Patient ID is required", "error")

    # PTV volume validation
    ptv = data.get("ptv_volume_cc", 0)
    try:
        ptv = float(ptv)
    except (ValueError, TypeError):
        return ValidationResult(False, "PTV volume must be a valid number", "error")

    if ptv <= config.PTV_VOLUME_RANGE[0] or ptv > config.PTV_VOLUME_RANGE[1]:
        return ValidationResult(
            False,
            f"PTV volume {ptv:.1f} cc is out of valid range ({config.PTV_VOLUME_RANGE[0]}-{config.PTV_VOLUME_RANGE[1]} cc)",
            "error"
        )

    # Number of fractions validation
    nf = data.get("num_fractions", 0)
    try:
        nf = int(nf)
    except (ValueError, TypeError):
        return ValidationResult(False, "Number of fractions must be a valid integer", "error")

    if nf < config.FRACTIONS_RANGE[0] or nf > config.FRACTIONS_RANGE[1]:
        return ValidationResult(
            False,
            f"Number of fractions {nf} is out of valid range ({config.FRACTIONS_RANGE[0]}-{config.FRACTIONS_RANGE[1]})",
            "error"
        )

    # Site-specific warnings
    site = data.get("site", "")
    if site in config.SITE_CONSTRAINTS:
        site_config = config.SITE_CONSTRAINTS[site]
        typical_range = site_config["typical_ptv_range"]

        if ptv < typical_range[0] or ptv > typical_range[1]:
            return ValidationResult(
                True,
                f"PTV volume {ptv:.1f} cc is outside typical range for {site} ({typical_range[0]}-{typical_range[1]} cc)",
                "warning"
            )

    # Machine validation
    machine = data.get("machine", "")
    if machine not in config.APPROVED_MACHINES and "Unknown" not in machine:
        return ValidationResult(
            True,
            f"Machine '{machine}' is not in approved list. Please verify.",
            "warning"
        )

    # Dose grid validation
    grid = data.get("dose_grid_size", "")
    if grid not in config.APPROVED_GRID_SIZES:
        return ValidationResult(
            True,
            f"Dose grid size '{grid}' is non-standard. Approved: {', '.join(config.APPROVED_GRID_SIZES)}",
            "warning"
        )

    return ValidationResult(True, "All validations passed", "info")

# -------------------------
# Enhanced Memory Manager
# -------------------------
class MemoryManager:
    """Thread-safe memory manager with enhanced features"""

    def __init__(self, memory_file: str = None):
        """
        Initialize memory manager.

        Args:
            memory_file: Path to JSON file for persistent storage
        """
        self.memory_file = memory_file or config.MEMORY_FILE
        self._lock = Lock()
        self.memory = self.load_memory()
        logger.info(f"MemoryManager initialized with {len(self.memory)} cases")

    def load_memory(self) -> List[Dict[str, Any]]:
        """Load memory from file or create demo data"""
        if os.path.exists(self.memory_file):
            try:
                with open(self.memory_file, "r") as f:
                    data = json.load(f)
                    logger.info(f"Loaded {len(data)} cases from {self.memory_file}")
                    return data
            except json.JSONDecodeError as e:
                logger.error(f"Failed to load memory file: {e}")
                # Try to load backup
                backup_file = f"{self.memory_file}.backup"
                if os.path.exists(backup_file):
                    logger.info(f"Attempting to load from backup: {backup_file}")
                    with open(backup_file, "r") as f:
                        return json.load(f)

        # Create demo data
        logger.info("Creating demo memory data")
        demo = [
            {
                "timestamp": "2025-01-01T10:00:00",
                "data": {
                    "patient_id": "P001",
                    "site": "Prostate",
                    "ptv_volume_cc": 150.5,
                    "num_fractions": 39,
                    "dose_grid_size": "2.5 mm",
                    "machine": "Varian TrueBeam",
                    "oar_constraints": {"Rectum_V70Gy": "<10%", "Bladder_V70Gy": "<15%"}
                },
                "results": {
                    "contour_result": "Contour OK",
                    "parameter_result": "Params OK",
                    "dose_result": "Dose OK"
                }
            },
            {
                "timestamp": "2025-01-02T11:30:00",
                "data": {
                    "patient_id": "P002",
                    "site": "Prostate",
                    "ptv_volume_cc": 120.0,
                    "num_fractions": 39,
                    "dose_grid_size": "3.0 mm",
                    "machine": "Varian TrueBeam",
                    "oar_constraints": {"Rectum_V70Gy": "<10%", "Bladder_V70Gy": "<15%"}
                },
                "results": {
                    "contour_result": "Minor issues",
                    "parameter_result": "Params OK",
                    "dose_result": "Dose OK"
                }
            },
            {
                "timestamp": "2025-01-03T14:15:00",
                "data": {
                    "patient_id": "P003",
                    "site": "Pancreas",
                    "ptv_volume_cc": 80.0,
                    "num_fractions": 25,
                    "dose_grid_size": "2.5 mm",
                    "machine": "Unknown",
                    "oar_constraints": {"Duodenum_Vx": "<5%"}
                },
                "results": {
                    "contour_result": "Warning",
                    "parameter_result": "Non-standard fx",
                    "dose_result": "Dose borderline"
                }
            }
        ]
        self.save_memory(demo)
        return demo

    def save_memory(self, data: List[Dict[str, Any]] = None):
        """
        Save memory with atomic write and backup.

        Args:
            data: Data to save (uses self.memory if None)
        """
        if data is None:
            data = self.memory

        # Create backup if file exists
        if os.path.exists(self.memory_file):
            backup_file = f"{self.memory_file}.backup"
            try:
                shutil.copy2(self.memory_file, backup_file)
                logger.debug(f"Created backup: {backup_file}")
            except Exception as e:
                logger.warning(f"Failed to create backup: {e}")

        # Atomic write using temp file
        try:
            dir_path = os.path.dirname(self.memory_file) or "."
            with tempfile.NamedTemporaryFile('w', delete=False, dir=dir_path, suffix='.tmp') as tf:
                json.dump(data, tf, indent=2)
                temp_name = tf.name

            shutil.move(temp_name, self.memory_file)
            logger.info(f"Saved {len(data)} cases to {self.memory_file}")

        except Exception as e:
            if 'temp_name' in locals() and os.path.exists(temp_name):
                os.remove(temp_name)
            logger.error(f"Failed to save memory: {e}")
            raise IOError(f"Failed to save memory: {e}")

    def add_case(self, structured_data: Dict[str, Any], results: Dict[str, Any]):
        """
        Add a case to memory (thread-safe).

        Args:
            structured_data: Patient and plan data
            results: QA results
        """
        with self._lock:
            entry = {
                "timestamp": datetime.now().isoformat(),
                "data": structured_data,
                "results": results
            }
            self.memory.append(entry)
            self.save_memory()
            logger.info(f"Added case {structured_data.get('patient_id')} to memory")

    def extract_features(self, data: Dict[str, Any]) -> np.ndarray:
        """
        Extract normalized features for similarity calculation.

        Args:
            data: Patient and plan data

        Returns:
            Numpy array of features
        """
        features = []

        # Numerical features (normalized)
        ptv = data.get("ptv_volume_cc", 0)
        features.append(ptv / 500.0)  # Normalize by typical max

        nf = data.get("num_fractions", 0)
        features.append(nf / 50.0)  # Normalize by typical max

        # Site (one-hot encoded)
        site = data.get("site", "Other")
        for known_site in config.KNOWN_SITES:
            features.append(1.0 if site == known_site else 0.0)

        # Machine (one-hot encoded)
        machine = data.get("machine", "Unknown")
        for approved_machine in config.APPROVED_MACHINES:
            features.append(1.0 if machine == approved_machine else 0.0)

        # Dose grid (one-hot encoded)
        grid = data.get("dose_grid_size", "")
        for approved_grid in config.APPROVED_GRID_SIZES:
            features.append(1.0 if grid == approved_grid else 0.0)

        return np.array(features)

    def retrieve_similar(self, structured_data: Dict[str, Any], top_k: int = 3) -> List[Dict[str, Any]]:
        """
        Retrieve similar cases using enhanced multi-feature similarity.

        Args:
            structured_data: Query case data
            top_k: Number of similar cases to retrieve

        Returns:
            List of similar cases with similarity scores
        """
        with self._lock:
            if not self.memory:
                logger.warning("Memory is empty, no similar cases to retrieve")
                return []

            try:
                q = self.extract_features(structured_data).reshape(1, -1)
                X = np.array([self.extract_features(m["data"]) for m in self.memory])

                sims = cosine_similarity(q, X)[0]
                idx = np.argsort(sims)[::-1][:top_k]

                similar = [{"similarity": float(sims[i]), **self.memory[i]} for i in idx]
                logger.info(f"Retrieved {len(similar)} similar cases (top similarity: {similar[0]['similarity']:.3f})")
                return similar

            except Exception as e:
                logger.error(f"Failed to retrieve similar cases: {e}")
                return []

    def export_to_csv(self, output_file: str = None) -> str:
        """
        Export memory to CSV file.

        Args:
            output_file: Output filename (auto-generated if None)

        Returns:
            Path to exported file
        """
        import csv

        if output_file is None:
            output_file = f"qa_memory_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

        with self._lock:
            if not self.memory:
                logger.warning("Memory is empty, nothing to export")
                return ""

            with open(output_file, 'w', newline='') as csvfile:
                # Get all possible fields
                fields = set(["timestamp"])
                for entry in self.memory:
                    fields.update(entry.get("data", {}).keys())
                    fields.update(entry.get("results", {}).keys())

                writer = csv.DictWriter(csvfile, fieldnames=sorted(fields))
                writer.writeheader()

                for entry in self.memory:
                    row = {
                        "timestamp": entry.get("timestamp", ""),
                        **entry.get("data", {}),
                        **entry.get("results", {})
                    }
                    # Convert dict/list values to strings for CSV
                    for key, value in row.items():
                        if isinstance(value, (dict, list)):
                            row[key] = json.dumps(value)
                    writer.writerow(row)

            logger.info(f"Exported {len(self.memory)} cases to {output_file}")
            return output_file

# -------------------------
# LLM Simulator (Enhanced)
# -------------------------
def call_llm_simulator(task: str, structured_json: Dict[str, Any],
                       memory_context: List[Dict[str, Any]] = None) -> str:
    """
    Simulate LLM-based QA checks.

    Args:
        task: Type of check to perform
        structured_json: Plan data
        memory_context: Similar cases for context

    Returns:
        Check result as string
    """
    mem_note = ""
    if memory_context:
        mem_note = " [Memory: " + ", ".join(
            f"{m['data'].get('patient_id', '?')} (sim={m['similarity']:.2f})"
            for m in memory_context[:3]
        ) + "]"

    try:
        if "contour" in task.lower():
            ptv = structured_json.get('ptv_volume_cc', 'N/A')
            site = structured_json.get('site', 'Unknown')
            result = f"Contour Check: {site} PTV {ptv} cc. No gross errors detected."

        elif "parameter" in task.lower():
            nf = structured_json.get("num_fractions", 0)
            grid = structured_json.get("dose_grid_size", "")
            machine = structured_json.get("machine", "")

            comments = []
            if nf in config.STANDARD_FRACTIONS:
                comments.append(f"Fractions: {nf} (standard)")
            else:
                comments.append(f"Fractions: {nf} (non-standard, verify)")

            if grid in config.APPROVED_GRID_SIZES:
                comments.append(f"Dose grid {grid} acceptable.")
            else:
                comments.append(f"Dose grid {grid} — review needed.")

            if machine in config.APPROVED_MACHINES:
                comments.append(f"Machine {machine} OK.")
            else:
                comments.append(f"Machine {machine} needs verification.")

            result = "Parameter Check: " + " ".join(comments)

        elif "dose" in task.lower():
            oar = structured_json.get("oar_constraints", {})
            if oar:
                result = f"Dose Check: OAR constraints {oar}. Review constraints against protocol."
            else:
                result = "Dose Check: No OAR constraints provided. Review required."

        elif "report" in task.lower():
            result = (
                f"FINAL QA REPORT\n"
                f"Contour: {structured_json.get('contour_result', 'N/A')}\n"
                f"Parameters: {structured_json.get('parameter_result', 'N/A')}\n"
                f"Dose: {structured_json.get('dose_result', 'N/A')}"
            )
        else:
            result = "LLM: no action."

        return result + mem_note

    except Exception as e:
        logger.error(f"LLM simulator error in {task}: {e}")
        return f"Error in {task}: {str(e)}"

# -------------------------
# Workflow
# -------------------------
def run_workflow(structured: Dict[str, Any], memory_mgr: MemoryManager,
                 top_k: int = 5) -> Dict[str, Any]:
    """
    Run the QA workflow.

    Args:
        structured: Plan data
        memory_mgr: Memory manager instance
        top_k: Number of similar cases to retrieve

    Returns:
        Dictionary with results and similar cases
    """
    try:
        logger.info(f"Running workflow for patient {structured.get('patient_id')}")

        # Validate input
        validation = validate_plan_data(structured)

        # Retrieve similar cases
        similar = memory_mgr.retrieve_similar(structured, top_k=top_k)

        # Run checks
        contour_res = call_llm_simulator("contour check", structured, similar)
        parameter_res = call_llm_simulator("parameter check", structured, similar)
        dose_res = call_llm_simulator("dose check", structured, similar)

        combined = {
            "contour_result": contour_res,
            "parameter_result": parameter_res,
            "dose_result": dose_res
        }

        final_report = call_llm_simulator("report", combined, similar)

        # Add validation message to report
        if not validation.is_valid:
            final_report = f"⚠ VALIDATION ERROR: {validation.message}\n\n" + final_report
        elif validation.severity == "warning":
            final_report = f"⚠ WARNING: {validation.message}\n\n" + final_report

        logger.info(f"Workflow completed for patient {structured.get('patient_id')}")

        return {
            **combined,
            "final_report": final_report,
            "similar": similar,
            "validation": {
                "is_valid": validation.is_valid,
                "message": validation.message,
                "severity": validation.severity
            }
        }

    except Exception as e:
        logger.error(f"Workflow error: {e}", exc_info=True)
        return {
            "contour_result": f"Error: {str(e)}",
            "parameter_result": "",
            "dose_result": "",
            "final_report": f"ERROR: Workflow failed - {str(e)}",
            "similar": [],
            "validation": {
                "is_valid": False,
                "message": str(e),
                "severity": "error"
            }
        }

# -------------------------
# Dash App
# -------------------------
memory = MemoryManager()
app = dash.Dash(__name__)
server = app.server

def memory_to_df(mem_list: List[Dict[str, Any]]) -> pd.DataFrame:
    """Convert memory list to DataFrame"""
    rows = []
    for i, m in enumerate(mem_list):
        d = m.get("data", {})
        rows.append({
            "idx": i,
            "timestamp": m.get("timestamp", "N/A")[:16],  # Truncate timestamp
            "patient_id": d.get("patient_id"),
            "site": d.get("site"),
            "ptv_volume_cc": d.get("ptv_volume_cc"),
            "num_fractions": d.get("num_fractions"),
            "dose_grid_size": d.get("dose_grid_size"),
            "machine": d.get("machine")
        })
    return pd.DataFrame(rows)

# -------------------------
# Layout
# -------------------------
app.layout = html.Div([
    html.H2("Memory-Enabled Contour QA Dashboard (Enhanced)"),
    html.P("Improved version with validation, logging, and enhanced similarity matching",
           style={"fontStyle": "italic", "color": "#666"}),

    html.Div([
        # Input Panel
        html.Div([
            html.H4("Enter New Plan"),
            html.Div(id="validation_message", style={"color": "red", "fontWeight": "bold", "marginBottom": "10px"}),

            html.Label("Patient ID *"),
            dcc.Input(id="patient_id", value="Q001", type="text", style={"width": "100%"}),

            html.Br(), html.Label("Site *"),
            dcc.Dropdown(
                id="site",
                options=[{"label": s, "value": s} for s in config.KNOWN_SITES],
                value="Prostate",
                clearable=False
            ),

            html.Br(), html.Label("PTV Volume (cc) *"),
            dcc.Input(id="ptv_volume_cc", value=150.5, type="number", min=0.1, max=2000, style={"width": "100%"}),

            html.Br(), html.Label("Number of Fractions *"),
            dcc.Input(id="num_fractions", value=39, type="number", min=1, max=100, style={"width": "100%"}),

            html.Br(), html.Label("Dose Grid Size *"),
            dcc.Dropdown(
                id="dose_grid_size",
                options=[{"label": g, "value": g} for g in config.APPROVED_GRID_SIZES],
                value="2.5 mm",
                clearable=False
            ),

            html.Br(), html.Label("Machine *"),
            dcc.Dropdown(
                id="machine",
                options=[{"label": m, "value": m} for m in config.APPROVED_MACHINES + ["Unknown", "Other"]],
                value="Varian TrueBeam",
                clearable=False
            ),

            html.Br(), html.Label("OAR Constraints (JSON)"),
            dcc.Textarea(
                id="oar_constraints",
                value='{"Rectum_V70Gy":"<10%","Bladder_V70Gy":"<15%"}',
                style={"width": "100%", "height": "80px"}
            ),

            html.Br(),
            html.Button("Run QA Workflow", id="run_workflow_btn", n_clicks=0,
                       style={"marginRight": "10px", "padding": "10px 20px", "fontSize": "14px"}),
            html.Button("Add to Memory", id="add_memory_btn", n_clicks=0,
                       style={"marginRight": "10px", "padding": "10px 20px", "fontSize": "14px"}),
            html.Button("Clear Form", id="clear_btn", n_clicks=0,
                       style={"padding": "10px 20px", "fontSize": "14px"}),

            html.Br(), html.Br(),
            html.Button("Export Memory to CSV", id="export_btn", n_clicks=0,
                       style={"padding": "10px 20px", "fontSize": "14px"}),
            html.Div(id="export_message", style={"marginTop": "10px", "color": "green"})

        ], style={
            "width": "38%",
            "display": "inline-block",
            "verticalAlign": "top",
            "padding": "15px",
            "border": "1px solid #ddd",
            "borderRadius": "5px",
            "backgroundColor": "#f9f9f9"
        }),

        # Results Panel
        html.Div([
            html.H4("Results"),
            dcc.Loading(
                id="loading",
                type="default",
                children=html.Div(
                    id="final_report_div",
                    style={
                        "whiteSpace": "pre-wrap",
                        "border": "1px solid #eee",
                        "padding": "15px",
                        "minHeight": "150px",
                        "backgroundColor": "#fff",
                        "borderRadius": "5px"
                    }
                )
            ),

            html.Hr(),
            html.H5("Similar Cases"),
            dash_table.DataTable(
                id="similar_table",
                columns=[
                    {"name": c, "id": c}
                    for c in ["patient_id", "site", "ptv_volume_cc", "num_fractions", "similarity"]
                ],
                page_size=5,
                style_table={"overflowX": "auto"},
                style_cell={'textAlign': 'left', 'padding': '8px'},
                style_header={'backgroundColor': '#f0f0f0', 'fontWeight': 'bold'}
            ),

            html.Br(),
            dcc.Graph(id="similarity_bar")

        ], style={
            "width": "58%",
            "display": "inline-block",
            "padding": "15px",
            "verticalAlign": "top"
        })
    ]),

    html.Hr(),
    html.H4("Memory Database"),
    html.Div(id="memory_table_div"),
    dcc.Interval(id="refresh_interval", interval=10*1000, n_intervals=0)
])

# -------------------------
# Callbacks
# -------------------------
@app.callback(
    Output("final_report_div", "children"),
    Output("similar_table", "data"),
    Output("similarity_bar", "figure"),
    Output("validation_message", "children"),
    Input("run_workflow_btn", "n_clicks"),
    State("patient_id", "value"),
    State("site", "value"),
    State("ptv_volume_cc", "value"),
    State("num_fractions", "value"),
    State("dose_grid_size", "value"),
    State("machine", "value"),
    State("oar_constraints", "value"),
    prevent_initial_call=True
)
def on_run_workflow(nc, pid, site, ptv_volume_cc, num_fractions, dose_grid_size, machine, oar_constraints):
    """Run QA workflow callback"""
    try:
        # Parse OAR constraints
        try:
            oar = json.loads(oar_constraints) if oar_constraints else {}
        except json.JSONDecodeError as e:
            error_msg = f"ERROR: Invalid JSON in OAR constraints: {str(e)}"
            logger.error(error_msg)
            return error_msg, [], px.bar(title="Error"), error_msg

        # Build structured data
        structured = {
            "patient_id": str(pid).strip() if pid else "",
            "site": site,
            "ptv_volume_cc": float(ptv_volume_cc) if ptv_volume_cc else 0,
            "num_fractions": int(num_fractions) if num_fractions else 0,
            "dose_grid_size": dose_grid_size,
            "machine": machine,
            "oar_constraints": oar
        }

        # Run workflow
        res = run_workflow(structured, memory, top_k=config.TOP_K_SIMILAR)

        # Prepare similar cases table
        similar_rows = []
        for s in res.get("similar", []):
            similar_rows.append({
                "patient_id": s["data"]["patient_id"],
                "site": s["data"]["site"],
                "ptv_volume_cc": s["data"]["ptv_volume_cc"],
                "num_fractions": s["data"]["num_fractions"],
                "similarity": round(s["similarity"], 3)
            })

        # Create similarity chart
        if similar_rows:
            fig = px.bar(
                pd.DataFrame(similar_rows),
                x="patient_id",
                y="similarity",
                title="Similarity to Memory Cases",
                color="similarity",
                color_continuous_scale="Viridis"
            )
            fig.update_layout(yaxis_range=[0, 1])
        else:
            fig = px.bar(title="No memory cases available")

        # Format report
        report_text = (
            res["final_report"] + "\n\n" +
            "---- Detailed Checks ----\n" +
            res["contour_result"] + "\n\n" +
            res["parameter_result"] + "\n\n" +
            res["dose_result"]
        )

        # Save workflow result
        try:
            with open("last_workflow_result.json", "w") as f:
                json.dump({"structured": structured, "results": res}, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save workflow result: {e}")

        # Validation message
        val_msg = ""
        if not res["validation"]["is_valid"]:
            val_msg = f"❌ {res['validation']['message']}"
        elif res["validation"]["severity"] == "warning":
            val_msg = f"⚠ {res['validation']['message']}"

        return report_text, similar_rows, fig, val_msg

    except Exception as e:
        error_msg = f"ERROR: {str(e)}"
        logger.error(f"Callback error: {e}", exc_info=True)
        return error_msg, [], px.bar(title="Error"), error_msg


@app.callback(
    Output("memory_table_div", "children"),
    Input("add_memory_btn", "n_clicks"),
    Input("refresh_interval", "n_intervals"),
    prevent_initial_call=False
)
def refresh_memory(add_nclicks, n_intervals):
    """Refresh memory table callback"""
    # Add to memory if button was clicked
    if ctx.triggered_id == "add_memory_btn" and os.path.exists("last_workflow_result.json"):
        try:
            with open("last_workflow_result.json", "r") as f:
                obj = json.load(f)

            # Validate before adding
            validation = validate_plan_data(obj["structured"])
            if validation.is_valid:
                memory.add_case(
                    obj["structured"],
                    {
                        "contour_result": obj["results"]["contour_result"],
                        "parameter_result": obj["results"]["parameter_result"],
                        "dose_result": obj["results"]["dose_result"]
                    }
                )
                logger.info(f"Case {obj['structured']['patient_id']} added to memory via UI")
            else:
                logger.warning(f"Cannot add invalid case to memory: {validation.message}")

        except Exception as e:
            logger.error(f"Failed to add to memory: {e}", exc_info=True)

    # Render memory table
    df = memory_to_df(memory.memory)
    if df.empty:
        return html.Div("Memory is empty.", style={"padding": "10px"})

    return html.Div([
        dash_table.DataTable(
            data=df.to_dict("records"),
            columns=[{"name": c, "id": c} for c in df.columns],
            page_size=10,
            style_table={"overflowX": "auto"},
            style_cell={'textAlign': 'left', 'padding': '8px'},
            style_header={'backgroundColor': '#f0f0f0', 'fontWeight': 'bold'},
            id="mem_table"
        ),
        html.Br(),
        html.Div(f"Total cases in memory: {len(df)}", style={"fontWeight": "bold"})
    ])


@app.callback(
    Output("patient_id", "value"),
    Output("ptv_volume_cc", "value"),
    Output("num_fractions", "value"),
    Output("oar_constraints", "value"),
    Input("clear_btn", "n_clicks"),
    prevent_initial_call=True
)
def clear_form(n_clicks):
    """Clear form callback"""
    return "", None, None, "{}"


@app.callback(
    Output("export_message", "children"),
    Input("export_btn", "n_clicks"),
    prevent_initial_call=True
)
def export_memory(n_clicks):
    """Export memory to CSV callback"""
    try:
        filename = memory.export_to_csv()
        if filename:
            return f"✓ Exported to {filename}"
        else:
            return "⚠ Memory is empty, nothing to export"
    except Exception as e:
        logger.error(f"Export failed: {e}")
        return f"❌ Export failed: {str(e)}"


# -------------------------
# Run Server
# -------------------------
if __name__ == "__main__":
    logger.info("Starting QA Dashboard...")
    app.run(debug=True, host='0.0.0.0', port=8050)

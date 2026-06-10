from __future__ import annotations

import io
import json
import tempfile
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_file
from werkzeug.utils import secure_filename

from generate_litematic import generate_litematic_file, load_groups, build_schematic
from midi_to_json import convert


BASE_DIR = Path(__file__).resolve().parent
ALLOWED_EXTENSIONS = {".mid", ".midi"}

app = Flask(__name__, static_folder="static", static_url_path="/static")
app.config["MAX_CONTENT_LENGTH"] = 32 * 1024 * 1024


def midi_stem(filename: str) -> str:
    """Return a safe filename stem for generated outputs."""
    stem = Path(secure_filename(filename)).stem.strip()
    return stem or "song"


@app.get("/")
def index():
    return render_template("index.html")


@app.post("/convert-json")
def convert_json():
    """Upload MIDI -> return JSON groups + summary for the visual preview."""
    upload = request.files.get("file")
    if upload is None or not upload.filename:
        return jsonify({"error": "No MIDI file uploaded."}), 400

    suffix = Path(upload.filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        return jsonify({"error": "Upload a .mid or .midi file."}), 400

    stem = midi_stem(upload.filename)

    # Tie-breaking when an onset lands exactly on a half-tick boundary.
    # Defaults to rounding up (matches the CLI default). The form sends
    # "round_half_up" as "true"/"false"; anything other than "false" rounds up.
    round_half_up = request.form.get("round_half_up", "true").lower() != "false"
    disable_octave_limit = request.form.get("disable_octave_limit", "false").lower() == "true"
    disable_ticking_limit = request.form.get("disable_ticking_limit", "false").lower() == "true"

    with tempfile.TemporaryDirectory(prefix="midi_litematic_") as temp_dir_name:
        temp_dir = Path(temp_dir_name)
        midi_path = temp_dir / f"{stem}{suffix}"
        upload.save(midi_path)

        groups, summary = convert(
            str(midi_path),
            tpr=1,
            round_half_up=round_half_up,
            disable_octave_limit=disable_octave_limit,
            disable_ticking_limit=disable_ticking_limit,
        )

    return jsonify({
        "stem": stem,
        "groups": groups,
        "summary": summary,
    })


@app.post("/download-litematic")
def download_litematic():
    """Accept JSON groups -> generate and return .litematic."""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "No JSON data provided."}), 400

    groups = data.get("groups")
    stem = data.get("stem", "song")
    if not groups or not isinstance(groups, list):
        return jsonify({"error": "Invalid groups data."}), 400

    try:
        description = (
            "Simple note-block layout generated from grouped JSON. "
            "Uses a north-facing repeater spine with an observer-over-note-block start input."
        )
        schematic = build_schematic(groups, stem, "Codex Web UI", description)

        with tempfile.TemporaryDirectory(prefix="midi_litematic_") as temp_dir_name:
            temp_dir = Path(temp_dir_name)
            litematic_path = temp_dir / f"{stem}.litematic"
            schematic.save(str(litematic_path))

            file_data = io.BytesIO(litematic_path.read_bytes())
            file_data.seek(0)

            return send_file(
                file_data,
                as_attachment=True,
                download_name=f"{stem}.litematic",
                mimetype="application/octet-stream",
            )
    except Exception as e:
        return jsonify({"error": f"Failed to generate litematic: {str(e)}"}), 500


@app.post("/convert")
def convert_midi():
    """Legacy endpoint: Upload MIDI -> download .litematic directly."""
    upload = request.files.get("file")
    if upload is None or not upload.filename:
        return jsonify({"error": "No MIDI file uploaded."}), 400

    suffix = Path(upload.filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        return jsonify({"error": "Upload a .mid or .midi file."}), 400

    stem = midi_stem(upload.filename)

    with tempfile.TemporaryDirectory(prefix="midi_litematic_") as temp_dir_name:
        temp_dir = Path(temp_dir_name)
        midi_path = temp_dir / f"{stem}{suffix}"
        json_path = temp_dir / f"{stem}.json"
        litematic_path = temp_dir / f"{stem}.litematic"

        upload.save(midi_path)

        groups, _summary = convert(str(midi_path), tpr=1, round_half_up=True)
        json_path.write_text(json.dumps(groups, indent=2), encoding="utf-8")

        generate_litematic_file(
            json_path,
            litematic_path,
            name=stem,
            author="Codex Web UI",
        )

        data = io.BytesIO(litematic_path.read_bytes())
        data.seek(0)

        return send_file(
            data,
            as_attachment=True,
            download_name=f"{stem}.litematic",
            mimetype="application/octet-stream",
        )


if __name__ == "__main__":
    app.run(debug=True)

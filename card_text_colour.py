"""Experimental per-pass colour changes. Never edits the shared Wallet database."""
from __future__ import annotations
import hashlib
import json
import re
import uuid
from pathlib import Path
from apply_card_skin import read_file, write_file, invalidate_cache

COLOURS = {"black": "rgb(0, 0, 0)", "white": "rgb(255, 255, 255)"}
KEYS = ("foregroundColor", "labelColor")

def decode_pass(payload):
    value = json.loads(payload)
    if not isinstance(value, dict) or not all(isinstance(value.get(k), str) for k in ("passTypeIdentifier", "serialNumber")):
        raise ValueError("Unrecognized pass metadata; no colour change was made.")
    return value

def recolour(payload, colour, original=None):
    current = decode_pass(payload)
    updated = dict(current)
    if colour == "restore":
        saved = decode_pass(original)
        if any(current[k] != saved[k] for k in ("passTypeIdentifier", "serialNumber")):
            raise ValueError("Backup belongs to a different pass.")
        for key in KEYS:
            if key in saved:
                updated[key] = saved[key]
            else:
                updated.pop(key, None)
    else:
        if colour not in COLOURS:
            raise ValueError("Choose black, white, or restore.")
        # Fail closed for payment formats which do not expose standard PassKit colours.
        if not any(key in current for key in KEYS):
            raise ValueError("This pass does not expose standard text colours. Database-based colours are unsupported.")
        for key in KEYS:
            updated[key] = COLOURS[colour]
    return json.dumps(updated, ensure_ascii=False, separators=(",", ":")).encode()

def apply_colour(udid, card_id, colour, backup_root=None):
    if not re.fullmatch(r"[A-Za-z0-9_+=-]{1,128}", card_id):
        raise ValueError("Invalid card identifier.")
    if colour not in (*COLOURS, "restore"):
        raise ValueError("Invalid colour.")
    root = backup_root or Path.home() / "Library/Application Support/AirCard/TextColourBackups"
    folder = root / hashlib.sha256(udid.encode()).hexdigest() / card_id
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    original = folder / "original.json"
    if colour == "restore" and not original.is_file():
        raise ValueError("No original colour backup exists for this card.")
    snapshot = folder / ("snapshot-" + uuid.uuid4().hex + ".json")
    target = f"/var/mobile/Library/Passes/Cards/{card_id}.pkpass"
    payload = read_file(udid, target, "pass.json", backup_path=snapshot)
    if payload is None:
        raise RuntimeError("Could not read and restore pass metadata. No colour update was attempted.")
    new_payload = recolour(payload, colour, original.read_bytes() if colour == "restore" else None)
    if not original.exists():
        with original.open("xb") as handle:
            import os
            os.chmod(original, 0o600)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    if not write_file(udid, target, "pass.json", new_payload):
        if not write_file(udid, target, "pass.json", payload):
            raise RuntimeError("Update and rollback failed. Keep the backup and recover the pass before retrying.")
        raise RuntimeError("Colour update failed; original metadata restored.")
    cache_ok = invalidate_cache(udid, card_id)
    return {"ok": True, "cache_ok": cache_ok, "message": "Metadata updated. Force-close Wallet and reopen to check the colour. iOS may retain its database colour."}

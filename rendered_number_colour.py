"""Glyph-only number colour patch for a checksummed Wallet render cache."""
from __future__ import annotations
import copy
import hashlib
import json
import os
import plistlib
import re
import subprocess
import tempfile
import uuid
from pathlib import Path
from apply_card_skin import read_file, write_file

ROOT = Path(__file__).resolve().parent
HELPER = ROOT / 'bin/render_number_colour' if (ROOT / 'bin/render_number_colour').exists() else ROOT / 'render_number_colour'


def patch_cache(payload, suffix, render=None):
    if len(payload) < 56 or len(payload) > 16*1024*1024 or not payload[48:].startswith(b'bplist00'):
        raise ValueError('Unsupported render cache format.')
    if hashlib.sha256(payload[48:]).digest() != payload[16:48]:
        raise ValueError('Render cache checksum failed.')
    archive = plistlib.loads(payload[48:])
    before = copy.deepcopy(archive)
    objects = archive['$objects']
    root = objects[archive['$top']['root'].data]
    if objects[root['$class'].data].get('$classname') != 'PKPassFrontFaceImageSet':
        raise ValueError('Unsupported render cache class.')
    face = objects[root['faceImage'].data]
    data_object = objects[face['imageData'].data]
    old_png = data_object['NS.data']
    if not isinstance(old_png, bytes) or not old_png.startswith(b'\x89PNG\r\n\x1a\n'):
        raise ValueError('Cache face is not a supported PNG.')
    if render is None:
        with tempfile.TemporaryDirectory(prefix='aircard-number-render-') as temporary:
            folder = Path(temporary); source = folder/'source.png'; output = folder/'black.png'
            source.write_bytes(old_png)
            run = subprocess.run([str(HELPER), str(source), str(output), suffix], capture_output=True, text=True, timeout=30)
            if run.returncode != 0 or not output.is_file():
                raise RuntimeError(run.stderr.strip() or 'Could not isolate the number. No cache change was made.')
            result = json.loads(run.stdout)
            if not result.get('ok'):
                raise RuntimeError('Renderer failed validation.')
            new_png = output.read_bytes()
    else:
        new_png = render(old_png, suffix)
    if not isinstance(new_png, bytes) or not new_png.startswith(b'\x89PNG\r\n\x1a\n'):
        raise ValueError('Renderer returned invalid PNG.')
    data_object['NS.data'] = new_png
    expected = copy.deepcopy(before)
    expected['$objects'][face['imageData'].data]['NS.data'] = new_png
    if archive != expected:
        raise RuntimeError('Unexpected cache metadata change.')
    encoded = plistlib.dumps(archive, fmt=plistlib.FMT_BINARY, sort_keys=False)
    return payload[:16] + hashlib.sha256(encoded).digest() + encoded


def save_exclusive(path, payload):
    with path.open('xb') as handle:
        os.chmod(path, 0o600); handle.write(payload); handle.flush(); os.fsync(handle.fileno())


def apply_number_black(udid, card_id, action='black'):
    if not re.fullmatch(r'[A-Za-z0-9_+=-]{1,128}', card_id) or action not in ('black','restore'):
        raise ValueError('Invalid card or action.')
    device_key = hashlib.sha256(udid.encode()).hexdigest()
    folder = Path.home()/'Library/Application Support/AirCard/NumberRenderBackups'/device_key/card_id
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    original, last = folder/'original.cache', folder/'last-patched.cache'
    # Match this exact device and card; never derive or change a card number.
    pass_backup = Path.home()/'Library/Application Support/AirCard/TextColourBackups'/device_key/card_id/'original.json'
    if not pass_backup.is_file():
        pass_backup.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        metadata_bytes = read_file(udid, f'/var/mobile/Library/Passes/Cards/{card_id}.pkpass', 'pass.json', backup_path=pass_backup, retries=1)
        if not metadata_bytes:
            raise ValueError('Could not safely back up this card metadata.')
    metadata = json.loads(pass_backup.read_bytes())
    suffix = metadata.get('primaryAccountSuffix')
    if not isinstance(suffix,str) or not re.fullmatch(r'\d{4}',suffix):
        raise ValueError('Unsupported card-number suffix.')
    target = f'/var/mobile/Library/Passes/Cards/{card_id}.cache'
    snapshot = folder/('snapshot-'+uuid.uuid4().hex+'.cache')
    current = read_file(udid,target,'FrontFace',backup_path=snapshot,retries=1)
    if not current:
        raise RuntimeError('Card render cache is unavailable. Open this card in Wallet once, close Wallet, then retry.')
    if action == 'restore':
        if not original.is_file() or not last.is_file() or current != last.read_bytes():
            raise RuntimeError('Cache no longer matches this patch; restore refused to preserve newer artwork.')
        modified = original.read_bytes()
    else:
        if last.is_file() and current == last.read_bytes():
            return {'ok':True,'message':'The cached number is already black. Reopen Wallet to check.'}
        modified = patch_cache(current,suffix)
        if not original.exists(): save_exclusive(original,current)
        # New cache after artwork refresh becomes the new reversible preimage.
        elif last.is_file() and current != last.read_bytes():
            save_exclusive(folder/('prior-original-'+uuid.uuid4().hex+'.cache'),original.read_bytes())
            original.write_bytes(current)
    if not write_file(udid,target,'FrontFace',modified):
        restored = write_file(udid,target,'FrontFace',current)
        raise RuntimeError('Cache write failed. '+('Previous render restored.' if restored else 'Restore failed; local backup retained.'))
    try:
        verify = read_file(udid,target,'FrontFace',backup_path=folder/('verify-'+uuid.uuid4().hex+'.cache'),retries=1)
        if verify != modified:
            raise RuntimeError('Cache readback did not match.')
    except Exception as error:
        if not write_file(udid,target,'FrontFace',current):
            raise RuntimeError('Readback failed and rollback failed. Local cache backup retained.') from error
        raise
    if action == 'black':
        last.write_bytes(modified); os.chmod(last,0o600)
    return {'ok':True,'message':'Number render '+('restored' if action=='restore' else 'changed to black')+' and readback verified. Reopen Wallet. The colour may reset if iOS regenerates this cache.'}

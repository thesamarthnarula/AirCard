import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import card_text_colour as colour
P = {"passTypeIdentifier": "pass.example", "serialNumber": "one", "foregroundColor": "rgb(255, 255, 255)", "paymentPass": {"primaryAccountIdentifier": "unchanged"}, "unknown": [1, 2]}
class ColourTests(unittest.TestCase):
    def test_recolour_preserves_other_fields(self):
        result = json.loads(colour.recolour(json.dumps(P).encode(), "black"))
        self.assertEqual(result["foregroundColor"], "rgb(0, 0, 0)")
        self.assertEqual(result["labelColor"], "rgb(0, 0, 0)")
        for key in ("paymentPass", "serialNumber", "unknown"):
            self.assertEqual(result[key], P[key])
    def test_restore_only_colours(self):
        modified = dict(P, labelColor="rgb(0, 0, 0)", unknown=[3])
        result = json.loads(colour.recolour(json.dumps(modified).encode(), "restore", json.dumps(P).encode()))
        self.assertNotIn("labelColor", result)
        self.assertEqual(result["unknown"], [3])
    def test_unsupported_and_wrong_identity_fail(self):
        unsupported = dict(P); unsupported.pop("foregroundColor")
        with self.assertRaises(ValueError): colour.recolour(json.dumps(unsupported).encode(), "black")
        with self.assertRaises(ValueError): colour.recolour(json.dumps(P).encode(), "restore", json.dumps(dict(P, serialNumber="other")).encode())
    def test_failed_update_rolls_back(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(colour, "read_file", return_value=json.dumps(P).encode()), patch.object(colour, "write_file", side_effect=[False, True]) as write, patch.object(colour, "invalidate_cache") as cache:
                with self.assertRaisesRegex(RuntimeError, "original metadata restored"): colour.apply_colour("device", "card", "black", Path(folder))
                self.assertEqual(write.call_count, 2)
                self.assertEqual(write.call_args.args[-1], json.dumps(P).encode())
                cache.assert_not_called()
    def test_invalid_id_never_reads(self):
        with patch.object(colour, "read_file") as read:
            with self.assertRaises(ValueError): colour.apply_colour("device", "../../other", "black")
            read.assert_not_called()

class ReaderRecoveryTests(unittest.TestCase):
    def test_failed_original_restore_keeps_recovered(self):
        import apply_card_skin as reader
        commands = []
        def native(command, udid, *args):
            commands.append(command)
            if command == 'afc-read': Path(args[1]).write_bytes(b'original')
            return {'exitCode': 0, 'targetGatePassed': True, 'operation': {'ok': True}}
        with tempfile.TemporaryDirectory() as folder:
            backup = Path(folder) / 'backup.json'
            with patch.object(reader, 'native', side_effect=native), patch.object(reader, 'run_json', return_value={'exitCode': 0, 'ok': True}), patch.object(reader, 'write_file', return_value=False):
                with self.assertRaisesRegex(RuntimeError, 'restoration failed'): reader.read_file('device', '/var/tmp', 'pass.json', backup_path=backup)
            self.assertEqual(backup.read_bytes(), b'original')
            self.assertNotIn('finish-write', commands)

class CardIdentifierTests(unittest.TestCase):
    def test_wallet_base64_identifier_is_supported(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(colour, "read_file", return_value=None) as read:
                with self.assertRaisesRegex(RuntimeError, "Could not read"):
                    colour.apply_colour("device", "IsSaQsjP-GfAgY=", "black", Path(folder))
                read.assert_called_once()

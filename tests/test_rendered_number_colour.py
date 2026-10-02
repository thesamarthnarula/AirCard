import hashlib
import plistlib
import unittest
import rendered_number_colour as r

PNG = b'\x89PNG\r\n\x1a\noriginal'
NEW = b'\x89PNG\r\n\x1a\nmodified'
def fixture():
    objects = ['$null', {'faceImage':plistlib.UID(2),'faceShadowImage':plistlib.UID(4),'$class':plistlib.UID(6),'version':31}, {'imageData':plistlib.UID(3),'scale':3.0}, {'NS.data':PNG}, {'imageData':plistlib.UID(5)}, {'NS.data':b'shadow unchanged'}, {'$classname':'PKPassFrontFaceImageSet','$classes':['PKPassFrontFaceImageSet','NSObject']}]
    archive={'$version':100000,'$archiver':'NSKeyedArchiver','$top':{'root':plistlib.UID(1)},'$objects':objects}
    data=plistlib.dumps(archive,fmt=plistlib.FMT_BINARY,sort_keys=False)
    return b'header metadata!'+hashlib.sha256(data).digest()+data

class CacheTests(unittest.TestCase):
    def test_only_image_changes_and_checksum_updates(self):
        old=fixture();result=r.patch_cache(old,'1234',lambda png,suffix:NEW)
        original=plistlib.loads(old[48:]);modified=plistlib.loads(result[48:])
        self.assertEqual(modified['$objects'][3]['NS.data'],NEW)
        modified['$objects'][3]['NS.data']=PNG
        self.assertEqual(modified,original)
        self.assertEqual(result[:16],old[:16])
        self.assertEqual(hashlib.sha256(result[48:]).digest(),result[16:48])
    def test_bad_checksum_refused(self):
        old=bytearray(fixture());old[20]^=1
        with self.assertRaisesRegex(ValueError,'checksum'):r.patch_cache(bytes(old),'1234',lambda png,suffix:NEW)
    def test_wrong_cache_format_refused(self):
        with self.assertRaises(ValueError):r.patch_cache(b'not cache','1234')
    def test_renderer_failure_propagates(self):
        def bad(*args):raise RuntimeError('number mismatch')
        with self.assertRaisesRegex(RuntimeError,'number mismatch'):r.patch_cache(fixture(),'1234',bad)
    def test_invalid_renderer_output_refused(self):
        with self.assertRaisesRegex(ValueError,'invalid PNG'):r.patch_cache(fixture(),'1234',lambda *args:b'bad')

import tempfile
import json
from pathlib import Path
from unittest.mock import patch

class TransportTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.home=Path(self.temp.name)
        self.device='test-device';self.card='synthetic-card='
        self.device_key=hashlib.sha256(self.device.encode()).hexdigest()
        metadata=self.home/'Library/Application Support/AirCard/TextColourBackups'/self.device_key/self.card/'original.json'
        metadata.parent.mkdir(parents=True);metadata.write_text(json.dumps({'primaryAccountSuffix':'1234'}))
        self.current=fixture();self.modified=r.patch_cache(self.current,'1234',lambda *args:NEW)
        self.home_patch=patch.object(Path,'home',return_value=self.home);self.home_patch.start()
    def tearDown(self):self.home_patch.stop();self.temp.cleanup()
    def test_writes_only_frontface_and_verifies(self):
        with patch.object(r,'read_file',side_effect=[self.current,self.modified]) as read, patch.object(r,'patch_cache',return_value=self.modified), patch.object(r,'write_file',return_value=True) as write:
            result=r.apply_number_black(self.device,self.card)
            self.assertTrue(result['ok']);self.assertEqual(write.call_count,1)
            self.assertEqual(write.call_args.args[2],'FrontFace');self.assertTrue(write.call_args.args[1].endswith('.cache'))
            self.assertEqual(read.call_count,2)
    def test_failed_readback_rolls_back(self):
        with patch.object(r,'read_file',side_effect=[self.current,b'wrong']), patch.object(r,'patch_cache',return_value=self.modified), patch.object(r,'write_file',return_value=True) as write:
            with self.assertRaisesRegex(RuntimeError,'readback'):r.apply_number_black(self.device,self.card)
            self.assertEqual(write.call_count,2);self.assertEqual(write.call_args.args[-1],self.current)
    def test_failed_write_restores_preimage(self):
        with patch.object(r,'read_file',return_value=self.current), patch.object(r,'patch_cache',return_value=self.modified), patch.object(r,'write_file',side_effect=[False,True]) as write:
            with self.assertRaisesRegex(RuntimeError,'Previous render restored'):r.apply_number_black(self.device,self.card)
            self.assertEqual(write.call_args.args[-1],self.current)
    def test_restore_refuses_newer_artwork(self):
        with patch.object(r,'read_file',return_value=self.current),patch.object(r,'write_file') as write:
            with self.assertRaisesRegex(RuntimeError,'newer artwork'):r.apply_number_black(self.device,self.card,'restore')
            write.assert_not_called()
    def test_mismatch_does_not_write(self):
        with patch.object(r,'read_file',return_value=self.current),patch.object(r,'patch_cache',side_effect=RuntimeError('suffix mismatch')),patch.object(r,'write_file') as write:
            with self.assertRaisesRegex(RuntimeError,'suffix mismatch'):r.apply_number_black(self.device,self.card)
            write.assert_not_called()

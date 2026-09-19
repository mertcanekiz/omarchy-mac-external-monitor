#!/usr/bin/env python3
"""Non-root tests of boot-file copy guards; only temporary files are touched."""
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('stage', Path(__file__).with_name('stage-usb4-gpu-test.py'))
stage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stage)

class CopyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='usb4-stage-test-')
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.source, self.target = self.base / 'source', self.base / 'target'
        self.source.write_bytes(b'new test data')
        self.expected = hashlib.sha256(b'new test data').hexdigest()
        sync = patch.object(stage.os, 'sync')
        sync.start()
        self.addCleanup(sync.stop)

    def test_copy_is_verified_and_idempotent(self):
        stage.copy_file(self.source, self.target, self.expected)
        stage.copy_file(self.source, self.target, self.expected)
        self.assertEqual(stage.digest(self.target), self.expected)

    def test_mismatch_never_touches_target(self):
        with self.assertRaises(RuntimeError):
            stage.copy_file(self.source, self.target, '0' * 64)
        self.assertFalse(self.target.exists())

    def test_existing_content_requires_explicit_replace(self):
        self.target.write_bytes(b'old test data')
        with self.assertRaises(RuntimeError):
            stage.copy_file(self.source, self.target, self.expected)
        self.assertEqual(self.target.read_bytes(), b'old test data')
        stage.copy_file(self.source, self.target, self.expected, replace=True)
        self.assertEqual(stage.digest(self.target), self.expected)

    def test_symlink_is_never_overwritten(self):
        self.target.symlink_to(self.source)
        with self.assertRaises(RuntimeError):
            stage.copy_file(self.source, self.target, self.expected, replace=True)
        self.assertTrue(self.target.is_symlink())

    def test_existing_staging_file_is_never_overwritten(self):
        tmp = self.target.with_name(self.target.name + '.usb4-gpu-staging')
        tmp.write_bytes(b'other work')
        with self.assertRaises(FileExistsError):
            stage.copy_file(self.source, self.target, self.expected)
        self.assertEqual(tmp.read_bytes(), b'other work')
        self.assertFalse(self.target.exists())

if __name__ == '__main__':
    unittest.main()

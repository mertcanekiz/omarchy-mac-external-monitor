#!/usr/bin/env python3
"""Ensure a timed-out display command cannot be replayed by buffered close."""
import errno
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    'run_dpin', Path(__file__).with_name('run-dpin-test.py'))
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class RequestOnceTests(unittest.TestCase):
    def exercise(self, result=None, error=None):
        with patch.object(runner.os, 'open', return_value=123) as opened, \
             patch.object(runner.os, 'write', return_value=result, side_effect=error) as write, \
             patch.object(runner.os, 'close') as close:
            if error is not None or result != 1:
                with self.assertRaises(OSError):
                    runner.request_once('/mock/control')
            else:
                runner.request_once('/mock/control')
            opened.assert_called_once()
            write.assert_called_once_with(123, b'1')
            close.assert_called_once_with(123)

    def test_success(self):
        self.exercise(result=1)

    def test_timeout(self):
        self.exercise(error=OSError(errno.ETIMEDOUT, 'Connection timed out'))

    def test_short_write(self):
        self.exercise(result=0)


if __name__ == '__main__':
    unittest.main()

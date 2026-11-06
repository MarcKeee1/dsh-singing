"""Launch the local NetEase QR login window without loading singing models."""
import pathlib
import runpy
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'python'))
runpy.run_module('netease_login', run_name='__main__')

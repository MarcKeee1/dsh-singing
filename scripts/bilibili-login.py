"""Open a local login window; use the backend virtual environment's Python."""
import pathlib,runpy,sys
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'python'))
runpy.run_module('bili_login',run_name='__main__')

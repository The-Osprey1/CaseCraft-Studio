"""Keep every test away from the real per-user folders (%APPDATA%, %LOCALAPPDATA%): saved
'My devices' presets or logs on the developer's machine must not change test results."""
import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="casecraft-tests-")
os.environ.setdefault("CASECRAFT_DATA_DIR", os.path.join(_tmp, "data"))
os.environ.setdefault("CASECRAFT_LOG_DIR", os.path.join(_tmp, "logs"))
os.environ.pop("CASECRAFT_TOKEN", None)

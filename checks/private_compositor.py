"""Auxiliar de QA: publica o endereço do barramento privado e inicia KWin virtual."""
import json
import os
from pathlib import Path
import sys

if __name__=='__main__':
    Path(os.environ['XDG_RUNTIME_DIR'],'private-bus.json').write_text(json.dumps({'DBUS_SESSION_BUS_ADDRESS':os.environ['DBUS_SESSION_BUS_ADDRESS']}))
    os.execvp('kwin_wayland',['kwin_wayland',*sys.argv[1:]])

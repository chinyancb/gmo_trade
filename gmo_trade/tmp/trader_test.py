import os
import sys
from pathlib import Path
import re

app_home = str(Path(__file__).parents[1])
sys.path.append(app_home)
import mylib.macdtradutil
mtu = mylib.macdtradutil.MacdTradUltil()
mtu.test_trader()

import os
import sys
from pathlib import Path
import re

app_home = str(Path(__file__).parents[1])
sys.path.append(app_home)
import mylib.macdtradutil
mtu = mylib.macdtradutil.MacdTradUltil()
filename = mtu._get_file_name(path='/Users/chinyancb/Documents/workspace/pj/gmo/gmo_coin_v0.2/gmo_trade/gmo_trade/var/share/sysc/') 
if re.search('^hist_', filename):
    hist_manual = int(filename.split('_')[-1])
    print(hist_manual)
    print(type(hist_manual))

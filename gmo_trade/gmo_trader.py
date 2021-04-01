import logging
from pathlib import Path
import  mylib.tradutil as tu

#------------------------------
# アプリケーションのパスを指定
#------------------------------
APP_HOME = str(Path(__file__).parents[0])

# ロギング設定
LOG_CONF = APP_HOME + '/etc/conf/logging.conf'
logging.config.fileConfig(LOG_CONF)
log = logging.getLogger('main')

def main():
    log.info(f'----- start -----')
    trd = tu.TradUltil()
    trd.scrap_macd_stoch()




if __name__ == '__main__':
    main()

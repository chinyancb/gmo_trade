import sys
import logging
import time
from pathlib import Path
import mylib.gmotradutil as gtu
from mylib.gmotradutil import ExchangStatusGetError, CloseRateGetError, MacdStochScrapGetError

#------------------------------
# アプリケーションのパスを指定
#------------------------------
APP_HOME = str(Path(__file__).parents[0])

# ロギング設定
LOG_CONF = APP_HOME + '/etc/conf/logging.conf'
logging.config.fileConfig(LOG_CONF)
log = logging.getLogger('scraping')

def main():
    log.info(f'----- start -----')
    while True:
        try:
            trd = gtu.GmoTradUtil()
            trd.set_logging('scraping')
            trd.scrap_macd_stoch()
        except MacdStochScrapGetError as e:
            log.critical(f'{e}')
            sys.exit(1)
        except Exception as e:
            log.error('f{e}')
            del (trd)
            trd.init_memb()
            trd = gtu.GmoTradUtil()
            trd.set_logging('scraping')
            time.sleep(10)
        continue




if __name__ == '__main__':
    main()

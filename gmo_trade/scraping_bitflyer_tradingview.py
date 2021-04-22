import sys
import logging
import time
from pathlib import Path
import mylib.gmotradutil as gtu
import mylib.lineutil as lu
from mylib.gmotradutil import  CloseMacdStochScrapGetError

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
            line = lu.LineUtil()
            trd = gtu.GmoTradUtil()
            trd.set_logging('scraping')
            #trd.scrap_macd_stoch_close(headless=False)
            trd.scrap_macd_stoch_close()
        except CloseMacdStochScrapGetError as e:
            log.critical(f'CloseMacdStochScrapGetError :[{e}]')
            trd.set_logging('scraping')
            line.send_line_notify(msg=f'\
                    スクレイピング処理に失敗しました。\
                    メンバーを初期化し、スクレイピングプロセスを停止します。\
                    エラー内容↓\
                    CloseMacdStochScrapGetError :[{e}]'
                    )
            trd.init_memb()
            sys.exit(1)
        except Exception as e:
            log.error(f'{e}')
            del (trd)
            trd = gtu.GmoTradUtil()
            trd.set_logging('scraping')
            trd.init_memb()
            time.sleep(10)
            continue
        except KeyboardInterrupt:
            log.info('KeyboardInterrupt stop')
            sys.exit(1)




if __name__ == '__main__':
    main()

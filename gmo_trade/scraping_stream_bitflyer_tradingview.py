import sys
import logging
import time
from pathlib import Path
import mylib.gmotradutil as gtu
import mylib.lineutil as lu
from mylib.gmotradutil import CloseMacdStochStreamScrapGetError

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
    line = lu.LineUtil()
    sleep_sec = 10
    while True:
        try:
            trd = gtu.GmoTradUtil()
            trd.set_logging('scraping')
            trd.scrap_macd_stoch_stream(sleep_sec=3)
        except CloseMacdStochStreamScrapGetError as e:
            log.critical(f'CloseMacdStochStreamScrapGetError :[{e}]')
            trd.set_logging('scraping')
            line.send_line_notify(msg=f'\
                    ストリーミングスクレイピングに失敗しました。\
                    {sleep_sec}秒後に再起動します。\
                    エラー内容↓\
                    CloseMacdStochStreamScrapGetError :[{e}]'\
                    )
            time.sleep(sleep_sec)
            continue
        except Exception as e:
            log.error(f'{e}')
            del (trd)
            trd = gtu.GmoTradUtil()
            trd.set_logging('scraping')
            line.send_line_notify(msg=f'\
                    ストリーミングスクレイピングに失敗しました。\
                    メンバを初期化し{sleep_sec}秒後に再起動します。\
                    エラー内容↓\
                    CloseMacdStochStreamScrapGetError :[{e}]'\
                    )
            trd.init_memb()
            time.sleep(sleep_sec)
            continue
        except KeyboardInterrupt:
            log.info('KeyboardInterrupt stop')
            sys.exit(1)




if __name__ == '__main__':
    main()

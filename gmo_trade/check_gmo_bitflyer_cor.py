import sys
import time
import logging
import logging.config
from pathlib import Path
import mylib.gmotradutil as gtu

#------------------------------
# アプリケーションのパスを指定
#------------------------------
APP_HOME = str(Path(__file__).parents[0])
sys.path.append(APP_HOME)

# ロギング設定
LOG_CONF = APP_HOME + '/etc/conf/logging.conf'
logging.config.fileConfig(LOG_CONF)
log = logging.getLogger('gmotradeUtil')

# GMOコインとビットフライヤーのトレンド相関チェック実行
def main():
    while True:
        try:
            obj = gtu.GmoTradUtil()
            obj.check_cor_gmo_bitflyer()
        except Exception as e:
            logging.critical(f'{e}')
            time.sleep(60)
        continue


if __name__ == '__main__':
    main()

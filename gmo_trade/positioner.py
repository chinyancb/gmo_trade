import sys
import logging
import logging.config
from pathlib import Path
import asyncio
import time
import mylib.gmotradutil as gtu
import mylib.lineutil as lu
from  mylib.gmotradutil import PosJudgementError

#------------------------------
# アプリケーションのパスを指定
#------------------------------
APP_HOME = str(Path(__file__).parents[0])
sys.path.append(APP_HOME)

# ロギング設定
LOG_CONF = APP_HOME + '/etc/conf/logging.conf'
logging.config.fileConfig(LOG_CONF)
log = logging.getLogger('position')


async def main():
    gmo = gtu.GmoTradUtil()
    gmo.set_logging('position')
    line = lu.LineUtil()
    while True:
        try:
            log.info('main start')
            await asyncio.gather(
                    gmo.positioner_stoch(),
                    gmo.positioner_macd(),
#                    gmo.positioner()
            )
        except PosJudgementError as e:
            gmo.make_file(path=gtu.SYSCONTROL, filename=gtu.STOP_NEW_TRADE)
            log.critical(f'PosJudgementError : [{e}]')
            line.send_line_notify(f'[CRITICAL]\
                    ポジション判定処理で障害が発生しました。\
                    新規ポジション及びポジショ判定処理を停止します。\
                    状況を確認してください。エラー内容↓\
                    PosJudgementError : [{e}]')
            sys.exit(1)
        except Exception as e:
            log.error(f'{e}')
            gmo.make_file(path=gtu.SYSCONTROL, filename=gtu.STOP_NEW_TRADE)
            line.send_line_notify(f'[ERROR]\
                    ポジション判定処理で障害が発生しました。\
                    新規ポジションを停止します。\
                    1時間後にポジション判定処理を再開します\
                    状況を確認してください。エラー内容↓\
                    [{e}]')
            del(gmo)
            gmo = gtu.GmoTradUtil()
            gmo.set_logging('position')
            time.sleep(6000)
            continue

asyncio.run(main())

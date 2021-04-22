import requests
import logging
import logging.config
import os
from pathlib import Path
import json


# エンドポイント
PUBLIC_ENDPOINT = 'https://api.bitflyer.com/v1/'

# アプリケーションのパス指定
app_home = str(Path(__file__).parents[1])

# ロギング設定
LOG_CONF = app_home + '/etc/conf/logging.conf'
logging.config.fileConfig(LOG_CONF)
log = logging.getLogger("bitfilyertradutil")

class BitfilyerTradUtil(object):

    def get_ticker(self, product_code='BTC_JPY'):
        """
        * bitflyerの最新レートを取得
        * param
            product_code:str (default 'BTC_JPY') 対象とする通貨
        * return
            dict型
                取得成功時
                    ltp:int 最終取引価格
                    stat:str 板の状態(https://lightning.bitflyer.com/docs?lang=ja#%E6%9D%BF%E3%81%AE%E7%8A%B6%E6%85%8B)
                取得失敗時
                    ltp:int -1
                    stat:str 'ERROR'
        """
        log.info(f'get_ticker() called')

        path = f'getticker?product_code={product_code}'
        url  = PUBLIC_ENDPOINT + path
        try:
            response = requests.get(url)
            response.raise_for_status
        except requests.exceptions.RequestException as e:
            log.critical(f"http status code error : [{e}]")
            return {'ltp':-1, 'stat': 'ERROR'}

        try:
            response_json = json.dumps(response.json())
        except Exception as e:
            log.error(f'response convert json failure : [{e}]')
            return {'ltp':-1, 'stat': 'ERROR'}

        ltp = int(json.loads(response_json)['ltp'])
        stat = json.loads(response_json)['state']

        return {'ltp':ltp, 'stat':stat}

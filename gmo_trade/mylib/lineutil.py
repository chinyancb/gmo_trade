import requests
import logging
import os
from pathlib import Path


# アプリケーションのパス指定
app_home = str(Path(__file__).parents[1])

# ロギング設定
LOG_CONF = app_home + '/etc/conf/logging.conf'
logging.config.fileConfig(LOG_CONF)
log = logging.getLogger("linenUtil")

class LineUtil(object):

    def __init__(self):

        self.line_notify_token = os.environ['LINE_TOKEN']
        self.line_notify_api = 'https://notify-api.line.me/api/notify'
        self.headers = {'Authorization': f'Bearer {self.line_notify_token}'}

    def send_line_notify(self, msg):
        """
        * LINEに通知する
        * param
            msg:str 通知するメッセージ
        * return
            True :bool 通知成功
            False:bool 通知失敗
        """
        data = {'message': f'{msg}'}


        # メッセージ送信
        try:
            response = requests.post(self.line_notify_api, headers = self.headers, data = data)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            log.error(f"http status code error :[{e}]")
            return False
        
        log.info('line message send done')
        return True

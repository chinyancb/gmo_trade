import requests
import logging
from logging import config

LOG_CONF = '/Users/chinyancb/Documents/workspace/pj/gmo/gmo_coin_v0.2/gmo_trade/gmo_trade/etc/conf/logging.conf'
config.fileConfig(LOG_CONF)
logging.getLogger("linenotify_util_log").setLevel(logging.DEBUG)

class LineUtil(object):

    def __init__(self):

        self.line_notify_token = 'uVcXpLU6J8C9Q1wfBN6SxBU1ZibX4VO4EajHCsEoU9a'
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
            logging.error(f"http status code error :[{e}]")
            return False
        
        logging.info('line message send done')
        return True

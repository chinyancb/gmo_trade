import os
import sys
import glob
import re
import logging
import logging.config
from pathlib import Path
import itertools
import requests
import websocket
import json
import hashlib
import hmac
import time
import datetime
import pytz
import dateutil.parser
import pandas as pd
import numpy as np
import random
import numexpr
import asyncio
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import chromedriver_binary
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from mylib.lineutil import LineUtil
from mylib.bitfilyertradutil import BitfilyerTradUtil
#from  mylib.websocketutil import WebSocketUtil

#------------------------------
# アプリケーションのパスを指定
#------------------------------
app_home = str(Path(__file__).parents[1])
sys.path.append(app_home)


#---------------------
# 定数
#---------------------
# PublicAPIエンドポイント 
PUBLIC_ENDPOINT = 'https://api.coin.z.com/public'

# WebSocketAPIエンドポイント
WEBSOCKET_ENDPOINT = 'wss://api.coin.z.com/ws/public/v1'


# データ出力先パス
CLOSE_RATE_FILE_PATH     = app_home + '/var/share/close/'        # closeレート情報
MACD_FILE_PATH           = app_home + '/var/share/macd/'         # MACD1分CLOSE値(ニアリーイコール)
MACD_STREAM_FILE_PATH    = app_home + '/var/share/macd_stream/'  # MACD1秒
STOCH_FILE_PATH          = app_home + '/var/share/stoch/'        # ストキャスティクス1分CLOSE(ニアリーイコール)
STOCH_STREAM_FILE_PATH   = app_home + '/var/share/stoch_stream/' # ストキャスティクス1秒値
POSITION_FILE_PATH       = app_home + '/var/share/pos/'          # ポジション判定結果
POSITION_MACD_FILE_PATH  = app_home + '/var/share/pos/macd/'     # MACDによるポジション判定結果
POSITION_STOCH_FILE_PATH = app_home + '/var/share/pos/stoch/'    # ストキャスティクスよるポジション判定結果
SYSCONTROL               = app_home + '/var/share/sysc/'         # システムコントロール用


# システムコントロール用ファイル名
INIT_POSITION  = 'init_positioner' # ポジションを初期化する(main_pos=STAYに設定する)
STOP_NEW_TRADE = 'stop_new_trade'     # 新規エントリーを停止する


# JST 変換用定数
JST = datetime.timezone(datetime.timedelta(hours=+9), 'JST') 



# 自作の例外class
class ExchangStatusGetError(Exception):
    """
    * 取引所のステータスが確認できない
    """
    pass

class CloseRateGetError(Exception):
    """
    * closeレートを取得できない
    """
    pass

class CloseMacdStochScrapGetError(Exception):
    """
    * tradingviewからスクレイピングでMACD,ストキャスティクス関連情報を取得できない
    """
    pass

class PosJudgementError(Exception):
    """
    * ポジション判定でのエラー
    """
    pass



class GmoTradUtil(object):

    def __init__(self): 

        # データ関連
        self.ind_df           = pd.DataFrame()  # レート,MACD,ストキャスティクスデータ格納用
        self.close_rate_df    = pd.DataFrame()  # closeレート格納用
        self.bitf_rate_df     = pd.DataFrame()  # ビットフライヤーのレート情報
        self.macd_stream_df   = pd.DataFrame()  # macdリアルタイムデータ格納用
        self.stoch_stream_df  = pd.DataFrame()  # ストキャスティクスデータ格納用
        self.macd_df          = pd.DataFrame()  # macd確定値データ格納用
        self.stoch_df         = pd.DataFrame()  # ストキャスティクス確定値データ格納用
        self.pos_jdg_df       = pd.DataFrame([{'position':'STAY', 'jdg_timestamp':datetime.datetime.now()}])  # ポジション計算用データフレーム
        self.pos_macd_jdg_df  = pd.DataFrame([{'position':'STAY', 'jdg_timestamp':datetime.datetime.now()}])  # ポジション計算用データフレーム
        self.pos_stoch_jdg_df = pd.DataFrame([{'position':'STAY', 'jdg_timestamp':datetime.datetime.now()}])  # ポジション計算用データフレーム

        # ファイル関連
        self.close_filename        = f"close_{datetime.datetime.now().strftime('%Y-%m-%d-%H:%M')}"       # closeデータの書き出しファイル名
        self.bitf_rate_filename    = f"close_bitf{datetime.datetime.now().strftime('%Y-%m-%d-%H:%M')}"       # closeデータの書き出しファイル名
        self.macd_filename         = f"macd_{datetime.datetime.now().strftime('%Y-%m-%d-%H:%M')}"        # macdデータの書き出しファイル名
        self.macd_stream_filename  = f"macd_stream{datetime.datetime.now().strftime('%Y-%m-%d-%H:%M')}"  # macd1秒データの書き出しファイル名
        self.stoch_filename        = f"stoch_{datetime.datetime.now().strftime('%Y-%m-%d-%H:%M')}"       # ストキャスティクスデータの書き出しファイル名
        self.stoch_stream_filename = f"stoch_stream{datetime.datetime.now().strftime('%Y-%m-%d-%H:%M')}" # ストキャスティクス1秒データの書き出しファイル名
        self.pos_filename          = f"pos_{datetime.datetime.now().strftime('%Y-%m-%d-%H:%M')}"         # ポジションデータの書き出しファイル名
        self.pos_macd_filename     = f"pos_{datetime.datetime.now().strftime('%Y-%m-%d-%H:%M')}"         # macdによるポジションデータの書き出しファイル名
        self.pos_stoch_filename    = f"pos_{datetime.datetime.now().strftime('%Y-%m-%d-%H:%M')}"         # ストキャスティクスによるポジションデータの書き出しファイル名

        # フラグ関連
        self.is_div         = False                                       # ダイバージェンスが発生していればTrue,起きていなければFalse 

        # Line通知用
        self.line = LineUtil()


        self.set_logging() 
        
    def set_logging(self, qualname='gmotradeUtil'):
        """
        * self.loggingの設定を行う
        * param
            qualname:str (default 'gmotradeUtil') self.loging.confで設定した名前
        * return
            self.log:Logger 設定が成功するとself.logに設定されたロガーが格納される
        """
        # ロギング
        LOG_CONF = app_home + '/etc/conf/logging.conf'
        logging.config.fileConfig(LOG_CONF)
        self.log = logging.getLogger(qualname)
        return self.log

    def init_memb(self):
        """
        closeレートの取得やMACDの計算,その他例外が発生した場合,緊急対応として使用しているdataframe,その他メンバを初期化する
        return:
            True
        """
        self.log.info('init_memb() called')
        self.__init__()
        self.line.send_line_notify('メンバを初期化しました')
        self.log.info('init_memb() done')
        return True



    def init_position(self):
        """
        * メインポジション、サポートポジション共にSTAY(初期化)にする
        * param
            なし
        * return
            True :初期化成功
            False:初期化失敗
        """
        self.log.info(f'init_position() called')
        try:
            pos_jdg_tmp_df = pd.DataFrame([{'main_pos':'STAY','sup_pos':'STAY',
                'jdg_timestamp':datetime.datetime.now()}])  # ポジション計算用データフレーム
        except Exception as e:
            self.log.critical(f'ポジションの初期化に失敗しました : [{e}]')
            return False

        self.pos_jdg_df = pos_jdg_tmp_df.copy()
        del(pos_jdg_tmp_df)

        self.log.info(f'position data is init done.')
        return True


            
    def make_file(self, path, filename, mode='w'):
        """
        * 指定されたパス、ファイル名に従い空のファイルを作成する
        * param
            path:str     ファイルを作成するディレクトリのパス(末尾には/を付けて指定)
            filename:str 作成するファイル名
            mode:str(default w) 書き込むモード(デフォルトは上書き)
        * return
            True : ファイル作成成功
            False: ファイル作成失敗
        """
        self.log.info(f'make_file() called')
        self.log.info(f'emptiness : [{path + filename}]')
            
        # ディレクトリ存在チェック。無ければ作成
        tmp_dir_list  = path.split('/')
        tmp_dir = '/'.join([str(i) for i in tmp_dir_list[0:-1]])
        if os.path.isdir(tmp_dir) == False:
            os.makedirs(tmp_dir, exist_ok=True)
            self.log.info(f'maked dir : [{tmp_dir}]')

        # 空ファイル作成
        try:
            with open(path + filename, mode=mode):
                pass
        except Exception as e:
            self.log.error(f'cant make emptiness file. : [{e}]')
            return False

        self.log.info(f'emptiness file make done.[{path + filename}]')
        return True




    def rm_file(self, path, filename):
        """
        * 指定されたファイルを削除する
        * param
            path:str 削除対象のファイルが置かれているディレクトリパス(末尾には/を付けて指定)
            filename:str 削除するファイル名
        * return
            True:bool 削除成功
            False:bool削除失敗
            None:bool ファイルが存在しない or ディレクトリが存在しない
       """ 
        self.log.info(f'rm_file() called.')
        
        # ファイルが存在しない場合
        if self.is_exit_file(path, filename) == False:
            self.log.info(f'not found remove file : [{path + filename}]')
            return None

        try:
            os.remove(path + filename)
        except Exception as e:
            self.log.error(f'remove file failure : [{e}]')
            return False

        self.log.info(f'remove file done : [{path + filename}]')
        self.log.info(f'rm_file() done')
        return True




    def is_exit_file(self, path, filename):
        """
        * 指定されたファイルの存在確認を行う
        * param
            path:str ファイルが格納されているディレクトリパス
            filename:str : 存在確認するファイル名
        * return
            True :bool ファイルが存在する場合
            False:book ファイルが存在しない場合
        """
        self.log.info(f'is_exit_file() called')

        if os.path.exists(path + filename):
            self.log.info(f'file is exists. : [{path + filename}]')
            self.log.info(f'is_exit_file is done')

            return True

        self.log.info(f'file not found : [{path + filename}]')
        self.log.info(f'is_exit_file() done')

        return False



    def _get_file_name(self, path, prefix='hist'):
        """
        * 指定されたディレクトリパス,prefixに当てはまる最新のファイル名を取得
        * 主にポジション判定のヒストグラムの閾値変更のために使用する
        * param
            path:str 取得するファイルが置かれているディレクトリ名(末尾に/を付けて指定)
            prefix:srt 取得するファイル名のprefix(defalt 'hist')
        * return
            filename:str 取得したファイル名
            not_found_file:str ファイル名がない場合
            not_found_dir :str 指定したディレクトリが存在しない場合
            cant_get_file:srt ファイル名取得に失敗した場合
        """

        self.log.info(f'_get_file_name() called')

        # ディレクトリ存在チェック
        if os.path.exists(path) == False:
            self.log.info(f'not found dir : [{path}]')
            return 'not_found_dir'

        # prefixにあたるファイル名があるか確認
        if len(glob.glob(f'{path}{prefix}*')) == 0:
            self.log.info(f'not found file : [{path}{prefix}]')
            return 'not_found_file'

        # ファイル名取得
        try:
            files = glob.glob(f"{path}{prefix}*")
            filename = max(files, key=os.path.getctime)
        except OSError as e:
            self.log.critical(f'cant get file name : [{e}]')
            return 'cant_get_file'

        # ファイル名が絶対パスなのでファイル名単体にする
        filename = filename.split('/')[-1]
        self.log.info(f'get file : [{filename}]')    
        self.log.info(f'_get_file_name() done')

        return filename 



    def load_pos_df(self, head_nrow=1):
        """
        * posデータをロードすし、メンバ（self.pos_jdg_df）として登録する
        * param
            head_nrow:int 先頭から読み込む行数（デフォルト1行）
        * retrn
            True :ロードに成功
            False:ロードに失敗
            None :posデータファイルが無い場合
        """
        self.log.info(f'load_pos_df() called')

        # posファイルが無い場合
        if len(glob.glob(f'{POSITION_FILE_PATH}pos*')) == 0: 
            self.log.error(f'not found pos data file. under path : [{POSITION_FILE_PATH}]')
            return None

        try:
            files = glob.glob(f"{POSITION_FILE_PATH}pos*")
            latest_file = max(files, key=os.path.getctime)
        except OSError as e:
            self.log.critical(f'reload pos data error: [{e}]')
            return False

        # ポジションファイル読み込み
        try:
            latest_file = latest_file.split('/')[-1]
            self.log.info(f'load file : [{latest_file}]')
            pos_df = pd.read_csv(filepath_or_buffer=POSITION_FILE_PATH + latest_file, sep=',', header=0)
            self.log.info(f'csv file read done')
    
            # 先頭行を読み込み
            pos_df = pos_df.head(n=head_nrow).reset_index(level=0, drop=True)
            self.log.info(f'reset index done') 
    
            # 文字列からint、datetime型に変換
            pos_df['close_rate'] = pos_df['close_rate'].astype('int')
            self.log.info('close_rate dtype convert done.')
    
            # ポジション判定時刻の変換(そのまま読み込んで大丈夫）
            jdg_timestamp_list = []
            for i in range(0, head_nrow):
                jdg_timestamp_jst    = dateutil.parser.parse(pos_df['jdg_timestamp'][i]).astimezone(JST)
                jdg_timestamp_list.append(jdg_timestamp_jst)
            else:
                pos_df['jdg_timestamp'] = jdg_timestamp_list 
        except Exception as e:
            self.log.error(f'position data load failure : [{POSITION_FILE_PATH + latest_file}, {e}]')
            return False

        # 読み込んだファイルは時系列で降順となっているため昇順に変更
        pos_df = pos_df.sort_values(by ='jdg_timestamp', ascending=True).reset_index(level=0, drop=True)
        self.log.info('jdg_timestamp dtype convert done.')

        # メンバとしてコピー
        self.pos_jdg_df = pos_df.copy()
        del(pos_df)

        self.log.info(f'pos data load success.')
        return True 




    def _write_csv_dataframe(self, df, path, sep=',', header=True, index=False, mode='w'):
        """
        データフレームをcsvとして書き出す
        param
            df:DataFrame 書き出すデータフレームオブジェクト
            path:str     書き出し先のパス
            sep:str     出力時のセパレーター(default : ,)
            header:blool (defalut : True) Trueの場合はヘッダを書き出す
            mode:str     出力モード(default : w )
            index(default True):bool Trueの場合indexも書き出す(default : False) 
        return
            True   書き出し成功
            False  書き出し失敗
        """

        self.log.info('_write_csv_dataframe() called.')
        # ディレクトリ存在チェック。無ければ作成
        tmp_dir_list  = path.split('/')
        tmp_dir = '/'.join([str(i) for i in tmp_dir_list[0:-1]])
        if os.path.isdir(tmp_dir) == False:
            os.makedirs(tmp_dir, exist_ok=True)
            self.log.info(f'maked dir : [{tmp_dir}]')

        df_tmp = df.copy()
        try:
            if df_tmp.to_csv(path_or_buf=path, sep=sep, index=index, mode=mode, header=header) == None:
                self.log.info(f'write dataframe to csv done. : [{path}]')
                del(df_tmp)
                return True
        except Exception as e:
            self.log.error(f'_write_csv_dataframe() cancelled.')
            return False 



    def _read_csv_dataframe(self, path, filename=None, header=True, dtypes=None):
        """
        * csvファイルをデータフレームとして読み込む
        * param
            path:str csvファイル格納ディレクトリパス。末尾に「/」をつけること
            filename:str (defult None) 読み込むファイル名
                         ※ Noneの場合指定されたディレクトリパス配下の最新のファイルを読み込む
            header:bool (default True) 読み込むファイルにヘッダーがあるか
                   True:ヘッダーあり
                   False:ヘッダー無し
            dtype:dict (default None) カラムの型を指定したい場合は下記のように定義する
                  {'a': 'int', 'b': 'float', 'c': 'str', 'd': 'np.datetime[64]', 'e': 'datetime'}
                  ただし設定できる型は上記のみ
        * return
            load_df:dataframe
                    読み込み成功:csvデータを格納したデータフレーム
                    読み込み失敗:空のデータフレーム
        """
        self.log.info(f'_read_csv_dataframe() called')

        # ディレクトリ存在チェック
        if os.path.isdir(path) == False:
            self.log.error(f'not found path : [{path}]')
            return pd.DataFrame()
                    

        # ファイル特定
        if filename == None:
            try:
                files = glob.glob(f"{path}*")
                latest_file = max(files, key=os.path.getctime)
            except Exception as e:
                self.log.error(f'not found file : [{e}]')
                return pd.DataFrame()
        
        else:
            try:
                latest_file = f'{path + filename}'
                # ファイルの存在チェック
                if os.path.exists(latest_file) != True:
                    self.log.error(f'not found file : [{filename}]')
                    return pd.DataFrame()
            except Exception as e:
                self.log.error(f'not found file : [{e}]')
                return pd.DataFrame()

        # ファイル読み込み
        if header != True:
            load_df = pd.read_csv(filepath_or_buffer=latest_file, header=None)
        else:
            load_df = pd.read_csv(filepath_or_buffer=latest_file, header=0)
        self.log.info(f'load data frame done')


        # 型指定がある場合
        if dtypes != None:
            try:
                for col ,vtype in dtypes.items(): 
                    if vtype == 'int':
                        load_df[col] = load_df[col].astype('int')
                    elif vtype == 'float':
                        load_df[col] = load_df[col].astype('float')
                    elif vtype == 'str':
                        load_df[col] = load_df[col].astype('str')
                    elif vtype == 'np.datetime[64]':
                        load_df[col] = pd.to_datetime(load_df[col])
                    elif vtype == 'datetime':
                        for i in range(len(load_df)):
                            load_df[col][i] = pd.to_datetime(load_df[col][i]).to_pydatetime()
                    else:
                        self.log.error('invalid set of columns name or type')
                        return pd.DataFrame()
                else:
                    self.log.info(f'type convert done')
            except Exception as e:
                self.log.error(f'convert error : [{e}]')
                return pd.DataFrame()

        self.log.info(f'_read_csv_dataframe() done')
        return load_df
         


    def _get_exchg_status(self, retry_sleep_sec=3):
        """
        * 引取所ステータス確認
        * param 
             retry_sleep_sec :リトライ用のスリープ時間（秒）
        * return 
             ecchg_stat:str(OPEN:オープン, PREOPEN:プレオープン, MAINTENANCE:メンテナンス)
        * Exception : ExchangStatusGetError
        """
        
        self.log.info(f'_get_exchg_status() called')
        path = '/v1/status'
        url  = PUBLIC_ENDPOINT + path

        # カウンター
        err_htp_cnt = 0 # HTTPリクエスト失敗カウンター
        err_cnt     = 0 # データリクエスト失敗カウンター

        while True:
            try:
                response = requests.get(url)
                response.raise_for_status() # HTTPステータスコードが200番台以外であれば例外を発生させる
            except requests.exceptions.RequestException as e:
                self.log.critical(f"http status code error : [{e}]")
        
                # リトライ
                err_htp_cnt += 1
                if err_htp_cnt <= 10:
                    self.log.critical(f"http request error. exec retry: [{e}]")
                    time.sleep(retry_sleep_sec)
                    continue
                self.log.critical(f"http request error. process kill {e}")
                #sys.exit(1)
                raise ExchangStatusGetError(f'HTTPエラーにより取引所ステータスが取得できません')

            # jsonに変換
            exchg_status_js = json.dumps(response.json())

            # 取引所ステータス取得
            try:
                exchg_stat = json.loads(exchg_status_js)['data']['status']
            except Exception as e:
                self.log.error(f'不正なレスポンスです. : [{e}]')
                raise ExchangStatusGetError(exchg_stat)
            except ExchangStatusGetError as e:
                self.log.error(f"取引所ステータスを取得できませんでした:[{e}]")
            break

        self.log.info(f'_get_exchg_status() is done')
        return exchg_stat

    
    

    def _get_rate(self, symbol='BTC_JPY'):
        """
        * 現在のレートを取得する(リトライはしない)
        * param
            symbol:str (defult 'BTC_JPY') 通貨のタイプ
        * return
            last_rate:int 最新のレート(※レートの取得に失敗は-1を返す)
        """

        self.log.info(f'_get_rate() called')

        path = f'/v1/ticker?symbol={symbol}'
        url = PUBLIC_ENDPOINT + path
        try:
            response = requests.get(url)
            response.raise_for_status
        except requests.exceptions.RequestException as e:
            self.log.critical(f"http status code error : [{e}]")
            return -1

        try:
            response_json = json.dumps(response.json())
        except Exception as e:
            self.log.error(f'response convert json failure : [{e}]')
            return -1 

        # レスポンスのステータスが0以外であれば失敗
        if json.loads(response_json)['status'] != 0:
            self.log.error(f'respons status invalid : [{response_json}]')
            return -1

        last_rate = int(json.loads(response_json)['data'][0]['last'])
        if last_rate:
            self.log.info(f'_get_rate() done')
            return last_rate
        else:
            return -1





    def _get_close_info(self, cls_mt, symbol='BTC_JPY', page=1, count=100, retry_sleep_sec=3):
        
        """
        1分足のcloseのレートを取得
        """ 
        #---------------------------
        # CLOSEデータ取得
        #----------------------------

        self.log.info(f'_get_close_info() is called')
        # 取引所ステータス確認
        try:
            exchg_stat = self._get_exchg_status() 
            if exchg_stat != 'OPEN':
                time.sleep(retry_sleep_sec)
                self.log.info(f'取引所がOPENではありません。メンバを初期化します: [{exchg_stat}]')
                raise ExchangStatusGetError(exchg_stat)
        except ExchangStatusGetError as e:
            self.log.critical(f'取引所がOPENではありません。メンバを初期化します  : [{e}]')
            self.init_memb()
         
        path = f"/v1/trades?symbol={symbol}&page={page}&count={count}"
        url  = PUBLIC_ENDPOINT + path
        self.log.info(f"URL : [{url}]")

        # イテレーター
        err_htp_cnt = 0 # closeデータHTTPリクエスト失敗カウンター
        err_cnt     = 0 # closeデータリクエスト失敗カウンター
        
        while True:
            try:
                response = requests.get(url)
                response.raise_for_status() # HTTPステータスコードが200番台以外であれば例外を発生させる
            except requests.exceptions.RequestException as e:
                self.log.critical(f"{e}")
        
                # リトライ
                err_htp_cnt += 1
                if err_htp_cnt <= 10:
                    self.log.critical(f"http request error. exec retry : [{e}]")
                    time.sleep(retry_sleep_sec)
                    continue

                self.log.critical(f'HTTPエラーによりclose情報が取得できません. プロセスを終了します.  : [{e}]')
                #sys.exit(1)
                raise CloseRateGetError(f'HTTPエラーによりclose情報が取得できません')
        
        
            #closeのレートをjsonで取得
            rate_info_js = json.dumps(response.json())
        
            # ステータスコードが0以外であればリトライ
            if json.loads(rate_info_js)['status'] != 0:
                err_cnt += 1
                time.sleep(retry_sleep_sec)
                self.log.error(f"status code invalid : [{json.loads(rate_info_js)}]")
                continue

                # 3回失敗するとエラー判定
                if err_cnt == 3:
                    self.log.critical(f"不正なレスポンスです。プロセスを終了します : [{json.loads(rate_info_js)}]")
                    #sys.exit(1)
        
            # データの個数を取得
            itr = len(json.loads(rate_info_js)['data']['list'])
        
            # jsonをパース(データは時系列で降順で返却されているため新しい順にfor文が実行される
            for i in np.arange(itr):
                close_timestamp_tmp = json.loads(rate_info_js)['data']['list'][i]['timestamp']
                close_timestamp_jst = dateutil.parser.parse(close_timestamp_tmp).astimezone(JST)
                close_rate_tmp = int(json.loads(rate_info_js)['data']['list'][i]['price'])
            
                self.log.debug(f"cls_mt : [{cls_mt}] close_timestamp_jst.minute:[{close_timestamp_jst.minute}]")
                # 分が同じ場合
                if cls_mt == close_timestamp_jst.minute:
                    close_timestamp = close_timestamp_jst
                    close_rate      = close_rate_tmp
                    break
            else: 
                #!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
                # 100カウントで取得できない場合は現在時刻,レートは-1を返す(暫定対応)
                #!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
                self.log.warning(f'not found close rate in 100 length js.')
                close_timestamp = datetime.datetime.now() + datetime.timedelta(seconds=120)
                return {'close_timestamp' : close_timestamp, 'close_rate' : -1}        

            break # while文を抜ける
            #--------------- while文ここまで -----------------#
        self.log.info(f'_get_close_info() is done')
        return {'close_timestamp' : close_timestamp, 'close_rate' : close_rate}        
            

    def get_close_info(self, idle_sleep_sec=0.3, retry_sleep_sec=5):

        """
        1分足のclose情報を取得
        param
            idle_sleep_sec:int  59秒まで待つためのスリープタイム(秒)
            retry_sleep_sec:int リトライまでのスリープタイム（秒）
        return
            False:bool データの取得に失敗した場合は以下の例外を発生させる
            CloseRateGetError
        """

        #=================================================
        # 1分足のclose情報を取得(メイン処理)
        #=================================================

        self.log.info(f'get_close_info() called')

        while True:

            cls_tm = datetime.datetime.now()
            if cls_tm.second != 59:  
                time.sleep(idle_sleep_sec) # 正確に時刻を取得するためtime.sleepで確実にブロッキングさせる
                continue
            else:
                #----------------------------------------------------------------------------------------
                # 59秒になったら
                # 1秒以内にメイン処理が終わるため1.5秒のスリープを入れ分をまたがせる
                # asyncio.sleepでなくtime.sleepを使い他タスクが入ってこないように確実にブロッキングさせる
                #----------------------------------------------------------------------------------------
                time.sleep(1.5)

                # 1分前のcloseデータを取得
                self.log.debug(f"cls_tm : {cls_tm}")
                close_dict = self._get_close_info(cls_tm.minute)

                # 最新のcloseの時刻(分)を取得
                if len(self.close_rate_df) >= 1:
                    last_close_rate_minute = self.close_rate_df['close_timestamp'].tail(n=1)[self.close_rate_df.index.max()].minute

                    # close_rateが-1に場合はリトライ
                    if close_dict['close_rate'] == -1:
                        self.log.warning(f"not found close data : [{close_dict['close_rate']}]")
                        self.log.info(f'retry func[_get_close_info()]')
                        
                        for _ in np.arange(1, 10):
                            time.sleep(retry_sleep_sec)
                            close_dict = self._get_close_info(cls_tm.minute, page=_)
                            if ((last_close_rate_minute + 1) == close_dict['close_timestamp'].minute) and (close_dict['close_rate'] != -1):
                                self.log.info(f'retry is success')
                                break
                        else:
                            self.log.info(f'not found close data. raise exception')
                            raise CloseRateGetError(f'not found close data')
                            return False

                # たまたま初回にclose_rateが-1で最初からやり直し
                if close_dict['close_rate'] == -1:
                    self.log.error(f"error: cant get close data : [{close_dict['close_rate']}]")
                    continue

                # データフレームを作成
                close_timestamp = close_dict["close_timestamp"]
                close_rate      = close_dict["close_rate"]
                close_rate_tmp_df = pd.DataFrame([[close_timestamp, close_rate]], columns=["close_timestamp","close_rate"])
                
                # 時系列的には昇順で作成
                self.close_rate_df = pd.concat([self.close_rate_df, close_rate_tmp_df], ignore_index=True).sort_values(by="close_timestamp", axis=0)

                # 1分毎にcloseレートが取れているか確認
                self.log.info(f"'check self.close_rate_df'")
                for i in range(0, len(self.close_rate_df)):
                    if i == 0:
                        tmp_close_tm = self.close_rate_df['close_timestamp'][i].minute
                        continue

                    # 59分の場合のみの条件
                    if tmp_close_tm == 59 and self.close_rate_df['close_timestamp'][i].minute == 0:
                        tmp_close_tm = self.close_rate_df['close_timestamp'][i].minute
                        continue 
                    elif (tmp_close_tm + 1) !=  self.close_rate_df['close_timestamp'][i].minute:
                        self.log.error(f"'self.close_rate_df' is  invalid. メンバを初期化します:[{self.close_rate_df.query('index==@i')}]")
                        self.init_memb() 
                        break
                    else:
                        tmp_close_tm = self.close_rate_df['close_timestamp'][i].minute
                else:
                    self.log.info(f"'self.close_rate_df' is ok")

                # 1分毎にデータが取得できていない場合
                if len(self.close_rate_df) == 0:
                    del(close_rate_tmp_df)
                    continue

                del(close_rate_tmp_df)
                print(self.close_rate_df)
                
                # ファイル出力
                self._write_csv_dataframe(self.close_rate_df, path=CLOSE_RATE_FILE_PATH + self.close_filename) 

                # MACD計算
                self.macd_calculator()
                self.log.info('get_close_info() 1cycle done')
    


    def get_rate_info_app(self, symbol='BTC_JPY', end_point=WEBSOCKET_ENDPOINT):
        """
        * WebsocketAPIでレート情報を取得
        * param
            symbol:str 対象とする通貨(default BTC_JPY')
        *retrun
            True:データ取得成功
            False:データ取得失敗
        """
        cnt = 0
        websocket.enableTrace(True)
        ws = websocket.WebSocketApp(end_point)
        def on_open(self):
            message = {
                "command": "subscribe",
                "channel": "ticker",
                "symbol": f"{symbol}"
            }
            ws.send(json.dumps(message))
        
        def on_message(self, message):
            cnt += 1
            rate = int(json.loads(message)['last'])
            timestamp_str = json.loads(message)['timestamp']
            timestamp = dateutil.parser.parse(timestamp_str).astimezone(JST)
            tmp_df = pd.DataFrame.from_dict({'timestamp' : timestamp, 'rate' : rate}, orient='index').T
            print(timestamp.minute)
#            print(tmp_df)
#            self.tmp_close_rate_df = pd.concat([self.tmp_close_rate_df, tmp_df], ignore_index=True)

        def on_error(self, err):
            self.log.critical(f'websocket api failed : [{errr}]')

        ws.on_open = on_open
        ws.on_message = on_message
        ws.on_error = on_error
        ws.run_forever()        

    def mk_close_data(self, df):
        while True:
            print(self.tmp_close_rate_df)
            time.sleep(5)




    def scrap_macd_stoch_close(self, cycle_minute=15, sleep_sec=0.5, n_row=10, trv_time_lag=7):
        """
        * tradingviewの自作のチャートから15分足のopen,high,low,close, macd,ストキャスティクスの値を取得する
          →https://jp.tradingview.com/chart/wTJWkxIA/
           !!!ウォッチリスト表示の形式でチャートが保存されていることが前提
        * param
            cycle_minute:int (default 15) スクレイピングする間隔（分）※1時間の場合は60で設定
                         ただし1, 5, 15, 30, 60のみ設定可能
            sleep_sec:int (default 5) sleep秒 ※1秒以下推奨
            n_row:int (default 10) データを保持する行数。超えると古いものから削除される
            trv_time_lag:int (default 10) ビットフライヤーの値がtradingviewに反映されるまでラグが発生する場合がある
            　　　　　　　　　そのためチャートに反映されるまでスクレイピングしないよう停止(スリープ)させ
                              正しいインジケーターを取得させるようにする
        * return 
            なし
                データ取得成功 :self.ind_dfにデータ時系列で降順で格納される
                データ取得失敗 :下記例外を発生させる
                                CloseMacdStochScrapGetError
        """

        
        # 始値で1分以内に複数回ループすることを防ぐ
        open_rate_tmp = 0

        # スクレイピングサイクルを設定
        if cycle_minute == 1:
            interval_minute_list = np.arange(0, 60, 1)
        elif cycle_minute == 5:
            interval_minute_list = np.arange(0, 60, 5)
        elif cycle_minute == 15:
            interval_minute_list = np.arange(0, 60, 15)
        elif cycle_minute == 30:
            interval_minute_list = np.arange(0, 60, 30)
        elif cycle_minute == 60:
            interval_minute_list = np.array([0])
        else:
            raise CloseMacdStochScrapGetError(f'invalid argument cycle_minute')
            self.log.error('invalid argument cycle_minute')
            sys.exit(1)

        while True:
            self.log.info(f'scrap_macd_stoch_close() called cycle_minute:[{cycle_minute}]')

            # ブラウザ立ち上げ
            try:
                options = webdriver.ChromeOptions()
                options.add_argument('--headless')
                driver = webdriver.Chrome(options=options)
                driver.set_window_size(1200, 900)
                driver.get('https://jp.tradingview.com/chart/wTJWkxIA/')
                # jsが反映されるまで待機
                time.sleep(10)

                # マウスオーバー
                chart = driver.find_element_by_class_name('chart-gui-wrapper')
                actions = ActionChains(driver)
                actions.move_to_element(chart)
                actions.move_by_offset(310, 100)
                actions.perform()

            except Exception as e:
                self.log.critical(f'{e}')
                driver.quit()
                raise CloseMacdStochScrapGetError(f'browser set error :[{e}]')

            self.log.info(f'browser set up done')
            
            #----------------------------------------------------------------------------------
            # スクレイピングのサイクルとTradingviewの分足があっていなければ例外発生し停止させる
            #----------------------------------------------------------------------------------
            try:
                title_attr = driver.find_element_by_class_name('titleWrapper-2KhwsEwE').text
                title_minute = int(title_attr.split('\n')[1])
                if cycle_minute != title_minute:
                    raise CloseMacdStochScrapGetError(f'cycle_minute and tradingview minute not match')
                    self.log.critical(f'cycle_minute and tradingview minute not match')
                    sys.exit(1)
            except Exception as e:
                self.log.critical(f'{e}')
                driver.quit()
                raise CloseMacdStochScrapGetError(f'cycle_minute and tradingview minute not match')



            # スクレイピング
            while True:
                now_time = datetime.datetime.now()
                # tredingviewでcloseがチャートに反映にタイムラグが生じることを考慮し秒で調整する
                if now_time.minute in interval_minute_list and now_time.second == trv_time_lag:
                    break
                time.sleep(sleep_sec) 
                self.log.info(f'not scraping time')
                continue
            try:
                # CSSセレクタで指定のクラスでelementを取得
                ind_array = driver.find_elements_by_css_selector('.valuesWrapper-2KhwsEwE')
                get_time = datetime.datetime.now()
                self.log.info(f'got elements :[{ind_array}]')

                # レートの値を取得
                rate_str = ind_array[0].text
                self.log.debug(f'rate_str : [{rate_str}]')
                open_rate  = int(rate_str.split('始値')[1].split('高値')[0])
                high_rate  = int(rate_str.split('高値')[1].split('安値')[0])
                low_rate   = int(rate_str.split('安値')[1].split('終値')[0])
                close_rate_str = rate_str.split('終値')[1].split('終値')[0]
                close_rate = int(re.split('[+|−]', close_rate_str)[0])
                rate_array = [open_rate, high_rate, low_rate, close_rate] 

                # 同じ値だったらcontinue
                if open_rate_tmp == open_rate:
                    self.log.info('bitflyer open rate same value :[{open_rate}]')
                    driver.quit()
                    time.sleep(sleep_sec) 
                    continue
                open_rate_tmp = open_rate

                # MACDとストキャスティクスをリストに変換(MACDはマイナスが全角表記になっているためreplaceで置換しておく
                macd_array  = ind_array[1].text.replace('−', '-').split('\n')
                stoch_array = ind_array[2].text.split('\n')
                self.log.info(f'scraped to array : [macd {macd_array}, stoch {stoch_array}]')

                # 文字列を数値へ変換
                macd_array  = [int(data) for data in macd_array]
                stoch_array = [float(data) for data in stoch_array]
                self.log.info(f'converted numeric : [macd {macd_array}, stoch {stoch_array}]')

                # 取得時刻をリストに追加
                rate_array.append(get_time)
                macd_array.append(get_time)
                stoch_array.append(get_time)

                # numpyのndarrayに変換
                rate_array  = np.array(rate_array)
                macd_array  = np.array(macd_array) 
                stoch_array = np.array(stoch_array)

                #------------------------------------------------------------------------
                # tradingview側でHTMLの変更があった場合に備えて
                # 値に制限のある ストキャスティクスの値でスクレイピングの異常を検知する
                #------------------------------------------------------------------------
                if ((stoch_array[:2] < 0.00).any() == True) or ((stoch_array[:2] > 100.00).any() == True):
                    self.log.critical(f'sotch value invalid : [{stoch_array}]')
                    raise CloseMacdStochScrapGetError(f'sotch value invalid : [{stoch_array}]')
            except Exception as e:
                self.log.critical(f'cant get macd stoch data : [{e}]')
                driver.quit()
                self.init_memb()
                raise CloseMacdStochScrapGetError(f'cant open headless browser : [{e}]')
            except KeyboardInterrupt:
                driver.quit()
                sys.exit(1)
           
            # ブラウザ閉じる
            driver.quit()
            self.log.info(f'browser closed')
            

            # データフレームとして作成しメンバーに登録(時系列では降順として作成)
            bitf_rate_df_tmp = pd.DataFrame(rate_array.reshape(1, 5), columns=['open', 'high', 'low', 'close', 'get_time'])    
            macd_df_tmp     = pd.DataFrame(macd_array.reshape(1, 4), columns=['hist', 'macd', 'signal', 'get_time'])    
            stoch_df_tmp    = pd.DataFrame(stoch_array.reshape(1, 3), columns=['pK', 'pD', 'get_time'])   
            self.bitf_rate_df = pd.concat([self.bitf_rate_df, bitf_rate_df_tmp], ignore_index=True)
            self.macd_df  = pd.concat([self.macd_df, macd_df_tmp], ignore_index=True)
            self.stoch_df = pd.concat([self.stoch_df, stoch_df_tmp], ignore_index=True)   
            self.log.info(f'memb registed done : [macd {macd_array}, stoch {stoch_array}]')

            # ファイル書き出し
            try:
                self._write_csv_dataframe(df=self.bitf_rate_df, path=CLOSE_RATE_FILE_PATH + self.bitf_rate_filename)
                self._write_csv_dataframe(df=self.macd_df,      path=MACD_FILE_PATH       + self.macd_filename)
                self._write_csv_dataframe(df=self.stoch_df,     path=STOCH_FILE_PATH      + self.stoch_filename)
            except Exception as e:
                self.log.critical(f'cant write macd stoch data : [{e}]')
                driver.quit()
                self.init_memb()
                raise CloseMacdStochScrapGetError(f'cant open headless browser : [{e}]')
            self.log.info(f'dataframe to csv write done')


            # データフレームが一定行数超えたら古い順から削除
            if len(self.bitf_rate_df) > n_row: self.bitf_rate_df.drop(index=self.bitf_rate_df.index.max())
            if len(self.macd_df)      > n_row: self.macd_df.drop(index=self.macd_df.index.max())
            if len(self.stoch_df)     > n_row: self.stoch_df.drop(index=self.stoch_df.index.max())

# test
            print(self.bitf_rate_df)
            print(self.macd_df)
            print(self.stoch_df)
# test



    def scrap_macd_stoch_stream(self, sleep_sec=1, n_row=65):
        """
        *tradingviewの自作のチャートからmacd,ストキャスティクスの値を取得する
         →https://jp.tradingview.com/chart/wTJWkxIA/
        * param
            sleep_sec:int (default 1) スリープ時間(秒)
            n_row:int (default 65) 作成したdataframeを保持する行数.超えると削除
        * return
            無し
            取得成功
                self.macd_dfに取得時刻, macd, signal, ヒストグラムを格納
                self.stoch_dfに取得時刻,%K, %Dの値を格納
            取得失敗: 例外を発生させる
        """
        self.log.info(f'scrap_macd_stoch() called')

        # ヘッドレスブラウザでtradingviewのURLを開く
        try:
            options = webdriver.ChromeOptions()
            options.add_argument('--headless')
            driver = webdriver.Chrome(options=options)
            driver.get('https://jp.tradingview.com/chart/wTJWkxIA/')
    
            # チャートのJSが完了するまで待機
            time.sleep(10)
        except Exception as e:
            driver.quit()
            self.log.critical(f'cant open headless browser : [{e}]')
            raise CloseMacdStochScrapGetError(f'cant open headless browser : [{e}]')

        self.log.info(f'headless browser opend')

        # macd関連のデータ取得
        while True:
            try:
                # CSSセレクタで指定のクラスでelementを取得
                ind_array = driver.find_elements_by_css_selector('.valuesWrapper-2KhwsEwE')
                get_time = datetime.datetime.now()
                self.log.info(f'got elements :[{ind_array}]')

                # リストに変換(MACDはマイナスが全角表記になっているためreplaceで置換しておく
                macd_array  = ind_array[1].text.replace('−', '-').split('\n')
                stoch_array = ind_array[2].text.split('\n')
                self.log.info(f'scraped to array : [macd {macd_array}, stoch {stoch_array}]')

                # 文字列を数値へ変換
                macd_array  = [int(data) for data in macd_array]
                stoch_array = [float(data) for data in stoch_array]
                self.log.info(f'converted numeric : [macd {macd_array}, stoch {stoch_array}]')

                # 取得時刻をリストに追加
                macd_array.append(get_time)
                stoch_array.append(get_time)

                # numpyのndarrayに変換
                macd_array  = np.array(macd_array) 
                stoch_array = np.array(stoch_array)

                #------------------------------------------------------------------------
                # tradingview側でHTMLの変更があった場合に備えて
                # 値に制限のある ストキャスティクスの値でスクレイピングの異常を検知する
                #------------------------------------------------------------------------
                if ((stoch_array[:2] < 0.00).any() == True) or ((stoch_array[:2] > 100.00).any() == True):
                    self.log.critical(f'sotch value invalid : [{stoch_array}]')
                    raise CloseMacdStochScrapGetError(f'sotch value invalid : [{stoch_array}]')
            except Exception as e:
                self.log.critical(f'cant get macd stoch data : [{e}]')
                driver.quit()
                self.init_memb()
                raise CloseMacdStochScrapGetError(f'cant open headless browser : [{e}]')
            except KeyboardInterrupt:
                driver.quit()
                self.init_memb()
                sys.exit(1)

            # データフレームとして作成しメンバーに登録(時系列では降順として作成)
            macd_stream_df_tmp   = pd.DataFrame(macd_array.reshape(1, 4), columns=['hist', 'macd', 'signal', 'get_time'])    
            stoch_stream_df_tmp  = pd.DataFrame(stoch_array.reshape(1, 3), columns=['pK', 'pD','get_time'])   
            self.macd_stream_df  = pd.concat([macd_stream_df_tmp, self.macd_stream_df], ignore_index=True)
            self.stoch_stream_df = pd.concat([stoch_stream_df_tmp, self.stoch_stream_df], ignore_index=True)   
            self.log.info(f'memb registed done : [macd {macd_array}, stoch {stoch_array}]')

            # 1分足macd,stochのcloseデータを作成
            if macd_stream_df_tmp['get_time'].item().second == 59:
                self.mk_close_macd(df=macd_stream_df_tmp)
            if stoch_stream_df_tmp['get_time'].item().second == 59:
                self.mk_close_stoch(df=stoch_stream_df_tmp)

            del(macd_stream_df_tmp)
            del(stoch_stream_df_tmp)

            # メモリ削減のため古いデータを削除
            if len(self.macd_stream_df)  == n_row:self.macd_stream_df.drop(index=self.macd_stream_df.index.max(), inplace=True)
            if len(self.stoch_stream_df) == n_row:self.stoch_stream_df.drop(index=self.stoch_stream_df.index.max(), inplace=True)

            # ファイル書き出し
            try:
                self._write_csv_dataframe(df=self.macd_stream_df, path=MACD_STREAM_FILE_PATH + self.macd_stream_filename)
                self._write_csv_dataframe(df=self.stoch_stream_df, path=STOCH_STREAM_FILE_PATH + self.stoch_stream_filename)
            except Exception as e:
                self.log.critical(f'cant write macd stoch data : [{e}]')
                driver.quit()
                self.init_memb()
                raise CloseMacdStochScrapGetError(f'cant open headless browser : [{e}]')

            time.sleep(sleep_sec)
            self.log.info(f'scraping 1cycle done')



    def mk_close_macd(self, df, n_row=30):
        """
        * scrap_macd_stoch()で取得したmacdのデータを1分足のクローズとして作成する
          作成したデータをCSVとして出力する
        * param
            df   :dataframe closeデータ作成のためのデータフレーム
            n_row:int (default 30) 保持する行数
        * return
            True :bool closeデータ作成成功
            False:bool closeデータ作成失敗             
        """
        self.log.info(f'mk_close_macd() called') 

        # メンバに登録(時系列としては昇順)
        self.macd_df = pd.concat([self.macd_df, df], ignore_index=True)
        self.log.info(f'close macd data make done')
        # ファイル出力
        try:
            self._write_csv_dataframe(df=self.macd_df, path=MACD_FILE_PATH + self.macd_filename)
        except Exception as e:
            self.log.critical(f'to csv failed : [{e}]')
            return False

#test
        print('----- macd -----')
        print(self.macd_df)
        if len(self.macd_df)  == n_row:self.macd_df.drop(index=0, inplace=True)
        del(df)
        self.log.info(f'mk_close_macd() done')
        return True



    def mk_close_stoch(self, df, n_row=30):
        """
        * scrap_macd_stoch()で取得したmacdのデータを1分足のクローズとして作成する
          ※スクレイピング処理に時間がかかり欠損が生じるため59秒のデータを取得できい場合は58秒時の値を採用する
        * param
            df   :dataframe closeデータ作成のためのデータフレーム
            n_row:int (default 30) 保持する行数
        * return
            True :bool closeデータ作成成功
            False:bool closeデータ作成失敗
        """
        self.log.info(f'mk_close_stoch() called') 


        # メンバに登録(時系列としては昇順)
        self.stoch_df = pd.concat([self.stoch_df, df], ignore_index=True)
        self.log.info(f'close stoch data make done')

        # ファイル出力
        try:
            self._write_csv_dataframe(df=self.stoch_df, path=STOCH_FILE_PATH + self.stoch_filename)
        except Exception as e:
            self.log.critical(f'to csv failed : [{e}]')
            return False
#test
        print('----- stoch -----')
        print(self.stoch_df)
        if len(self.stoch_df)  == n_row:self.stoch_df.drop(index=0, inplace=True)
        del(df)
        self.log.info(f'mk_close_stoch() done')
        return True



    def check_cor_gmo_bitflyer(self, cor_thresh=0.5, symbol='BTC_JPY', n_mv=5, sleep_sec=60, retry_sleep_sec=10, retry_thresh=3, sma_len_thresh=10, len_thresh=50):
        """
        * GMOコインとビットフライヤーでの最新レートで同じトレンド(相関関係)となっているか確認する
          相関関係は1分足の5移動平均の相関係数で判断
          相関関係が確認されるまで「STOP_NEW_TRADE」ファイルを作成し新規ポジションを作成させない
          相関関係が確認されると「STOP_NEW_TRADE」ファイルを削除しトレード可能となる
        * param
            cor_thresh:float (default 0.7) 相関係数の閾値。これを下回ると取引停止とさせる
            symbol:str (default 'BTC_JPY') 対象となる通貨
            n_mv:int (defult 5) 移動平均の次数
            sleep_sec:int (default 5) スリープ秒
            retry_sleep_sec:int (default 10) リトライ用のスリープ
            retry_thresh:int (default 3) リトライ回数の閾値。超えるとSTOP_NEW_TRADEファイルを作成
            sma_len_thresh:int (default 5) 単純移動平均を保持する個数。超えると古いものから削除する
            len_thresh:int (default 60) レートを保持する個数。超えると古いものから削除する
        * return
            無し 
                閾値以上:pass
                閾値未満:STOP_NEW_TRADE ファイルを作成し新規ポジションを停止させる
                         ※ただし閾値以上に戻ったらSTOP_NEW_TRADE ファイルを削除する
        """
        self.log.info(f'is_cor_gmo_bitflyer() called')

        # 新規ポジションを停止させる「STOP_NEW_TRADE」を作成
        self.make_file(path=SYSCONTROL, filename=STOP_NEW_TRADE)            

        # ビットフライヤー用のインスタンス作成
        btu = BitfilyerTradUtil() 

        # レート格納用dataframe(乱数で初期化※空で作成すると相関係数を計算する時にゼロで割りエラーとなるため)
        gmo_rate_df          = pd.DataFrame(columns=['rate'])
        gmo_rate_sma_df      = pd.DataFrame(columns=['rate_sma'])
        bitflyer_rate_df     = pd.DataFrame(columns=['rate'])
        bitflyer_rate_sma_df = pd.DataFrame(columns=['rate_sma'])
        
        # リトライカウント用変数
        gmo_retry_cnt  = 0
        bitf_retry_cnt = 0

        # LINE通知用フラグ
        is_line = False

        while True:

            while True:
                # GMO最新レート取得
                gmo_rate = self._get_rate()
                if gmo_rate != -1:
                    break

                # リトライ
                time.sleep(retry_sleep_sec) 
                gmo_retry_cnt += 1
                self.log.info(f'_get_rate() retry. retry count : [{gmo_retry_cnt}]')
                continue

                # リトライ回数の閾値を超えたらSTOP_NEW_TRADE ファイルを作成し新規ポジションを停止させる
                if gmo_retry_cnt > retry_thresh:
                    self.make_file(path=SYSCONTROL, filename=STOP_NEW_TRADE)            
                    if is_line == False:
                        self.line.send_line_notify(f'\
                                [CRITICALL]\
                                ビットフライヤーの最新レートを取得できませんでした。\
                                新規ポジション作成を停止します。')
                        is_line = True
                    # dataframe、リトライカウント用変数を初期化
                    gmo_rate_df     = pd.DataFrame(columns=['rate'])
                    gmo_rate_sma_df = pd.DataFrame(columns=['rate_sma'])
                    gmo_retry_cnt  = 0
                    continue

            # レート格納
            df_tmp = pd.DataFrame([gmo_rate], columns=['rate'])
            gmo_rate_df = pd.concat([gmo_rate_df, df_tmp], ignore_index=True)
            
            # 移動平均を計算
            if len(gmo_rate_df) >= n_mv:
                df_tmp = pd.DataFrame(columns=['rate_sma']) 
                df_tmp['rate_sma'] = gmo_rate_df['rate'].rolling(n_mv).mean().dropna(how='all').tail(n=1).values
                gmo_rate_sma_df = pd.concat([gmo_rate_sma_df, df_tmp], ignore_index=True)
            #-------------- GMO ここまで --------------#

            while True:
                # ビットフライヤーのレート
                bitflyer_rate = btu.get_ticker()
                if bitflyer_rate['ltp'] != -1:
                    break

                # リトライ
                time.sleep(retry_sleep_sec) 
                bitf_retry_cnt += 1
                continue

                # リトライ回数の閾値を超えたらSTOP_NEW_TRADE ファイルを作成し新規ポジションを停止させる
                if bitf_retry_cnt > retry_thresh:
                    self.make_file(path=SYSCONTROL, filename=STOP_NEW_TRADE) 
                    if is_line == False:
                        self.line.send_line_notify(f'\
                                [CRITICALL]\
                                ビットフライヤーの最新レートを取得できませんでした。\
                                新規ポジション作成を停止します。')
                        is_line = True
                    # dataframe、リトライカウント初期化
                    bitflyer_rate_df     = pd.DataFrame(columns=['rate'])
                    bitflyer_rate_sma_df = pd.DataFrame(columns=['rate_sma'])
                    bitf_retry_cnt = 0
                    continue

            # レート格納
            df_tmp = pd.DataFrame([bitflyer_rate['ltp']], columns=['rate'])
            bitflyer_rate_df = pd.concat([bitflyer_rate_df, df_tmp], ignore_index=True)
            
            # 移動平均を計算
            if len(bitflyer_rate_df) >= n_mv:
                df_tmp = pd.DataFrame(columns=['rate_sma']) 
                df_tmp['rate_sma'] = bitflyer_rate_df['rate'].rolling(n_mv).mean().dropna(how='all').tail(n=1).values
                bitflyer_rate_sma_df = pd.concat([bitflyer_rate_sma_df, df_tmp], ignore_index=True)
            #-------------- ビットフライヤー ここまで --------------#

            # レートの個数が2つ以上無い計算できないためconitnue
            if (len(gmo_rate_sma_df.index) < 2) and (len(bitflyer_rate_sma_df.index) < 2):
                time.sleep(sleep_sec)
                continue

            
            # 配列の長さが等しく無ければ配列を初期化し再度最新レートを取得する
            if len(gmo_rate_sma_df) != len(bitflyer_rate_sma_df):
                gmo_rate_df          = pd.DataFrame(columns=['rate'])
                gmo_rate_sma_df      = pd.DataFrame(columns=['rate_sma'])
                bitflyer_rate_df     = pd.DataFrame(columns=['rate'])
                bitflyer_rate_sma_df = pd.DataFrame(columns=['rate_sma'])
                self.log.info(f'gmo and biftlyer rate array length no match. init both array')
                continue


            # 相関係数を計算
            cor = np.corrcoef(gmo_rate_sma_df['rate_sma'].values, bitflyer_rate_sma_df['rate_sma'].values)[0,1]

            # 相関係数が閾値以上
            if cor >= cor_thresh:
                # ポジション停止ファイルがあった場合は削除する
                if self.rm_file(path=SYSCONTROL, filename=STOP_NEW_TRADE) == True:
                    if is_line == False:
                        self.line.send_line_notify(f'\
                                [INFO]\
                                GMOコインとビットフライヤーでトレンドの相関が確認できました。\
                                新規ポジション作成可能状態にします。\
                                相関係数:{cor}')
                        is_line = True

                self.log.info(f'gmo bitfilyer rate cor ok : [{cor}]')

            # 相関係数が閾値を下回るとSTOP_NEW_TRADE ファイルを作成し新規ポジションを停止させる
            else:
                self.log.critical(f'gmo bitfilyer rate cor NG : [{cor}]')
                self.make_file(path=SYSCONTROL, filename=STOP_NEW_TRADE)
                self.log.critical('stop new trad. make file {STOP_NEW_TRADE}')
                if is_line == False:
                    self.line.send_line_notify(f'\
                            [CRITICALL]\
                            GMOコインとビットフライヤーでトレンドの相関が崩れました。\
                            新規ポジションを停止状態にします。\
                            相関係数:{cor}')
                    is_line = True

            # 配列の長さが閾値を超えると古いものを削除(メモリ削減のため)
            if len(gmo_rate_df) > len_thresh: gmo_rate_df.drop(index=0, inplace=True)
            if len(gmo_rate_sma_df) > sma_len_thresh: gmo_rate_sma_df.drop(index=0, inplace=True)
            if len(bitflyer_rate_df) > len_thresh: bitflyer_rate_df.drop(index=0, inplace=True)
            if len(bitflyer_rate_sma_df) > sma_len_thresh: bitflyer_rate_sma_df.drop(index=0, inplace=True)

            # リトライカウント初期化
            gmo_retry_cnt  = 0
            bitf_retry_cnt = 0

            time.sleep(sleep_sec)
            continue



    async def positioner_stoch(self, row_thresh=20, hight_thresh=80, sleep_sec=1, n_row=5):
        """
        * ストキャスティクスの値によりポジション判定を行う
          スクレイピングとは別プロセスなのでスクレイピングで出力したファイルを読み込み判定する
          ストキャスティクスはリアルタイムでなく1分足closeを使用する
          閾値をクリアした行を基準値としてポジション判定を行う。
          基準値が確定すると基準値確定フラグがTrue、未確定の場合はFalseとする
          ファイル出力はなくpandas上で保持。ログにはポジション情報が出力される
        * param
            row_thresh:int (default 20) ストキャスティクスのロング目線でのライン閾値
            hight_thresh:int (default 80)ストキャスティクスのショート目線での閾値
            dlt_se:int (default 180) 上記の閾値を超えてからGX、DXが生じるまでの秒。この時間未満だと判定しない
            sleep_sec:int (default 1) スリープ秒
            n_row:int (default 5) ポジションデータ保持行数。超えたら古いものから削除
        * return
            なし
                ポジションが確定すると下記データフレームにポジション情報を格納する
                また、データフレームに格納された情報をcsvファイルとして書き出す
                self.pos_stoch_jdg_df
        """


        # ポジション確定フラグ
        is_position = False

        while True:
            self.log.info(f'positioner_stoch() called')        
#test
            print('----- stoch -----')
            print(self.pos_stoch_jdg_df)

            # ストキャスティクスcloseデータ読み込み(get_timeはnumpyのdatetime型で指定)
            try:
                stoch_df = self._read_csv_dataframe(path=STOCH_FILE_PATH, filename=None, dtypes={'get_time':'np.datetime[64]'}) 
            except Exception as e:
                self.log.error(f'{e}')
                await asyncio.sleep(sleep_sec)
                continue
            self.log.info(f'stoch close data to dataframe done')        

            # ストキャスティクスcloseデータが未作成の場合
            if len(stoch_df) == 0:
                await asyncio.sleep(sleep_sec)
                continue

            # 最新(2行)のストキャスティクスを取得
            last_stoch_df = stoch_df.tail(n=2).reset_index(level=0, drop=True)
            self.log.info(f'last_stoch_df : [{last_stoch_df.to_json()}]')

            # 閾値をクリアしていなければ判定しない
            if row_thresh < last_stoch_df.at[0, 'pK'] < hight_thresh:
                self.log.info(f'stoch close data not satisfy :[{last_stoch_df.at[0, "pK"]}]')
                await asyncio.sleep(sleep_sec)
                continue

            # ポジション判定処理
            # LONG目線
            if last_stoch_df['pK'][0] <= row_thresh:
                if last_stoch_df['pK'][0] < last_stoch_df['pD'][0]:
                    if last_stoch_df['pK'][1] > last_stoch_df['pD'][1]:

                        if is_position == False:
                            # 時系列では降順として作成
                            tmp_df = pd.DataFrame({'position':'LONG', 'jdg_timestamp':datetime.datetime.now()}, index=[0])
                            self.pos_stoch_jdg_df = pd.concat([tmp_df, self.pos_stoch_jdg_df], ignore_index=True)
                            is_position = True
                            self.log.info(f'position set LONG')
                    else:
                        is_position = False
                else:
                    is_position = False
           
            # SHORT目線
            elif last_stoch_df['pK'][0] >= hight_thresh:
                if last_stoch_df['pK'][0] > last_stoch_df['pD'][0]:
                    if last_stoch_df['pK'][1] < last_stoch_df['pD'][1]:

                        if is_position == False:
                            # 時系列では降順として作成
                            tmp_df = pd.DataFrame({'position':'SHORT', 'jdg_timestamp':datetime.datetime.now()}, index=[0])
                            self.pos_stoch_jdg_df = pd.concat([tmp_df, self.pos_stoch_jdg_df], ignore_index=True)
                            is_position = True
                            self.log.info(f'position set SHORT')
                    else:
                        is_position = False
                else:
                    is_position = False
            else:
                is_position = False
#            # LONG目線
#            if std_stoch_df.at[0, 'pK'] <= row_thresh:
#
#                # GX状態
#                if last_stoch_df.at[0, 'pK'] > last_stoch_df.at[0, 'pD']:
#
#                    # 基準値の時刻からdlt_sec秒経過していればポジション確定
#                    if (last_stoch_df['get_time'][0] - std_stoch_df['get_time'][0]).seconds >= dlt_sec:
#
#                        if is_position == False:
#                            # 時系列では降順として作成
#                            tmp_df = pd.DataFrame({'position':'LONG', 'jdg_timestamp':datetime.datetime.now()}, index=[0])
#                            self.pos_stoch_jdg_df = pd.concat([tmp_df, self.pos_stoch_jdg_df], ignore_index=True)
#                            is_position = True
#                            self.log.info(f'position set LONG')
#                    else:
#                        is_position = False
#                else:
#                    is_position = False
#
#
#            # SHORT目線
#            elif std_stoch_df.at[0, 'pK'] >= hight_thresh:
#
#                # DX状態
#                if last_stoch_df.at[0, 'pK'] < last_stoch_df.at[0, 'pD']:
#
#                    # 基準値の時刻からdlt_sec秒経過していればポジション確定
#                    if (last_stoch_df['get_time'][0] - std_stoch_df['get_time'][0]).seconds >= dlt_sec:
#
#                        if is_position == False:
#                            # 時系列では降順として作成
#                            tmp_df = pd.DataFrame({'position':'SHORT', 'jdg_timestamp':datetime.datetime.now()}, index=[0])
#                            self.pos_stoch_jdg_df = pd.concat([tmp_df, self.pos_stoch_jdg_df], ignore_index=True)
#                            is_position = True
#                            self.log.info(f'position set SHORT')
#
#                    else:
#                        is_position = False
#                else:
#                    is_position = False
#
#
            await asyncio.sleep(sleep_sec)

            # ポジション格納データフレームの行数が一定数超えたら古いものから削除
            if len(self.pos_stoch_jdg_df) > n_row:
                self.pos_stoch_jdg_df.drop(index=self.pos_stoch_jdg_df.index.max(), inplace=True)




    async def positioner_macd(self, hist_zero=100, kms_thresh=-376000, sleep_sec=1, n_row=5):
        """
        * macdの情報によりポジション判定を行う
        * param
            hist_zero:int (default 100) 反発系での判定でヒストグラムの絶対値がこの閾値以下であればゼロとみなす
            kms_thresh:int MACDとシグナルの傾きの積の閾値(オリジナル指標).閾値以下の場合GX or DX間近
            sleep_sec:int (default 1) スリープ秒
            n_row:int (default 5) ポジション情報を保持するdataframeのレコード数。超えると古いものから削除する
        * return
            なし
            　ポジションが確定すると下記のメンバに格納する
              self.pos_macd_jdg_df
        """
        self.log.info(f'positioner_macd() called')
        
        # ポジション確定フラグ
        is_position = False
       

        while True:

            # macdのcloseデータ読み込み(get_timeはnumpyのdatetime型で指定)
            try:
                macd_df = self._read_csv_dataframe(path=MACD_FILE_PATH, filename=None, dtypes={'get_time':'np.datetime[64]'}) 
            except Exception as e:
                self.log.error(f'{e}')
                await asyncio.sleep(sleep_sec)
                continue
            self.log.info(f'stoch close data to dataframe done')        

            # 最新のmacd情報を取得（3行）
            tmp_macd_df = macd_df.tail(n=3).reset_index(level=0, drop=True)
            self.log.info(f'macd data : [{tmp_macd_df.to_json()}]')

            if len(tmp_macd_df) < 3:
                await asyncio.sleep(sleep_sec)
                continue

            macd0 = tmp_macd_df['macd'][0]           
            macd1 = tmp_macd_df['macd'][1]
            macd2 = tmp_macd_df['macd'][2]

            signal0 = tmp_macd_df['signal'][0]            
            signal1 = tmp_macd_df['signal'][1]
            signal2 = tmp_macd_df['signal'][2]

            hist0 = tmp_macd_df['hist'][0]
            hist1 = tmp_macd_df['hist'][1]
            hist2 = tmp_macd_df['hist'][2]

            # MACDとシグナルの傾き
            kmd1 = (macd1 - macd0) / 1
            kmd2 = (macd2 - macd1) / 1

            ksg1 = (signal1 - signal0) / 1
            ksg2 = (signal2 - signal1) / 1

            # MACDとシグナルの傾きの積（オリジナル指標）
            kms1 = kmd1 * ksg1
            kms2 = kmd2 * ksg2
            self.log.info(f'kms1 : [{kms1}] kms2 : [{kms2}]')

            
            # ポジション判定

            #------------------
            # GX (LONG)
            #------------------
            if macd0 < signal0 and macd2 > signal2:

                # 時系列では降順として作成
                if is_position == False:
                    tmp_df = pd.DataFrame({'position':'LONG', 'jdg_timestamp':datetime.datetime.now()}, index=[0])
                    self.pos_macd_jdg_df = pd.concat([tmp_df, self.pos_macd_jdg_df], ignore_index=True)
                    is_position = True
                    self.log.info(f'position set LONG : pattern [GX]')
            
            #------------------
            # DX (SHORT)
            #------------------
            elif macd0 > signal0 and macd2 < signal2:
                # 時系列では降順として作成
                if is_position == False:
                    tmp_df = pd.DataFrame({'position':'SHORT', 'jdg_timestamp':datetime.datetime.now()}, index=[0])
                    self.pos_macd_jdg_df = pd.concat([tmp_df, self.pos_macd_jdg_df], ignore_index=True)
                    is_position = True
                    self.log.info(f'position set SHORT : pattern [DX]')

            #-----------------------------
            # シグナル上で上に反発（LONG）
            #-----------------------------
            elif ((macd1 < macd0) and (macd1 < macd2)) and ((hist0 > hist_zero) and (abs(hist1) < hist_zero) and (hist2 > hist_zero)):

                # 時系列では降順として作成
                if is_position == False:
                    tmp_df = pd.DataFrame({'position':'LONG', 'jdg_timestamp':datetime.datetime.now()}, index=[0])
                    self.pos_macd_jdg_df = pd.concat([tmp_df, self.pos_macd_jdg_df], ignore_index=True)
                    is_position = True
                    self.log.info(f'position set LONG : pattern [rebound LONG]')

            #-----------------------------
            # シグナル上で下に反発（SHORT）
            #-----------------------------
            elif ((macd1 > macd0) and (macd1 > macd2)) and ((hist0 < -hist_zero) and (abs(hist1) < hist_zero) and (hist2 < -hist_zero)):

                # 時系列では降順として作成
                if is_position == False:
                    tmp_df = pd.DataFrame({'position':'SHORT', 'jdg_timestamp':datetime.datetime.now()}, index=[0])
                    self.pos_macd_jdg_df = pd.concat([tmp_df, self.pos_macd_jdg_df], ignore_index=True)
                    is_position = True
                    self.log.info(f'position set SHORT : pattern [rebound SHORT]')
            
            #------------------------------
            # GX間近(オリジナル指標を使用)
            #------------------------------
            elif ((hist0 < 0) and (hist1 < 0) and (hist2 < 0)) and ((kms1 > 0) and (kms2 <= kms_thresh)):
                # 時系列では降順として作成
                if is_position == False:
                    tmp_df = pd.DataFrame({'position':'LONG', 'jdg_timestamp':datetime.datetime.now()}, index=[0])
                    self.pos_macd_jdg_df = pd.concat([tmp_df, self.pos_macd_jdg_df], ignore_index=True)
                    is_position = True
                    self.log.info(f'position set LONG : pattern [nearness GX]')

            #------------------------------
            # DX間近(オリジナル指標を使用)
            #------------------------------
            elif ((hist0 > 0) and (hist1 > 0) and (hist2 > 0)) and ((kms1 > 0) and (kms2 <= kms_thresh)):
                # 時系列では降順として作成
                if is_position == False:
                    tmp_df = pd.DataFrame({'position':'SHORT', 'jdg_timestamp':datetime.datetime.now()}, index=[0])
                    self.pos_macd_jdg_df = pd.concat([tmp_df, self.pos_macd_jdg_df], ignore_index=True)
                    is_position = True
                    self.log.info(f'position set SHORT : pattern [nearness DX]')

            else:
                self.log.info('no position stat')
                is_position = False


            # ポジションデータが一定数超えたら古いものから削除
            if len(self.pos_macd_jdg_df.index) > n_row:
                self.pos_macd_jdg_df.drop(index=self.pos_macd_jdg_df.index.max(), inplace=True)

            await asyncio.sleep(sleep_sec)
# test
            print('----- macd -----')
            print(self.pos_macd_jdg_df)



    async def positioner(self, path=POSITION_FILE_PATH, dlt_sec=185, n_row=3, sleep_sec=1):
        """
        * ストキャスティクスとMACDから判定されたポジションをもとに
        　最終のポジションを判定する。
        　この最終のポジションが確定しないとトレードしない
          ポジション確定した場合、指定されたディレクトリ配下にポジション情報をファイル名とした空ファイルを作成
        * param
            path=
            dlt_sec:int (default 180)
            n_row:int (default 3) ポジションデータ保持数。超えると古い順に削除される
            sleep_sec:int (default 1) スリープ秒
        * return
            なし
                ポジション確定の場合:self.pos_jdg_dfにポジション情報を格納し、
                                     指定されたディレクトリ配下にポジション情報をファイル名とした空ファイルを作成
                                     ファイルが作成できない場合は例外を発生させる
                                     * ファイル名の例
                                     {position}_{jdg_timestamp} ※「T」が入ることに注意
                                     LONG_2021-04-07T17:59:18.037976
                ポジション未確定の場合:pass
        * Exception
            PosJudgementError
        """
        # ライン通知用（テスト)
        is_line = False

        # ポジション確定フラグ
        is_position = False

        while True:
            self.log.info('positioner() called') 
            await asyncio.sleep(sleep_sec)
            
            # 各ポジションを読み込む
            pos_macd  = self.pos_macd_jdg_df.head(n=1)
            pos_stoch = self.pos_stoch_jdg_df.head(n=1)
            
            # ポジションが未確定の場合はcontinue
            if pos_stoch['position'][0] == 'STAY':
                self.log.info(f'stoch no position stat : [{pos_stoch.to_json()}]')  
                continue

            if pos_macd['position'][0] == 'STAY':
                self.log.info(f'macd no position stat : [{pos_macd.to_json()}]')  
                continue
             
            # MACDとストキャスティクスのポジションでない場合はcontinue
            if pos_stoch['position'][0] != pos_macd['position'][0]:
                self.log.info(f"macd stoch not same position. macd :[{pos_stoch['position'][0]}] stoch :[{pos_macd['position'][0]}]")
                is_line = False
                is_position = False 
                continue

            # 各ポジション判定時間が閾値を超えている場合はcontinue
            dlt_jdg_timestamp = pos_macd['jdg_timestamp'][0] - pos_stoch['jdg_timestamp'][0]
            self.log.debug(f'dlt_jdg_timestamp.seconds : [{dlt_jdg_timestamp.seconds}]')
            if dlt_jdg_timestamp.seconds > 0:
                if dlt_jdg_timestamp.seconds > dlt_sec:
                    self.log.info(f'time lag not satisfy. dlt_jdg_timestamp : [{dlt_jdg_timestamp}]')
                    is_line = False
                    is_position = False
                    continue
            else:
                if dlt_jdg_timestamp.seconds < dlt_sec:
                    self.log.info(f'time lag not satisfy. dlt_jdg_timestamp : [{dlt_jdg_timestamp}]')
                    is_line = False
                    is_position = False
                    continue

            # ポジションデータを指定されたディレクトリ配下に空ファイルとして作成
            filename = pos_stoch['position'][0] + '_' + datetime.datetime.now().isoformat()
#test
            if is_line == False:
                self.line.send_line_notify(f'[INFO]\
                        ポジション確定しました。↓\
                        position : [{filename}]')
                is_line = True
#test
            if is_position == False:
                if self.make_file(path=path, filename=filename) == False:
                    self.log.critical(f'cant make position file. path : [{path}]')
                    raise PosJudgementError(f'cant make position file. path : [{path}]')
                is_position = True
            continue



    def trader(self, size=0.01, n_pos=1, loss_cut_rate=40000):
        """
        * ポジションファイルを読み込みトレードを行う
        * param
            size:float or int ロット数(default 0.01)
            n_pos:int (default 1) ポジション数。これ以上のポジションは持たない
            loss_cut_rate:int (default 40000) 損切りライン。ただし相場の状況によっては最新レートに近づける,
                              あるいは成行で損切りする場合もある
                              （保有しているポジションとは逆のポジションがpositionerから指示が出た場合など)
        """
        while True:
            self.log.info('trader() called')
            
            # ポジションファイル読み込み




    def trade_common_resource(self):
        """
        * トレードで使うリソースを設定
        * param
            なし
        * return
            リソースのdict(下記参照)
        """
        apiKey    = os.environ['GMO_API_KEY']
        secretKey = os.environ['GMO_API_SKEY']
        method    = 'POST'
        endPoint  = 'https://api.coin.z.com/private'
        timestamp = '{0}000'.format(int(time.mktime(datetime.datetime.now().timetuple())))
        return {'API-KEY':apiKey, 'API-SKEY':secretKey, 'method':method, 'endPoint':endPoint, 'timestamp':timestamp} 




    def get_position_info(self):
        """
        * 約定情報、建玉情報、注文情報、余力情報、資産残高情報を参照するためのリソース設定
        * param
            なし
        * return
            リソースのdict(下記参照)
        """
        apiKey    = os.environ['GMO_API_KEY']
        secretKey = os.environ['GMO_API_SKEY']
        method    = 'GET'
        endPoint  = 'https://api.coin.z.com/private'
        timestamp = '{0}000'.format(int(time.mktime(datetime.datetime.now().timetuple())))
        return {'API-KEY':apiKey, 'API-SKEY':secretKey, 'method':method, 'endPoint':endPoint, 'timestamp':timestamp} 


    def order(self, symbol='BTC_JPY', size='0.01', executionType='LIMIT', timeInForce='FAS', priceRang=4000, losscutPrice=''):
        """
        * 注文を実行する
        * param
            symbol:str (default 'BTC_JPY') 対象通貨
            size:str (default '0.01') 通貨量
            executionType:str (default 'LIMIT'指値) 'MARKET'成行, 'STOP'逆指値
            timeInForce:str (default 'FAS' こちらを参照:https://api.coin.z.com/docs/#order)
            priceRang:int (default 4000) 最新レートから差し引く金額※最新レートから差し引いた金額が実際の注文金額となる
            losscutPrice:str (default '')GMO側でロスカットされる金額。空文字の場合自動で設定される
        * return
            is_order:bool
                True:注文成功
                False:注文失敗
        """
        pass





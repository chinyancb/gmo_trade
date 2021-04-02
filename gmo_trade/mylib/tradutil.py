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
import numexpr
#from pyti.moving_average_convergence_divergence import moving_average_convergence_divergence as macd
#from pyti.exponential_moving_average import exponential_moving_average as ema
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import chromedriver_binary
from  mylib.lineutil import LineUtil
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
POSITION_MACD_FILE_PATH  = app_home + '/var/share/pos/macd/'     # MACDによるポジション判定結果
POSITION_STOCH_FILE_PATH = app_home + '/var/share/pos/stoch/'    # ストキャスティクスよるポジション判定結果
SYSCONTROL               = app_home + '/var/share/sysc/'         # システムコントロール用


# システムコントロール用ファイル名
INIT_POSITION  = 'init_positioner' # ポジションを初期化する(main_pos=STAYに設定する)
STOP_NEW_TRADE = 'stop_new_trade'     # 新規エントリーを停止する


# JST 変換用定数
JST = datetime.timezone(datetime.timedelta(hours=+9), 'JST') 

# ロギング
LOG_CONF = app_home + '/etc/conf/logging.conf'
logging.config.fileConfig(LOG_CONF)
log = logging.getLogger('tradeUtil')



class ExchangStatusGetError(Exception):
    """
    取引所用　自作例外クラス
    """
    pass

class CloseRateGetError(Exception):
    """
    closeレートを取得できない
    """
    pass

class MacdStochScrapGetError(Exception):
    """
    tradingviewからスクレイピングでMACD,ストキャスティクス関連情報を取得できない
    """
    pass


class TradUltil(object):

    def __init__(self): 

        # データ関連
        self.close_rate_df    = pd.DataFrame()  # closeレート格納用
        self.macd_stream_df   = pd.DataFrame()  # macdリアルタイムデータ格納用
        self.stoch_stream_df  = pd.DataFrame()  # ストキャスティクスデータ格納用
        self.macd_df          = pd.DataFrame()  # macd確定値データ格納用
        self.stoch_df         = pd.DataFrame()  # ストキャスティクス確定値データ格納用
        self.pos_jdg_df       = pd.DataFrame([{'main_pos':'STAY', 'sup_pos':'STAY', 'jdg_timestamp':datetime.datetime.now(tz=JST)}])  # ポジション計算用データフレーム
        self.pos_macd_jdg_df  = pd.DataFrame([{'main_pos':'STAY', 'sup_pos':'STAY', 'jdg_timestamp':datetime.datetime.now(tz=JST)}])  # ポジション計算用データフレーム
        self.pos_stoch_jdg_df = pd.DataFrame([{'main_pos':'STAY', 'sup_pos':'STAY', 'jdg_timestamp':datetime.datetime.now(tz=JST)}])  # ポジション計算用データフレーム

        # ファイル関連
        self.close_filename        = f"close_{datetime.datetime.now(tz=JST).strftime('%Y-%m-%d-%H:%M')}"       # closeデータの書き出しファイル名
        self.macd_filename         = f"macd_{datetime.datetime.now(tz=JST).strftime('%Y-%m-%d-%H:%M')}"        # macdデータの書き出しファイル名
        self.macd_stream_filename  = f"macd_stream{datetime.datetime.now(tz=JST).strftime('%Y-%m-%d-%H:%M')}"  # macd1秒データの書き出しファイル名
        self.stoch_filename        = f"stoch_{datetime.datetime.now(tz=JST).strftime('%Y-%m-%d-%H:%M')}"       # ストキャスティクスデータの書き出しファイル名
        self.stoch_stream_filename = f"stoch_stream{datetime.datetime.now(tz=JST).strftime('%Y-%m-%d-%H:%M')}" # ストキャスティクス1秒データの書き出しファイル名
        self.pos_filename          = f"pos_{datetime.datetime.now(tz=JST).strftime('%Y-%m-%d-%H:%M')}"         # ポジションデータの書き出しファイル名
        self.pos_macd_filename     = f"pos_{datetime.datetime.now(tz=JST).strftime('%Y-%m-%d-%H:%M')}"         # macdによるポジションデータの書き出しファイル名
        self.pos_stoch_filename    = f"pos_{datetime.datetime.now(tz=JST).strftime('%Y-%m-%d-%H:%M')}"         # ストキャスティクスによるポジションデータの書き出しファイル名

        # フラグ関連
        self.is_div         = False                                       # ダイバージェンスが発生していればTrue,起きていなければFalse 

        # Line通知用
        self.line = LineUtil()

    
        
    def init_memb(self):
        """
        closeレートの取得やMACDの計算,その他例外が発生した場合,緊急対応として使用しているdataframe,その他メンバを初期化する
        return:
            True
        """
        log.info('init_memb() called')
        self.__init__()
        self.line.send_line_notify('メンバを初期化しました')
        log.info('init_memb() done')
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
        log.info(f'init_position() called')
        try:
            pos_jdg_tmp_df = pd.DataFrame([{'main_pos':'STAY','sup_pos':'STAY',
                'jdg_timestamp':datetime.datetime.now(tz=JST)}])  # ポジション計算用データフレーム
        except Exception as e:
            log.critical(f'ポジションの初期化に失敗しました : [{e}]')
            return False

        self.pos_jdg_df = pos_jdg_tmp_df.copy()
        del(pos_jdg_tmp_df)

        log.info(f'position data is init done.')
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
        log.info(f'make_file() called')
        log.info(f'emptiness : [{path + filename}]')
            
        # ディレクトリ存在チェック。無ければ作成
        tmp_dir_list  = path.split('/')
        tmp_dir = '/'.join([str(i) for i in tmp_dir_list[0:-1]])
        if os.path.isdir(tmp_dir) == False:
            os.makedirs(tmp_dir, exist_ok=True)
            log.info(f'maked dir : [{tmp_dir}]')

        # 空ファイル作成
        try:
            with open(path + filename, mode=mode):
                pass
        except Exception as e:
            log.error(f'cant make emptiness file. : [{e}]')
            return False

        log.info(f'emptiness file make done.[{path + filename}]')
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
        log.info(f'rm_file() called.')
        
        # ファイルが存在しない場合
        if selt.is_exit_file(path, filename):
            log.info(f'not found remove file : [{path + filename}]')
            return None

        try:
            os.remove(path + filename)
        except Exception as e:
            log.error(f'remove file failure : [{e}]')

        log.info(f'remove file done : [{path + filename}]')
        log.info(f'rm_file() done')
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
        log.info(f'is_exit_file() called')

        if os.path.exists(path + filename):
            log.info(f'file is exists. : [{path + filename}]')
            log.info(f'is_exit_file is done')

            return True

        log.info(f'file not found : [{path + filename}]')
        log.info(f'is_exit_file() done')

        return False



    def _get_file_name(self, path, prefix='hist'):
        """
        * 指定されたディレクトリパス,prefixに当てはまるファイル名を取得
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

        log.info(f'_get_file_name() called')

        # ディレクトリ存在チェック
        if os.path.exists(path) == False:
            log.info(f'not found dir : [{path}]')
            return 'not_found_dir'

        # prefixにあたるファイル名があるか確認
        if len(glob.glob(f'{path}{prefix}*')) == 0:
            log.info(f'not found file : [{path}{prefix}]')
            return 'not_found_file'

        # ファイル名取得
        try:
            files = glob.glob(f"{path}{prefix}*")
            filename = max(files, key=os.path.getctime)
        except OSError as e:
            log.critical(f'cant get file name : [{e}]')
            return 'cant_get_file'

        # ファイル名が絶対パスなのでファイル名単体にする
        filename = filename.split('/')[-1]
        log.info(f'get file : [{filename}]')    
        log.info(f'_get_file_name() done')

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
        log.info(f'load_pos_df() called')

        # posファイルが無い場合
        if len(glob.glob(f'{POSITION_FILE_PATH}pos*')) == 0: 
            log.error(f'not found pos data file. under path : [{POSITION_FILE_PATH}]')
            return None

        try:
            files = glob.glob(f"{POSITION_FILE_PATH}pos*")
            latest_file = max(files, key=os.path.getctime)
        except OSError as e:
            log.critical(f'reload pos data error: [{e}]')
            return False

        # ポジションファイル読み込み
        try:
            latest_file = latest_file.split('/')[-1]
            log.info(f'load file : [{latest_file}]')
            pos_df = pd.read_csv(filepath_or_buffer=POSITION_FILE_PATH + latest_file, sep=',', header=0)
            log.info(f'csv file read done')
    
            # 先頭行を読み込み
            pos_df = pos_df.head(n=head_nrow).reset_index(level=0, drop=True)
            log.info(f'reset index done') 
    
            # 文字列からint、datetime型に変換
            pos_df['close_rate'] = pos_df['close_rate'].astype('int')
            log.info('close_rate dtype convert done.')
    
            # ポジション判定時刻の変換(そのまま読み込んで大丈夫）
            jdg_timestamp_list = []
            for i in range(0, head_nrow):
                jdg_timestamp_jst    = dateutil.parser.parse(pos_df['jdg_timestamp'][i]).astimezone(JST)
                jdg_timestamp_list.append(jdg_timestamp_jst)
            else:
                pos_df['jdg_timestamp'] = jdg_timestamp_list 
        except Exception as e:
            log.error(f'position data load failure : [{POSITION_FILE_PATH + latest_file}, {e}]')
            return False

        # 読み込んだファイルは時系列で降順となっているため昇順に変更
        pos_df = pos_df.sort_values(by ='jdg_timestamp', ascending=True).reset_index(level=0, drop=True)
        log.info('jdg_timestamp dtype convert done.')

        # メンバとしてコピー
        self.pos_jdg_df = pos_df.copy()
        del(pos_df)

        log.info(f'pos data load success.')
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

        log.info('_write_csv_dataframe() called.')
        # ディレクトリ存在チェック。無ければ作成
        tmp_dir_list  = path.split('/')
        tmp_dir = '/'.join([str(i) for i in tmp_dir_list[0:-1]])
        if os.path.isdir(tmp_dir) == False:
            os.makedirs(tmp_dir, exist_ok=True)
            log.info(f'maked dir : [{tmp_dir}]')

        df_tmp = df.copy()
        try:
            if df_tmp.to_csv(path_or_buf=path, sep=sep, index=index, mode=mode, header=header) == None:
                log.info(f'write dataframe to csv done. : [{path}]')
                del(df_tmp)
                return True
        except Exception as e:
            log.error(f'_write_csv_dataframe() cancelled.')
            return False 

    

    def _get_exchg_status(self, retry_sleep_sec=3):
        """
        * 引取所ステータス確認
        * param 
             retry_sleep_sec :リトライ用のスリープ時間（秒）
        * return 
             ecchg_stat:str(OPEN:オープン, PREOPEN:プレオープン, MAINTENANCE:メンテナンス)
        * Exception : ExchangStatusGetError
        """
        
        log.info(f'_get_exchg_status() called')
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
                log.critical(f"http status code error : [{e}]")
        
                # リトライ
                err_htp_cnt += 1
                if err_htp_cnt <= 10:
                    log.critical(f"http request error. exec retry: [{e}]")
                    time.sleep(retry_sleep_sec)
                    continue
                log.critical(f"http request error. process kill {e}")
                #sys.exit(1)
                raise ExchangStatusGetError(f'HTTPエラーにより取引所ステータスが取得できません')

            # jsonに変換
            exchg_status_js = json.dumps(response.json())

            # 取引所ステータス取得
            try:
                exchg_stat = json.loads(exchg_status_js)['data']['status']
            except Exception as e:
                log.error(f'不正なレスポンスです. : [{e}]')
                raise ExchangStatusGetError(exchg_stat)
            except ExchangStatusGetError as e:
                log.error(f"取引所ステータスを取得できませんでした:[{e}]")
            break

        log.info(f'_get_exchg_status() is done')
        return exchg_stat

    
    

    def _get_rate(self, symbol='BTC_JPY'):
        """
        * 現在のレートを取得する(リトライはしない)
        * param
            symbol:str (defult 'BTC_JPY') 通貨のタイプ
        * return
            last_rate:int 最新のレート(※レートの取得に失敗は-1を返す)
        """

        log.info(f'_get_rate() called')

        path = f'/v1/ticker?symbol={symbol}'
        url = PUBLIC_ENDPOINT + path
        try:
            response = requests.get(url)
            response.raise_for_status
        except requests.exceptions.RequestException as e:
            log.critical(f"http status code error : [{e}]")
            return -1

        try:
            response_json = json.dumps(response.json())
        except Exception as e:
            log.error(f'response convert json failure : [{e}]')
            return -1 

        # レスポンスのステータスが0以外であれば失敗
        if json.loads(response_json)['status'] != 0:
            log.error(f'respons status invalid : [{response_json}]')
            return -1

        last_rate = int(json.loads(response_json)['data'][0]['last'])
        if last_rate:
            log.info(f'_get_rate() done')
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

        log.info(f'_get_close_info() is called')
        # 取引所ステータス確認
        try:
            exchg_stat = self._get_exchg_status() 
            if exchg_stat != 'OPEN':
                time.sleep(retry_sleep_sec)
                log.info(f'取引所がOPENではありません。メンバを初期化します: [{exchg_stat}]')
                raise ExchangStatusGetError(exchg_stat)
        except ExchangStatusGetError as e:
            log.critical(f'取引所がOPENではありません。メンバを初期化します  : [{e}]')
            self.init_memb()
         
        path = f"/v1/trades?symbol={symbol}&page={page}&count={count}"
        url  = PUBLIC_ENDPOINT + path
        log.info(f"URL : [{url}]")

        # イテレーター
        err_htp_cnt = 0 # closeデータHTTPリクエスト失敗カウンター
        err_cnt     = 0 # closeデータリクエスト失敗カウンター
        
        while True:
            try:
                response = requests.get(url)
                response.raise_for_status() # HTTPステータスコードが200番台以外であれば例外を発生させる
            except requests.exceptions.RequestException as e:
                log.critical(f"{e}")
        
                # リトライ
                err_htp_cnt += 1
                if err_htp_cnt <= 10:
                    log.critical(f"http request error. exec retry : [{e}]")
                    time.sleep(retry_sleep_sec)
                    continue

                log.critical(f'HTTPエラーによりclose情報が取得できません. プロセスを終了します.  : [{e}]')
                #sys.exit(1)
                raise CloseRateGetError(f'HTTPエラーによりclose情報が取得できません')
        
        
            #closeのレートをjsonで取得
            rate_info_js = json.dumps(response.json())
        
            # ステータスコードが0以外であればリトライ
            if json.loads(rate_info_js)['status'] != 0:
                err_cnt += 1
                time.sleep(retry_sleep_sec)
                log.error(f"status code invalid : [{json.loads(rate_info_js)}]")
                continue

                # 3回失敗するとエラー判定
                if err_cnt == 3:
                    log.critical(f"不正なレスポンスです。プロセスを終了します : [{json.loads(rate_info_js)}]")
                    #sys.exit(1)
        
            # データの個数を取得
            itr = len(json.loads(rate_info_js)['data']['list'])
        
            # jsonをパース(データは時系列で降順で返却されているため新しい順にfor文が実行される
            for i in np.arange(itr):
                close_timestamp_tmp = json.loads(rate_info_js)['data']['list'][i]['timestamp']
                close_timestamp_jst = dateutil.parser.parse(close_timestamp_tmp).astimezone(JST)
                close_rate_tmp = int(json.loads(rate_info_js)['data']['list'][i]['price'])
            
                log.debug(f"cls_mt : [{cls_mt}] close_timestamp_jst.minute:[{close_timestamp_jst.minute}]")
                # 分が同じ場合
                if cls_mt == close_timestamp_jst.minute:
                    close_timestamp = close_timestamp_jst
                    close_rate      = close_rate_tmp
                    break
            else: 
                #!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
                # 100カウントで取得できない場合は現在時刻,レートは-1を返す(暫定対応)
                #!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
                log.warning(f'not found close rate in 100 length js.')
                close_timestamp = datetime.datetime.now(tz=JST) + datetime.timedelta(seconds=120)
                return {'close_timestamp' : close_timestamp, 'close_rate' : -1}        

            break # while文を抜ける
            #--------------- while文ここまで -----------------#
        log.info(f'_get_close_info() is done')
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

        log.info(f'get_close_info() called')

        while True:

            cls_tm = datetime.datetime.now(tz=JST)
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
                log.debug(f"cls_tm : {cls_tm}")
                close_dict = self._get_close_info(cls_tm.minute)

                # 最新のcloseの時刻(分)を取得
                if len(self.close_rate_df) >= 1:
                    last_close_rate_minute = self.close_rate_df['close_timestamp'].tail(n=1)[self.close_rate_df.index.max()].minute

                    # close_rateが-1に場合はリトライ
                    if close_dict['close_rate'] == -1:
                        log.warning(f"not found close data : [{close_dict['close_rate']}]")
                        log.info(f'retry func[_get_close_info()]')
                        
                        for _ in np.arange(1, 10):
                            time.sleep(retry_sleep_sec)
                            close_dict = self._get_close_info(cls_tm.minute, page=_)
                            if ((last_close_rate_minute + 1) == close_dict['close_timestamp'].minute) and (close_dict['close_rate'] != -1):
                                log.info(f'retry is success')
                                break
                        else:
                            log.info(f'not found close data. raise exception')
                            raise CloseRateGetError(f'not found close data')
                            return False

                # たまたま初回にclose_rateが-1で最初からやり直し
                if close_dict['close_rate'] == -1:
                    log.error(f"error: cant get close data : [{close_dict['close_rate']}]")
                    continue

                # データフレームを作成
                close_timestamp = close_dict["close_timestamp"]
                close_rate      = close_dict["close_rate"]
                close_rate_tmp_df = pd.DataFrame([[close_timestamp, close_rate]], columns=["close_timestamp","close_rate"])
                
                # 時系列的には昇順で作成
                self.close_rate_df = pd.concat([self.close_rate_df, close_rate_tmp_df], ignore_index=True).sort_values(by="close_timestamp", axis=0)

                # 1分毎にcloseレートが取れているか確認
                log.info(f"'check self.close_rate_df'")
                for i in range(0, len(self.close_rate_df)):
                    if i == 0:
                        tmp_close_tm = self.close_rate_df['close_timestamp'][i].minute
                        continue

                    # 59分の場合のみの条件
                    if tmp_close_tm == 59 and self.close_rate_df['close_timestamp'][i].minute == 0:
                        tmp_close_tm = self.close_rate_df['close_timestamp'][i].minute
                        continue 
                    elif (tmp_close_tm + 1) !=  self.close_rate_df['close_timestamp'][i].minute:
                        log.error(f"'self.close_rate_df' is  invalid. メンバを初期化します:[{self.close_rate_df.query('index==@i')}]")
                        self.init_memb() 
                        break
                    else:
                        tmp_close_tm = self.close_rate_df['close_timestamp'][i].minute
                else:
                    log.info(f"'self.close_rate_df' is ok")

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
                log.info('get_close_info() 1cycle done')
    


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
            log.critical(f'websocket api failed : [{errr}]')

        ws.on_open = on_open
        ws.on_message = on_message
        ws.on_error = on_error
        ws.run_forever()        

    def mk_close_data(self, df):
        while True:
            print(self.tmp_close_rate_df)
            time.sleep(5)




    def scrap_macd_stoch(self, sleep_sec=1, n_row=65):
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
        log.info(f'scrap_macd_stoch() called')

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
            log.critical(f'cant open headless browser : [{e}]')
            raise MacdStochScrapGetError(f'cant open headless browser : [{e}]')

        log.info(f'headless browser opend')

        # macd関連のデータ取得
        while True:
            try:
                # CSSセレクタで指定のクラスでelementを取得
                ind_array = driver.find_elements_by_css_selector('.valuesWrapper-2KhwsEwE')
                get_time = datetime.datetime.now(tz=JST)
                log.info(f'got elements :[{ind_array}]')

                # リストに変換(MACDはマイナスが全角表記になっているためreplaceで置換しておく
                macd_array  = ind_array[1].text.replace('−', '-').split('\n')
                stoch_array = ind_array[2].text.split('\n')
                log.info(f'scraped to array : [macd {macd_array}, stoch {stoch_array}]')

                # 文字列を数値へ変換
                macd_array  = [int(data) for data in macd_array]
                stoch_array = [float(data) for data in stoch_array]
                log.info(f'converted numeric : [macd {macd_array}, stoch {stoch_array}]')

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
                    log.critical(f'sotch value invalid : [{stoch_array}]')
                    raise MacdStochScrapGetError(f'sotch value invalid : [{stoch_array}]')
            except Exception as e:
                log.critical(f'cant get macd stoch data : [{e}]')
                driver.quit()
                self.init_memb()
                raise MacdStochScrapGetError(f'cant open headless browser : [{e}]')

            # データフレームとして作成しメンバーに登録(時系列では降順として作成)
            macd_stream_df_tmp   = pd.DataFrame(macd_array.reshape(1, 4), columns=['hist', 'macd', 'signal', 'get_time'])    
            stoch_stream_df_tmp  = pd.DataFrame(stoch_array.reshape(1, 3), columns=['pK', 'pD','get_time'])   
            self.macd_stream_df  = pd.concat([macd_stream_df_tmp, self.macd_stream_df], ignore_index=True)
            self.stoch_stream_df = pd.concat([stoch_stream_df_tmp, self.stoch_stream_df], ignore_index=True)   
            log.info(f'memb registed done : [macd {macd_array}, stoch {stoch_array}]')

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
                log.critical(f'cant write macd stoch data : [{e}]')
                driver.quit()
                self.init_memb()
                raise MacdStochScrapGetError(f'cant open headless browser : [{e}]')

            time.sleep(sleep_sec)
            log.info(f'scraping 1cycle done')



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
        log.info(f'mk_close_macd() called') 

        # メンバに登録(時系列としては昇順)
        self.macd_df = pd.concat([self.macd_df, df], ignore_index=True)
        log.info(f'close macd data make done')
        # ファイル出力
        try:
            self._write_csv_dataframe(df=self.macd_df, path=MACD_FILE_PATH + self.macd_filename)
        except Exception as e:
            log.critical(f'to csv failed : [{e}]')
            return False

#test
        print('----- macd -----')
        print(self.macd_df)
        if len(self.macd_df)  == n_row:self.macd_df.drop(index=0, inplace=True)
        del(df)
        log.info(f'mk_close_macd() done')
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
        log.info(f'mk_close_stoch() called') 


        # メンバに登録(時系列としては昇順)
        self.stoch_df = pd.concat([self.stoch_df, df], ignore_index=True)
        log.info(f'close stoch data make done')

        # ファイル出力
        try:
            self._write_csv_dataframe(df=self.stoch_df, path=STOCH_FILE_PATH + self.stoch_filename)
        except Exception as e:
            log.critical(f'to csv failed : [{e}]')
            return False
#test
        print('----- stoch -----')
        print(self.stoch_df)
        if len(self.stoch_df)  == n_row:self.stoch_df.drop(index=0, inplace=True)
        del(df)
        log.info(f'mk_close_stoch() done')
        return True



    def macd_calculator(self):
        '''
        MACDを計算する
        *param
            無し
        *return
            None : MACDを計算できるcloseデータがない場合
            True : MACDを計算しpositioner()を実行した場合
            False: MACDを計算しpositioner()を実行しなかった場合
        ''' 
        log.info('macd_calculator() called')

        # closeレートが26個無いと計算できないためNoneを返す
        if len(self.close_rate_df) < 26: 
            log.info(f'close data not enough : [{len(self.close_rate_df)}]')
            return None

        # closeの情報をコピー
        macd_tmp_df = self.close_rate_df.copy()

        # 時系列を昇順にソート
        macd_tmp_df = macd_tmp_df.sort_values(by="close_timestamp", axis=0, inplace=False).reset_index(level=0, drop=True)

        # MACD計算
        macd_period = {'long' : 26, 'short' : 12}
        signal_period = 9
        macd_tmp_df["macd"] = macd(macd_tmp_df["close_rate"].values.tolist(),  macd_period['short'], macd_period['long'])
        log.info(f"macd calculated : [{macd_tmp_df['macd'].tail(n=1)}]")

        # Pytiの仕様により初回のmacdの計算結果は一つとなる
        macd_tmp_df = pd.concat([self.macd_df, macd_tmp_df.tail(n=1)])

        #-----------------------------------------------------------------
        # シグナル,ヒストグラム計算
        # !!!tradingviewではシグナルの定義がMACDのemaなのでemaで計算!!!
        # https://jp.tradingview.com/scripts/macd/
        # https://jp.tradingview.com/scripts/macd/?solution=43000502344
        #-----------------------------------------------------------------

        # シグナル,ヒストグラムの計算
        if len(macd_tmp_df["macd"]) >= 9:
            macd_tmp_df["signal"] = ema(macd_tmp_df["macd"].values.tolist(), signal_period)
            macd_tmp_df["hist"]   = macd_tmp_df["macd"] - macd_tmp_df["signal"]
            log.info(f"signal  : [{macd_tmp_df['signal'].tail(n=1)}] - hist :[{macd_tmp_df['hist'].tail(n=1)}]")

        self.macd_df = macd_tmp_df.reset_index(level=0, drop=True)

        print('----- test macd_df -----')
        print(self.macd_df)
        print('----- test macd_df -----')
        

        del(macd_tmp_df)

        # ファイル出力(再ロードする際に大きなファイルとなるためデータは昇順だがファイル出力は降順で書き出し　
        self._write_csv_dataframe(self.macd_df, path=MACD_FILE_PATH + self.macd_filename, ascending=False)

        #------------------------------------------
        # ポジション判定
        #------------------------------------------

        # もしヒストグラムが手動で変更された場合はヒストグラムを指定して実行
        # そうでなければデフォルトで実行
        filename = self._get_file_name(path=SYSCONTROL, prefix='hist') 
        if re.search('^hist_', filename):
            hist_manual = int(filename.split('_')[-1])
            log.info(f'hist_thresh is changed at manual. hist_thresh : [{hist_manual}]')
            self.positioner(hist_thresh=hist_manual)
#        else:
#            # デフォルトのヒストグラムの閾値で実行
#            self.positioner()
#
#        # データフレームの行数が27行以上になったら先頭行を削除
#        if len(self.macd_df)       > 26: self.macd_df.drop(index=0, inplace=True)
#        if len(self.close_rate_df) > 26: self.close_rate_df.drop(index=0, inplace=True)
#
#        log.info(f'macd_calculator() done')

        return True




    def positioner(self, n_row=15, macd_thresh=8000, n_macd_ok=5, hist_thresh=3500, hist_zero=200):
        """
        * ポジションを判定する
          ポジションはメインポジション、サポートポジションの２つで管理する
          ポジションは3つ：LONG、SHORT、STAY
          ポジション判定はMACD、シグナルの傾き、ヒストグラムの値で判定する
          MACDが+-閾値以上以下でないとポジション判定を行わない
        * closeレートとMACDが逆行（ダイバージェンス）が起きたらメインポジション、サポートポジション共にSTAY
        * ヒストグラムが+-200未満は0とする
        * param
            n_row      :int (default 5) self.pos_jdg_dfを保持するレコード数(メモリ削減のため)
            macd_thresh:int (default 8000) ポジション判定するためのMACDの閾値※値を上げるほど厳しい閾値になる
#            n_macd_ok  :int (default 5) MACDの閾値をクリアしたcloseデータの個数 ※値をあげるほど厳しい閾値になる
            hist_thresh:int (default 1200) ポジションを判別するためのヒストグラム閾値※値を下げるほど厳しい閾値になる
#            hist_zero  :int (default 200) 指定された値未満は0とみなす※値を下げるほど厳しい閾値になる
        * return
            True:bool (self.pos_jdg_dfにてポジションデータと判定した時刻のタイムスタンプを格納)
            None:bool ポジション判定を行わない場合
        """

        log.info(f'positioner() called')
        #-----------------------------------------------------------------------------------------
        # ※ Pytiの仕様によりcloseのデータが26個で初めて計算されるため、macdが計算されても
        # macdが9個ないとシグナル、ヒストグラムが計算されない
        # シグナル、ヒストグラムも3個必要であるため、MACDの個数が11個必要。11個なければNoneを返す
        #-----------------------------------------------------------------------------------------
        if self.macd_df.count()['macd'] < 11:
            log.info(f"macd data not enough  : [{self.macd_df.count()['macd']}]")
            return None 

        # ポジション判定停止が出ている場合はポジション判定を行わない
        if self.is_exit_file(SYSCONTROL, INIT_POSITION):
            log.info(f'init Judgment position file exists. : [{SYSCONTROL + INIT_POSITION}]')
            self.init_position()
            return None

        # データ取得
        macd_tmp_df = self.macd_df.tail(n=3).copy()
        macd_tmp_df = macd_tmp_df.sort_values(by="close_timestamp", axis=0, inplace=False).reset_index(level=0, drop=True)

        # 一時格納用データフレーム作成
        pos_jdg_tmp_df = pd.DataFrame()

        #-----------------------------------------------------------------------------------------
        # !!! ダイバージェンスが起きている場合はメイン,サポートポジション共に初期化(STAY)にする
        #-----------------------------------------------------------------------------------------
        if self.is_div == True:
            if self.init_position():
                log.info(f"Divergence occur! all position STAY. self.pos_jdg_df: [{self.pos_jdg_df}]")
                return None    

        # MACDの値が閾値を超えていないと判定しない
        if ((macd_tmp_df['macd'] >= macd_thresh).all() == False) and ((macd_tmp_df['macd'] <= -macd_thresh).all() == False):
            log.info(f"macd not satisfy :[{macd_tmp_df['macd']}]")
            return None

        # ヒストグラム
        ht0  =  macd_tmp_df['hist'][0]
        ht1  =  macd_tmp_df['hist'][1]
        ht2  =  macd_tmp_df['hist'][2]

        # MACD
        md0 = macd_tmp_df['macd'][0]
        md1 = macd_tmp_df['macd'][1]
        md2 = macd_tmp_df['macd'][2]

        # シグナル
        sg0 = macd_tmp_df['signal'][0]
        sg1 = macd_tmp_df['signal'][1]
        sg2 = macd_tmp_df['signal'][2]


        # 最新のMACDとシグナルの傾き
        kmd1 = (md1 - md0) / 1
        kmd2 = (md2 - md1) / 1
        ksg1 = (sg1 - sg0) / 1
        ksg2 = (sg2 - sg1) / 1
        

        # 一時格納用データフレーム作成
        pos_jdg_tmp_df = pd.DataFrame([{'main_pos':'STAY','sup_pos':'STAY',
            'jdg_timestamp':datetime.datetime.now(tz=JST)}])  # ポジション計算用データフレーム
        
        #----------------------------------------------------------------
        # パターン1 MACDが閾値クリア、MACDとシグナルの傾きが逆転した場合
        #----------------------------------------------------------------
        # LONG目線(GX間近)
        if (macd_tmp_df['macd'] <= -macd_thresh).all():
            if ((kmd2 > 0) and (ksg2 < 0) and (kmd1 < 0) and (ksg1 < 0)):
                jdg_time                        = datetime.datetime.now(tz=JST)
                pos_jdg_tmp_df['main_pos']      = 'LONG'
                pos_jdg_tmp_df['sup_pos']       = 'LONG'
                pos_jdg_tmp_df['jdg_timestamp'] = jdg_time 
                pos_jdg_tmp_df                  = pd.merge(macd_tmp_df.tail(n=1).reset_index(level=0, drop=True), pos_jdg_tmp_df, left_index=True, right_index=True)
                self.pos_jdg_df                 = pd.concat([pos_jdg_tmp_df, self.pos_jdg_df], ignore_index=True).dropna(how='all')
                log.info(f"pattern 11 position : [{self.pos_jdg_df.tail(n=1)}]")

        # SHORT目線(SHORT間近)
        elif (macd_tmp_df['macd'] >= macd_thresh).all():
            if ((0 < ht2 < hist_thresh) and (kmd5 < 0) and (ksg2 > 0)):
                jdg_time                        = datetime.datetime.now(tz=JST)
                pos_jdg_tmp_df['main_pos']      = 'SHORT'
                pos_jdg_tmp_df['sup_pos']       = 'SHORT'
                pos_jdg_tmp_df['jdg_timestamp'] = jdg_time 
                pos_jdg_tmp_df                  = pd.merge(macd_tmp_df.tail(n=1).reset_index(level=0, drop=True), pos_jdg_tmp_df, left_index=True, right_index=True)
                self.pos_jdg_df                 = pd.concat([pos_jdg_tmp_df, self.pos_jdg_df], ignore_index=True).dropna(how='all')
                log.info(f"pattern 12 position : [{self.pos_jdg_df.tail(n=1)}]")

#        #------------------------------------------------------------------------------
#        # パターン2 ヒストグラムが閾値を超えてないが、MACDが大きく振れGX、DX間近の場合
#        # MACDの閾値は+-8000とする
#        #------------------------------------------------------------------------------
#        # LONG目線(GX間近)
#        elif (macd_tmp_df['macd'] < -8000).all():
#            if ((md2 > md1) and (sg2 < sg1)):
#                jdg_time                        = datetime.datetime.now(tz=JST)
#                pos_jdg_tmp_df['main_pos']      = 'LONG'
#                pos_jdg_tmp_df['sup_pos']       = 'LONG'
#                pos_jdg_tmp_df['jdg_timestamp'] = jdg_time 
#                pos_jdg_tmp_df                  = pd.merge(macd_tmp_df.tail(n=1).reset_index(level=0, drop=True), pos_jdg_tmp_df, left_index=True, right_index=True)
#                self.pos_jdg_df                 = pd.concat([pos_jdg_tmp_df, self.pos_jdg_df], ignore_index=True).dropna(how='all')
#                log.info(f"pattern 21 position : [{self.pos_jdg_df.tail(n=1)}]")
#
#        # SHORT目線(DX間近)
#        elif (macd_tmp_df['macd'] > 8000).all():
#            if ((md2 < md1) and (sg2 > sg1)):
#                jdg_time                        = datetime.datetime.now(tz=JST)
#                pos_jdg_tmp_df['main_pos']      = 'SHORT'
#                pos_jdg_tmp_df['sup_pos']       = 'SHORT'
#                pos_jdg_tmp_df['jdg_timestamp'] = jdg_time 
#                pos_jdg_tmp_df                  = pd.merge(macd_tmp_df.tail(n=1).reset_index(level=0, drop=True), pos_jdg_tmp_df, left_index=True, right_index=True)
#                self.pos_jdg_df                 = pd.concat([pos_jdg_tmp_df, self.pos_jdg_df], ignore_index=True).dropna(how='all')
#                log.info(f"pattern 22 position : [{self.pos_jdg_df.tail(n=1)}]")
#
#        #--------------------------------------------------
#        # パターン3 MACDがシグナル上で反発した場合(一旦やめ
#        #--------------------------------------------------
#        # LONG目線
#        #elif ((abs(ht0) < hist_zero) and (abs(ht1) < hist_zero)):
#
        # 上記以外はSTAY
        else:
            jdg_time                        = datetime.datetime.now(tz=JST)
            pos_jdg_tmp_df['main_pos']      = self.pos_jdg_df['main_pos'][0]
            pos_jdg_tmp_df['sup_pos']       = 'STAY'
            pos_jdg_tmp_df['jdg_timestamp'] = jdg_time 
            pos_jdg_tmp_df                  = pd.merge(macd_tmp_df.tail(n=1).reset_index(level=0, drop=True), pos_jdg_tmp_df, left_index=True, right_index=True)
            self.pos_jdg_df                 = pd.concat([pos_jdg_tmp_df, self.pos_jdg_df], ignore_index=True).dropna(how='all')
            log.info(f"pattern none position : [{self.pos_jdg_df.tail(n=1)}]")
        
        # ファイル出力(時系列的に最新を優先しているの降順で出力)
        self._write_csv_dataframe(self.pos_jdg_df, path=POSITION_FILE_PATH + self.pos_filename, ascending=False, key='jdg_timestamp')
        # メモリ削減のため一番古いデータを削除
        print('---------- pos ----------')
        print(self.pos_jdg_df)
        print('---------- pos ----------')
        if len(self.pos_jdg_df) > n_row: self.pos_jdg_df.drop(index=n_row, inplace=True)
        log.info(f'positioner() done')
        return True



    def test_trader(self, size=0.01, n_pos=1, loss_cut_rate=40000):
        """
        * トレードを行う
        * param
            size:float or int ロット数(default 0.01)
            n_pos:int (default 1) ポジション数。これ以上のポジションは持たない
            loss_cut_rate:int (default 40000) 損切りライン。ただし相場の状況によっては最新レートに近づける,
                              あるいは成行で損切りする場合もある
                              （保有しているポジションとは逆のポジションがpositionerから指示が出た場合など)
        """
        log.info('trader() called')
        timestamp = datetime.datetime.now(tz=JST)
        while True:
            self.load_pos_df() # ロードするタイミングでタイムスタンプはJSTで設定されているため変換する必要無し
            if len(self.pos_jdg_df) == 0:
                # asyncio sleepを使う予定
                time.sleep(10)
                continue

            # ポジション確認
            mpos = self.pos_jdg_df['main_pos'][0]
            spos = self.pos_jdg_df['sup_pos'][0]
            jdg_timestamp = self.pos_jdg_df['jdg_timestamp'][0]
            if timestamp != jdg_timestamp: 
                if mpos == 'LONG' and spos == 'LONG':
                    print('----------------- trader -------------------')
                    print(f'LONG : [{self.pos_jdg_df.head(n=1)}]')
                    print('----------------- trader -------------------')
                    # LONGの関数を呼び出す(コルーチンを使う予定)
                    self.line.send_line_notify(f'ポジション:[{self.pos_jdg_df.head(n=1)}]')

                elif mpos == 'SHORT' and spos == 'SHORT':
                    print('----------------- trader -------------------')
                    print(f'SHORT : [{self.pos_jdg_df.head(n=1)}]')
                    print('----------------- trader -------------------')
                    # SHORTの関数を呼び出す(コルーチンを使う予定)
                    self.line.send_line_notify(f'ポジション:[{self.pos_jdg_df.head(n=1)}]')
                timestamp = jdg_timestamp
            time.sleep(59)
            continue
            # asyncio sleepでも使う予定




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





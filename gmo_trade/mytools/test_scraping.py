import os
import sys
import time
import datetime
from pathlib import Path
import numpy as np
import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import chromedriver_binary
from selenium.webdriver.common.action_chains import ActionChains



def main():
    try:
        app_home = str(Path(__file__).parents[1])
        sys.path.append(app_home)

        # ブラウザ立ち上げ
        options = webdriver.ChromeOptions()
        options.add_argument('--headless')
        driver = webdriver.Chrome(options=options)
        #driver = webdriver.Chrome()
        driver.set_window_size(1200, 900)
        driver.get('https://jp.tradingview.com/chart/wTJWkxIA/')
        time.sleep(20)

        # マウスオーバー
        chart = driver.find_element_by_class_name('chart-gui-wrapper')
        actions = ActionChains(driver)
        actions.move_to_element(chart)
        actions.move_by_offset(310, 100)
        actions.perform()
    except Exception as e:
        print(f'{e}')
        driver.quit()
        sys.exit(1)

    # 初期化
    macd_df = pd.DataFrame()
    stoch_df = pd.DataFrame()

    macd = 0
    pK   = 0

    while True:

        try:
            # CSSセレクタで指定のクラスでelementを取得
            ind_array = driver.find_elements_by_css_selector('.valuesWrapper-2KhwsEwE')
            get_time = datetime.datetime.now()
            
            # リストに変換(MACDはマイナスが全角表記になっているためreplaceで置換しておく
            macd_array  = ind_array[1].text.replace('−', '-').split('\n')
            stoch_array = ind_array[2].text.split('\n')
            
            # 文字列を数値へ変換
            macd_array  = [int(data) for data in macd_array]
            stoch_array = [float(data) for data in stoch_array]
            
            # 取得時刻をリストに追加
            macd_array.append(get_time)
            stoch_array.append(get_time)
            
            # numpyのndarrayに変換
            macd_array  = np.array(macd_array)
            stoch_array = np.array(stoch_array)
            # データフレームとして作成しメンバーに登録(時系列では降順として作成)
            # ただし値が同じであれば作成せずcontinue
            if macd_array[1] == macd:
                time.sleep(10)
                continue

            if stoch_array[0] == pK:
                time.sleep(10)
                continue
            macd_df_tmp   = pd.DataFrame(macd_array.reshape(1, 4), columns=['hist', 'macd', 'signal', 'get_time'])        
            stoch_df_tmp  = pd.DataFrame(stoch_array.reshape(1, 3), columns=['pK', 'pD','get_time'])
            
            # 時系列では降順でマージ
            macd_df = pd.concat([macd_df_tmp, macd_df], ignore_index=True)
            stoch_df = pd.concat([stoch_df_tmp, stoch_df], ignore_index=True)

            print('----- macd -----')
            print(macd_df)
            print('----- stoch -----')
            print(stoch_df)

            # データフレームが5行を超えたら古いものから削除
            if len(macd_df) > 5: macd_df.drop(index=macd_df.index.max(), inplace=True)
            if len(stoch_df) > 5:stoch_df.drop(index=stoch_df.index.max(), inplace=True)

            # 値を更新
            macd = macd_array[1]
            pK   = stoch_array[0]
            time.sleep(10)
        except Exception as e:
            print(f'{e}')
            driver.quit()
            sys.exit(1)
        except KeyboardInterrupt:
            driver.quit()
            sys.exit(1)
        continue

if __name__ == '__main__':
    main()

import sys
import time
from selenium import webdriver
import chromedriver_binary
from selenium.webdriver.common.action_chains import ActionChains

def main(x=205, y=200, headless=False):

    try:
        # ブラウザ起動
        options = webdriver.ChromeOptions()
        if headless == True:
            options.add_argument('--headless')
        driver = webdriver.Chrome(options=options)
        driver.set_window_size(1500, 1000)
        driver.get('https://coin.z.com/jp/member/tools/exchange/#/btc_jpy')
        time.sleep(30)
        
        # iframeで作成されているトレーディングビューのタグを取得
        iframe = driver.find_element_by_css_selector('iframe[id^=tradingview]')
        
        # driverをiframeにスイッチ
        driver.switch_to.frame(iframe)
        
        # 1分足に設定
        driver.find_element_by_css_selector('.value-DWZXOdoK-').click()
        time.sleep(2)
    
        # インジケーターボタンをクリック
        driver.find_element_by_css_selector('#header-toolbar-indicators').click()
        time.sleep(2)
        
        # MACDを設定
        driver.find_element_by_css_selector('.tv-search-row__input.js-input-control').send_keys('MACD')
        time.sleep(2)
        driver.find_element_by_css_selector('.tv-insert-study-item__title').click()
        driver.find_element_by_css_selector('.tv-search-row__input-reset.js-reset-button').click()
        
        # ストキャスティクスを設定
        driver.find_element_by_css_selector('.tv-search-row__input.js-input-control').send_keys('ストキャスティクス')
        time.sleep(2)
        driver.find_element_by_xpath("//div[@class='tv-insert-study-item__title-text' and @title='ストキャスティクス']").click()
        time.sleep(2)
        
        # インジケーター検索ウィンドウを削除
        driver.find_element_by_css_selector('.tv-dialog__close.js-dialog__close').click()
        time.sleep(2)
        
        # ストキャスティクスのパラメーター設定(リストの0は大本のチャート、1はMACDにあたる)
        driver.find_elements_by_css_selector('.pane-legend-icon.apply-common-tooltip.format')[2].click()
        time.sleep(2)
        
        # %Kをスムージングで3に設定するため数値を上げるボタンを2回クリックする(リストの0は期間、2は%Dにあたる）
        driver.find_elements_by_css_selector('.tv-ticker__btn.tv-ticker__btn--up')[1].click()
        driver.find_elements_by_css_selector('.tv-ticker__btn.tv-ticker__btn--up')[1].click()
        time.sleep(2)
        # OKボタンをクリック
        driver.find_element_by_css_selector('._tv-button.ok').click()
        time.sleep(2)
    
    
        # マウスオーバー
        # GMOのサイトの仕様なのか、時間が経過して次のローソクが出ると
        # マウスの位置が合っていてもインジケーター、レート等の値が取得できないため
        # 最新のcloseしたデータを取得するためには毎回マウスオーバーをする必要がある
        while True:
            #chart = driver.find_element_by_css_selector('.chart-markup-table')
#            chart = driver.find_element_by_css_selector('#root')
            chart = driver.find_element_by_css_selector('.chart-container-border')
            actions = ActionChains(driver)
            actions.move_to_element(chart)
            #actions.move_by_offset(205, 200)
            actions.move_by_offset(x, y)
            actions.perform()
    
            # closeの時刻を取得
            close_time = driver.find_element_by_xpath("//span[@class='inner-2FptJsfC-' and contains(text(), 'UTC')]")
    
            # 各種値を取得
            elements = driver.find_elements_by_css_selector('.pane-legend-item-value-wrap')
            print('----------')
            print(close_time.text)
            for element in elements:
                print(element.text)
       
            time.sleep(5)
        # driverを元に戻す(必要であれば)
        #driver.switch_to.default_content()
    except Exception as e:
        print(e)
        driver.quit()
        sys.exit(1)
    except KeyboardInterrupt:
        driver.quit()
        sys.exit(1)


if __name__ == '__main__':
    if len(sys.argv) > 1:
        x=int(sys.argv[1])
        y=int(sys.argv[2])
        main(x=x, y=y)
    else:
        main()


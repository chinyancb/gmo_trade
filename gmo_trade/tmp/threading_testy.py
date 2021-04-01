import threading
import logging
import time
import random

logging.basicConfig(level=logging.DEBUG, format='%(threadName)s: %(message)s')



def worker():
    # thread の名前を取得
    logging.debug('start')
    time.sleep(5)
    logging.debug('end')


def err_f(x=20):
    
    while True:
        try:
            y = random.randrange(5)
            logging.debug(f' {x}/{y} ')
            x/y
            time.sleep(5)
        except Exception as e:
            print('err_f restart')
            continue

def thred_main1():
    
    while True:
        worker()




def thred_main2():

    while True:
        err_f()


if __name__ == '__main__':
     t1 = threading.Thread(target=thred_main1, name='main1')
     t2 = threading.Thread(target=thred_main2, name='main2')

     t1.start()
     t2.start()

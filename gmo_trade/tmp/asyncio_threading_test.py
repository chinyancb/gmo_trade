import asyncio
import time
import concurrent.futures




async def asy_func_for(y, x=10):

    print('-- Called asy_func_for() --')
    print(f'-- asy_func_for x={x} y={y} --')
    for i in range(0, x):
        print(f'-- asy_func_for i={i} --')
        print(f'-- asy_func_for {y} sec sleep start --')
        await asyncio.sleep(y)
        print(f'-- asy_func_for {y} sec sleep end --')
    
        
    print('-- FINISH asy_func_for() --')
    return True

async def asy_func_for2(y, x=10):

    print('-- Called asy_func_for2() --')
    print(f'-- asy_func_for2 x={x} y={y} --')
    for i in range(0, x):
        print(f'-- asy_func_for2 i={i} --')
        print(f'-- asy_func_for2 {y} sec sleep start --')
        await asyncio.sleep(y)
        print(f'-- asy_func_for2 {y} sec sleep end --')
    
        
    print('-- FINISH asy_func_for2() --')
    return True


async def asy_err_func(y, x=10):
    print('-- Called asy_err_func() --')
    print(f'-- asy_err_func x={x} y={y} --')
    for i in range(x, -1, -1):
        print(f'-- asy_err_func i={i} --')
        print(f'-- asy_err_func x/i={x/i} --')
        print(f'-- asy_err_func {y} sec sleep start --')
        await asyncio.sleep(y)
        print(f'-- asy_err_func {y} sec sleep end --')
    
        
    print('-- FINISH asy_err_func() --')
    return True



async def main():
    #cors = [asy_func_for(2, 10), asy_func_for2(1, 20), asy_err_func(1, 10)]
    cors = [asy_func_for(2, 10), asy_func_for2(1, 20)]
    await asyncio.gather(*cors)

def th_worker(x=2):
    print('-- Called th_worker() --')
    print(f'-- th_worker x={x} --')
    while True:
        time.sleep(x)
        print('!!! th_worker !!!')
        

if __name__ == '__main__':
    t1 = threading.Thread(target=th_worker, kwargs={'x':1})
    t2 = threading.Thread(target=asyn_main)
    
    t1.start()
    t2.start()


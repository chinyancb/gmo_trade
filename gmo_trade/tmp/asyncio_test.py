import asyncio
import sys

async def func1(x, y):

    print(f'----- func1 called -----')
    print(f'--- func1 x={x} y={y} ---')
    for i in range(0, x):
        print(f'- func1 -- {i} -')
        print(f'- func1 -- sleep start {y} sec-')
        await asyncio.sleep(y)
        print(f'- func1 -- sleep end {y} sec-')

    print(f'----- func1 end -----')

    return True



async def func2(x, y):

    print(f'----- func2 called -----')
    print(f'--- func2 x={x} y={y} ---')
    for i in range(0, x):
        print(f'- func2 -- {i} -')
        print(f'- func2 -- sleep start {y} sec-')
        await asyncio.sleep(y)
        print(f'- func2 -- sleep end {y} sec-')

    print(f'----- func2 end -----')

    return True


async def func_while(y, x=20):
    print(f'----- func_while called -----')
    print(f'--- func_while x={x} y={y} ---')
    while x > 0:
        print(f'- func_while -- {x} -')
        print(f'- func_while -- sleep start {y} sec-')
        await asyncio.sleep(y)
        print(f'- func_while -- sleep end {y} sec-')
        x -= 1

    print(f'----- func_while end -----')
    return True

async def while_forever(x):

    print(f'----- while_forever called -----')
    print(f'--- while_forever x={x} ---')

    while True:
        print(f'- while_forever -- sleep start {x} sec-')
        await asyncio.sleep(x)
        print(f'- while_forever -- sleep end {x} sec-')


async def err_func(x, y):
    print(f'----- err_func called -----')
    print(f'--- err_func x={x} y={y} ---')

    for i in range(x,-1, -1):
        print(f'- err_func -- {i} -')
        print(f'- err_func -- sleep start {y} sec-')
        print(f'- err_func y/i = {y/i} -')
        y/i
        await asyncio.sleep(y)
        print(f'- err_func -- sleep end {y} sec-')

    return True



async def main():
    tsk_func1 = asyncio.create_task(func1(10, 2))
    tsk_func2 = asyncio.create_task(func2(5, 3))
#    tsk_func_while = asyncio.create_task(func_while(1))
    tsk_func_forever = asyncio.create_task(while_forever(1))
    tsk_err_func = asyncio.create_task(err_func(5, 3))
#    await asyncio.gather(
#        tsk_func_while,
#        tsk_func1, 
#        tsk_func2,
#        tsk_err_func,
#        return_exceptions=True
#        )

    try:
        result = await asyncio.gather(
#            tsk_func_while,
            #tsk_func_forever,
            asyncio.to_thread(while_forever, 1),
            tsk_func1, 
            tsk_func2,
            tsk_err_func,
            return_exceptions=True
            )
    except Exception as e:
        print(f'in try : exception is [{e}]')

    result='hello world'
    print(f'result is [{result}]')


if __name__ == '__main__':
    asyncio.run(main())

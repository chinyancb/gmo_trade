import asyncio


async def say(msg='hello_world', x=5, sleep_time=3):

    print('----- say() called -----')
    for i in range(0, x):
        print(msg)
        await asyncio.sleep(sleep_time)

    return True

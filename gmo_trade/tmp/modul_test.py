import asyncio
import hello_world


async def f_for(x, y=1):

    print('----- f_for() called -----')
    for i in range(0, x):
        print(f'--- i = {i} ---')
        print(f' f_for sleep {y} sec start')
        await asyncio.sleep(y)
        print(f' f_for sleep {y} sec finish')
    
    print('----- f_for() end -----')
    return True



async def main():
    result = await asyncio.gather(
        f_for(5),
        hello_world.say('test hi!', 5, 1),
        #hello_world.say(5, 1), <- gatherの中でタスク化されるため、デフォルト引数を省略すると反映されない
        return_exceptions=False
        )
    print(f' result -> {result}')

if __name__ == '__main__':
    asyncio.run(main())

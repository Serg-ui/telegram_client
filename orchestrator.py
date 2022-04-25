import asyncio
import json
import logging
import os
from rabbit import get_connection, send_message_to_queue
import const
from multiprocessing import Process


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def run_client(msg_data):
    command = f'python telegram_client.py {msg_data["app_id"]} {msg_data["app_hash"]} {msg_data["phone"]}'
    os.system(command)


class Orchestrator:

    def __init__(self):
        self.running_clients = dict()

    async def listen_rabbit(self):
        connection = await get_connection()
        channel = await connection.channel()
        await channel.set_qos(prefetch_count=100)

        queue = await channel.declare_queue(const.TO_ORCHESTRATOR_QUEUE_NAME, durable=True)

        async with queue.iterator() as queue_iter:
            async for message in queue_iter:
                async with message.process():
                    await self.messaging(message)


    async def messaging(self, msg):

        msg_data = json.loads(msg.body.decode())
        if msg_data['type'] == 'start_client':
            logger.info(f'Оркестратор: получен запрос на создание клиента {msg_data["phone"]}')

            client = self.running_clients.get(msg_data['phone'], None)
            if not client:
                self.running_clients[msg_data['phone']] = (False, None)

            await self.check_client(msg_data)

        if msg_data['type'] == const.CLIENT_CHECK_STATUS:
            if msg_data['text'] == 'waiting_code':
                self.running_clients[msg_data['phone']] = (False, msg_data['pid'])
                logger.info(f'Оркестратор: Клиент {msg_data["phone"]} ждет кода подтверждения')

            if msg_data['text'] == 'running':

                self.running_clients[msg_data['phone']] = (True, msg_data['pid'])
                print(self.running_clients)
                logger.info(f'Оркестратор: Клиент {msg_data["phone"]} запущен')

    async def check_client(self, msg):
        """ Запрос состояния у клиента """

        phone = msg['phone']

        data = {
            'type': const.CLIENT_CHECK_STATUS
        }

        await send_message_to_queue(json.dumps(data), f'{const.TO_TELEGRAM_QUEUE_NAME}{phone.replace("+", "")}')
        logger.info(f'Оркестратор: Запрос состояния у клиента {phone}')
        await self.accept_client_status(msg)

    async def accept_client_status(self, msg):
        """ После запроса check_client ждем n секунд, если клиент не ответил создаем его """
        phone = msg['phone']
        for i in range(5):
            print(i)
            if self.running_clients[phone][0]:
                logger.info(f'Оркестратор: Клиент {phone} ответил, что запущен')
                return
            await asyncio.sleep(1)

        # Клиент не ответил, запускаем
        # todo Правильно настроить процессы
        p = Process(target=run_client, args=(msg,))
        p.start()
        self.running_clients[msg['phone']] = (True, p.pid)
        logger.info(f'Оркестратор: клиент {phone} запущен')
        #p.join()
        #await self.test()


    async def test(self):
        data = {
            'type': const.CLIENT_CHECK_STATUS
        }
        await send_message_to_queue(json.dumps(data), f'{const.TO_TELEGRAM_QUEUE_NAME}79112370642')
        logger.info(f'Оркестратор: Запрос состояния у клиента 79112370642')


if __name__ == '__main__':
    orchestrator = Orchestrator()
    loop = asyncio.get_event_loop()
    loop.create_task(orchestrator.listen_rabbit())
    loop.run_forever()

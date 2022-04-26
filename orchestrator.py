import asyncio
import json
import logging
import os
from rabbit import get_connection, send_message_to_queue
import const
from multiprocessing import Process


logging.basicConfig(level=logging.INFO, format='%(asctime)s %(module)s %(levelname)s:%(message)s')
logger = logging.getLogger(__name__)


def run_client(msg_data):
    try:
        command = f'python telegram_client.py {msg_data["app_id"]} {msg_data["app_hash"]} {msg_data["phone"]}'
        os.system(command)
    except Exception as e:
        logger.error(e, exc_info=True)


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
                    loop.create_task(self.messaging(message))

    async def messaging(self, msg):
        """ Обработка входящих сообщений из rabbit """

        msg_data = json.loads(msg.body.decode())
        if msg_data['type'] == 'start_client':
            logger.info(f'получен запрос на создание клиента {msg_data["phone"]}')

            await self.check_client(msg_data, start=True)

        # Клиент ответил на запрос о его статусе
        if msg_data['type'] == const.CLIENT_CHECK_STATUS:

            self.running_clients[msg_data['phone']] = {'status': msg_data['status'], 'pid': msg_data['pid']}
            logger.info(f'Клиент {msg_data["phone"]} запущен, pid - {msg_data["pid"]}')

    async def check_client(self, msg, start=False):
        """ Запрос состояния у клиента, Если start=True, запускаем клиента в случае, если он не ответил """

        phone = msg['phone']

        data = {
            'type': const.CLIENT_CHECK_STATUS
        }

        await send_message_to_queue(json.dumps(data), f'{const.TO_TELEGRAM_QUEUE_NAME}{phone.replace("+", "")}')
        logger.info(f'Запрос состояния у клиента {phone}')

        if start:
            client_status = await self.accept_client_status(msg)
            if not client_status:
                # Клиент не ответил, запускаем
                # todo Правильно настроить процессы
                p = Process(target=run_client, args=(msg,))
                p.start()
                logger.info(f'стартовал клиента {phone}')
                # await asyncio.sleep(5)
                # await self.check_client(msg)

    async def accept_client_status(self, msg):
        """ После запроса check_client ждем n секунд, если клиент не ответил создаем его """
        phone = msg['phone']
        logger.info(f'Ожидание ответа клиента {phone}')
        for i in range(5):
            client = self.running_clients.get(phone, None)
            if client:
                logger.info(f'Клиент {phone} ответил, что уже запущен')
                return True
            await asyncio.sleep(1)

        return False


if __name__ == '__main__':
    orchestrator = Orchestrator()
    loop = asyncio.get_event_loop()
    loop.create_task(orchestrator.listen_rabbit())
    loop.run_forever()

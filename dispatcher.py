import argparse
import asyncio
import logging

import const
from rabbit import get_connection, send_message_to_queue
import json
import random
import string

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(module)s %(levelname)s:%(message)s')
logger = logging.getLogger(__name__)


class Dispatcher:

    def __init__(self, app_id, app_hash, phone):
        self.app_id = app_id
        self.app_hash = app_hash
        self.phone = phone
        self.q_from_telegram = f'{const.FROM_TELEGRAM_QUEUE_NAME}{phone.replace("+", "")}'
        self.q_to_telegram = f'{const.TO_TELEGRAM_QUEUE_NAME}{phone.replace("+", "")}'
        self.client_is_ready = False

    async def start_telegram_client(self):
        """ Отправляет команду оркестратору на созлание телеграм клиента """

        data = {
            'type': 'start_client',
            'app_id': self.app_id,
            'app_hash': self.app_hash,
            'phone': self.phone
        }
        await send_message_to_queue(json.dumps(data), const.TO_ORCHESTRATOR_QUEUE_NAME)
        logger.info('Отправлен запрос оркестратору на создание клиента')

    async def receive_message_from_telegram(self):
        """ Получает входящее сообщение из telegram """

        connection = await get_connection()
        channel = await connection.channel()
        await channel.set_qos(prefetch_count=100)

        queue = await channel.declare_queue(self.q_from_telegram, durable=True)

        async with queue.iterator() as queue_iter:
            async for message in queue_iter:
                async with message.process():
                    loop.create_task(self.messages_from_telegram(message))

    async def messages_from_telegram(self, msg):
        """ Определение типа сообщения от telegram """

        msg_data = json.loads(msg.body.decode())
        if msg_data['type'] == const.MESSAGE:
            logger.info(f'Диспетчер {self.phone}: Получено сообщение от {msg_data["user"]}')
            await self.reply(msg_data)
        if msg_data['type'] == const.CONFIRM_CODE:
            await self.get_code(msg_data)
        if msg_data['type'] == const.CLIENT_IS_READY:
            self.client_is_ready = True
            logger.info(f'Диспетчер {self.phone}: Получено уведомление о готовности клиента')
            # loop.create_task(self.send_message_manually())  # Если нужно отправить сообщение через консоль

    async def reply(self, msg):
        """ Для тестирования. Отвечает адресату путем отправки сообщ в очередь на отправку в telegram """

        letters = string.ascii_lowercase
        random_str = ''.join(random.choice(letters) for _ in range(15))

        msg['type'] = 'message'
        msg['text'] = f'Тест диспетчера {random_str}'

        await asyncio.sleep(const.TELEGRAM_REPLAY_DELAY)
        await send_message_to_queue(json.dumps(msg), self.q_to_telegram)
        logger.info(f'Диспетчер {self.phone}: Отправлено сообщение сообщение к {msg["user"]}')

    async def get_code(self, msg):
        """ Получение у юзера кода подтверждения аутентификации в телеграм"""
        code = await loop.run_in_executor(None, input, msg['text'])
        data = {
            'type': const.CONFIRM_CODE,
            'text': code
        }
        await send_message_to_queue(json.dumps(data), self.q_to_telegram)
        logger.info(f'Диспетчер {self.phone}: Отправлен код подтверждения {code}')

    async def send_message_manually(self):
        """ Ручное отправление сообщения через input """

        while True:
            input_data = await loop.run_in_executor(None, input, 'Отправить сообщение (stop для отмены). Через запятую user, текст: ')
            if input_data == 'stop':
                break

            try:
                phone, text = input_data.split(',')
            except ValueError:
                print('user + сообщение через запятую!')
                continue

            data = {
                'type': const.MESSAGE,
                'user': phone.strip(),
                'text': text.strip()
            }

            await send_message_to_queue(json.dumps(data), self.q_to_telegram)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='client data')
    parser.add_argument('id', type=int, help='client id')
    parser.add_argument('hash', type=str, help='client hash')
    parser.add_argument('phone', type=str, help='client phone')
    args = parser.parse_args()

    dispatcher = Dispatcher(args.id, args.hash, args.phone)

    loop = asyncio.get_event_loop()
    loop.create_task(dispatcher.receive_message_from_telegram())
    loop.create_task(dispatcher.start_telegram_client())
    loop.run_forever()

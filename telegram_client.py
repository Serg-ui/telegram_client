import argparse
import json
import logging
import os
from telethon import TelegramClient, events
import asyncio
import const
from rabbit import get_connection, send_message_to_queue


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class Telegram:
    def __init__(self, app_id, app_hash, phone, session_name=None):
        if not session_name:
            session_name = f'session_{phone.replace("+", "")}'
        self.session_name = session_name
        self.app_id = app_id
        self.app_hash = app_hash
        self.phone = phone
        self.client = TelegramClient(self.session_name, self.app_id, self.app_hash)
        self.is_login = False
        self.q_from_telegram = f'{const.FROM_TELEGRAM_QUEUE_NAME}{phone.replace("+", "")}'
        self.q_to_telegram = f'{const.TO_TELEGRAM_QUEUE_NAME}{phone.replace("+", "")}'

    async def login(self):
        """ Аутентификация """

        await self.client.connect()
        if not await self.client.is_user_authorized():
            await self.client.send_code_request(self.phone)
            data = {
                'type': const.CONFIRM_CODE,
                'text': 'Введите код подтверждения: '
            }

            await send_message_to_queue(json.dumps(data), self.q_from_telegram)
            logger.info('Отправлен запрос кода диспетчеру')
        else:
            await self.im_ready()

    async def accept_code(self, msg):
        """ Отправка к telegram кода подтверждения """

        logger.info(f'Получен код от диспетчера {msg["text"]}')
        await self.client.sign_in(self.phone, msg['text'])
        await self.im_ready()

    async def check_status(self):
        logger.info('Получен запрос статуса от оркестратора')
        data = {
            'type': const.CLIENT_CHECK_STATUS,
            'phone': self.phone,
            'pid': os.getpid(),
            'text': None
        }
        if self.is_login:
            data['text'] = 'running'  # запущен
        else:
            data['text'] = 'running'  # ждет от пользователя кода подтверждения

        await send_message_to_queue(json.dumps(data), self.q_from_telegram)
        print(data)

    async def im_ready(self):
        """ Запуск прослушивания, отправка уведомления диспетчеру о готовности """

        if self.is_login:
            logger.error('Сюда не должно попадать, когда клиент уже запущен')

        self.is_login = True
        a_loop = asyncio.get_running_loop()
        a_loop.create_task(self.listen_telegram())

        data = {
            'type': const.CLIENT_IS_READY
        }

        await send_message_to_queue(json.dumps(data), self.q_from_telegram)
        logger.info('Отправлено уведомление о готовности')

    async def listen_telegram(self):
        """ Прослушивает телеграм на входящие сообщения, отправляет полученные в диспетчер """

        client = self.client

        @client.on(events.NewMessage)
        async def listen_t(event):
            sender = await event.get_sender()

            user = sender.phone if sender.username is None else sender.username
            user = sender.id if user is None else user

            data = {
                'type': const.MESSAGE,
                'user': user,
                'text': event.raw_text
            }
            logger.info(f'Получено сообщение от {user}')
            await send_message_to_queue(json.dumps(data), self.q_from_telegram)

    async def listen_rabbit(self):
        """ Получение входящих сообщений из очереди """
        connection = await get_connection()

        queue_name = self.q_to_telegram

        channel = await connection.channel()

        await channel.set_qos(prefetch_count=100)

        queue = await channel.declare_queue(queue_name, durable=True)
        async with queue.iterator() as queue_iter:
            async for message in queue_iter:
                async with message.process():
                    await self.messages_from_rabbit(message)


    async def messages_from_rabbit(self, msg):
        """ Определение типа сообщения, которое поступило из rabbitmq """

        msg_data = json.loads(msg.body.decode())

        if msg_data['type'] == const.MESSAGE:  # это для отправки в телеграм
            await self.send(msg_data)

        if msg_data['type'] == const.CONFIRM_CODE:  # это код подтверждения аутентификации
            await self.accept_code(msg_data)

        if msg_data['type'] == const.CLIENT_CHECK_STATUS:  # это проверка статуса клиента
            await self.check_status()

    async def send(self, msg):
        if not self.is_login:
            logger.error('Получен запрос на отправку, когда клиент не авторизован')
            return
        try:
            await self.client.send_message(msg['user'], msg['text'])
            logger.info(f'Отправлено сообщение к {msg["user"]}')
        except ValueError as e:
            logger.error(e)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='client data')
    parser.add_argument('id', type=int, help='client id')
    parser.add_argument('hash', type=str, help='client hash')
    parser.add_argument('phone', type=str, help='client phone')
    args = parser.parse_args()

    telegram = Telegram(args.id, args.hash, args.phone)

    loop = asyncio.get_event_loop()
    loop.create_task(telegram.login())
    loop.create_task(telegram.listen_rabbit())

    loop.run_forever()

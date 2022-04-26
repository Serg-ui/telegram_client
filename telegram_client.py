import argparse
import json
import logging
import os
import traceback

from telethon import TelegramClient, events
import asyncio

from telethon.errors import PhoneCodeInvalidError, ApiIdInvalidError

import const
from rabbit import get_connection, send_message_to_queue
import enum


class ClientStatus(enum.Enum):
    disconnected = 0
    connected = 1
    authorized = 2


logging.basicConfig(level=logging.ERROR, format='%(asctime)s %(module)s %(levelname)s:%(message)s')
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
        self.status = ClientStatus.disconnected
        self.q_from_telegram = f'{const.FROM_TELEGRAM_QUEUE_NAME}{phone.replace("+", "")}'
        self.q_to_telegram = f'{const.TO_TELEGRAM_QUEUE_NAME}{phone.replace("+", "")}'

    async def login(self):
        """ Аутентификация """

        await self.client.connect()
        self.status = ClientStatus.connected

        if not await self.client.is_user_authorized():

            try:
                await self.client.send_code_request(self.phone)
                data = {
                    'type': const.CONFIRM_CODE,
                    'text': 'Введите код подтверждения: '
                }

                await send_message_to_queue(json.dumps(data), self.q_from_telegram)
                logger.info('Отправлен запрос кода диспетчеру')
            except ApiIdInvalidError as e:
                logger.error(e, exc_info=True)
                return

        else:
            await self.im_ready()

    async def accept_code(self, msg):
        """ Отправка к telegram кода подтверждения """

        logger.info(f'Получен код от диспетчера {msg["text"]}')

        try:
            await self.client.sign_in(self.phone, msg['text'])
            await self.im_ready()
        except PhoneCodeInvalidError as e:
            logger.error(e)
            data = {
                'type': const.CONFIRM_CODE,
                'text': 'Код неверный, введите еще раз: '
            }

            await send_message_to_queue(json.dumps(data), self.q_from_telegram)

        # todo
        except:
            logger.error("uncaught exception: %s", traceback.format_exc())

    async def check_status(self):
        logger.info('Получен запрос статуса от оркестратора')

        data = {
            'type': const.CLIENT_CHECK_STATUS,
            'phone': self.phone,
            'pid': os.getpid(),
            'status': self.status.name
        }

        await send_message_to_queue(json.dumps(data), const.TO_ORCHESTRATOR_QUEUE_NAME)

    async def im_ready(self):
        """ Запуск прослушивания, отправка уведомления диспетчеру о готовности """

        if self.status == ClientStatus.authorized:
            logger.error('Сюда не должно попадать, когда клиент уже запущен')

        self.status = ClientStatus.authorized
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

        @client.on(events.NewMessage(incoming=True))
        async def listen_t(event):
            try:
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

            # todo
            except:
                logger.error("uncaught exception: %s", traceback.format_exc())

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
                    loop.create_task(self.messages_from_rabbit(message))

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
        """ Отправка сообщения адресату в telegram """

        if self.status != ClientStatus.authorized:
            logger.error('Получен запрос на отправку сообщения, когда клиент еще не авторизован')
            return
        try:
            await self.client.send_message(msg['user'], msg['text'])
            logger.info(f'Отправлено сообщение к {msg["user"]}')

        # todo
        except:
            logger.error("uncaught exception: %s", traceback.format_exc())


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

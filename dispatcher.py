#!/usr/bin/env python3

import asyncio
import const
from rabbit import get_connection, send_message_to_queue
import json
import random
import string


class Dispatcher:

    def __init__(self, phone):
        self.phone = phone
        self.q_from_telegram = f'{const.FROM_TELEGRAM_QUEUE_NAME}{phone.replace("+", "")}'
        self.q_to_telegram = f'{const.TO_TELEGRAM_QUEUE_NAME}{phone.replace("+", "")}'

    async def receive_message_from_telegram(self):
        """ Получает входящее сообщение из telegram """

        connection = await get_connection()
        channel = await connection.channel()
        await channel.set_qos(prefetch_count=100)

        queue = await channel.declare_queue(
            self.q_from_telegram,
            auto_delete=False, durable=True
        )

        async with queue.iterator() as queue_iter:
            async for message in queue_iter:
                async with message.process():

                    await self.messages_from_telegram(message.body.decode())

    async def messages_from_telegram(self, msg):
        """ Определение типа сообщения от telegram """

        msg = json.loads(msg)
        if msg['type'] == const.MESSAGE:
            await self.reply(msg)
        if msg['type'] == const.CONFIRM_CODE:
            await self.get_code(msg)

    async def reply(self, msg):
        """ Для тестирования. Отвечает адресату путем отправки сообщ в очередь на отправку в telegram """

        letters = string.ascii_lowercase
        random_str = ''.join(random.choice(letters) for _ in range(15))

        msg['type'] = 'message'
        msg['text'] = f'Тест диспетчера {random_str}'

        await asyncio.sleep(const.TELEGRAM_REPLAY_DELAY)
        await send_message_to_queue(json.dumps(msg), self.q_to_telegram)

    async def get_code(self, msg):
        """ Получение у юзера кода подтверждения аутентификации в телеграм"""
        loop = asyncio.get_running_loop()
        code = await loop.run_in_executor(None, input, msg['text'])
        data = {
            'type': const.CONFIRM_CODE,
            'text': code
        }
        await send_message_to_queue(json.dumps(data), self.q_to_telegram)

    async def send_message_manually(self):
        """ Ручное отправление сообщения через input """
        loop = asyncio.get_running_loop()

        while True:
            input_data = await loop.run_in_executor(None, input, 'Отправить сообщение. Через запятую телефон, текст: ')
            if input_data == 'stop':
                break

            try:
                phone, text = input_data.split(',')
            except ValueError:
                await loop.run_in_executor(None, print, 'телефон + сообщение через запятую!')
                continue

            data = {
                'type': 'message',
                'user': phone.strip(),
                'text': text.strip()
            }

            await send_message_to_queue(json.dumps(data), f'{const.TO_TELEGRAM_QUEUE_NAME}{self.phone}')

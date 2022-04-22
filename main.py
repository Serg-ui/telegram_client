from dispatcher import Dispatcher
from telegram_client import Telegram
import asyncio
import argparse


# 9721250
# 98f55f13bc93e71d032bf46752417db0
# +79211872891

parser = argparse.ArgumentParser(description='client data')
parser.add_argument('id', type=int, help='client id')
parser.add_argument('hash', type=str, help='client hash')
parser.add_argument('phone', type=str, help='client phone')
args = parser.parse_args()


telegram = Telegram(args.id, args.hash, args.phone)
dispatcher = Dispatcher(args.phone)

loop = asyncio.get_event_loop()
loop.create_task(telegram.login())
loop.create_task(dispatcher.receive_message_from_telegram())
loop.create_task(telegram.listen_rabbit())

loop.run_forever()

import const
import aio_pika


async def get_connection():
    return await aio_pika.connect_robust(
        f"amqp://{const.RABBITMQ_USER}:{const.RABBITMQ_PASSWORD}@{const.RABBITMQ_HOST}:{const.RABBITMQ_PORT}/",
    )


async def send_message_to_queue(msg, queue_name):
    """ Отправляет сообщение в очередь """

    connection = await get_connection()

    async with connection:
        routing_key = queue_name

        channel = await connection.channel()

        await channel.default_exchange.publish(
            aio_pika.Message(body=msg.encode()),
            routing_key=routing_key,
        )

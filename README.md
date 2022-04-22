Начальный вариант работы с telegram
Необходимы библиотеки: telethon, aio_pika

Запуск telegram - из консоли telegram_client.py id hash phone
Запуск диспетчера - из консоли dispatcher.py phone 

Затем начинает работать прослушка telegram и rabbitmq.
Диспетчер принимает поступившее сообщение из telegram и отвечает адресату с задержкой в n секунд.
Так же можно отправить сообщение адресату вручную через консоль когда клиент отправил уведомление о готовности.

RabbitMQ я зупускал через docker:
`docker run -d --hostname my-rabbit -p 5672:5672  --name some-rabbit -e RABBITMQ_DEFAULT_USER=guest -e RABBITMQ_DEFAULT_PASS=guest rabbitmq:3-management`
Константы описаны в const.py

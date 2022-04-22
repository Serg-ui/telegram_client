RABBITMQ_USER = 'guest'
RABBITMQ_PASSWORD = 'guest'
RABBITMQ_HOST = 'localhost'
RABBITMQ_PORT = '5672'

TO_TELEGRAM_QUEUE_NAME = 'to_telegram'
FROM_TELEGRAM_QUEUE_NAME = "from_telegram"

TELEGRAM_REPLAY_DELAY = 1

# Типы сообщений
MESSAGE = 'message'  # Обычное сообщение
CONFIRM_CODE = 'confirm_code'  # код аутентификации
CLIENT_IS_READY = 'client_is_ready'  # телеграм клиент запущен а авторизован

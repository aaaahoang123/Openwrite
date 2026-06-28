import sys
import os

from .config import AdapterConfig, ConfigError
from .chat_config import ChatAdapterConfig, ConfigError as ChatConfigError
from .runner import SmartStoryAdapterRunner, ChatTurnAdapterRunner


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "chat-turn":
        try:
            config = ChatAdapterConfig.from_env()
        except ChatConfigError as exc:
            print(f"ChatConfigError: {exc}", file=sys.stderr)
            return 78
        return ChatTurnAdapterRunner(config).run()
    else:
        try:
            config = AdapterConfig.from_env(os.environ)
        except ConfigError as exc:
            print(f"ConfigError: {exc}", file=sys.stderr)
            return 78
        return SmartStoryAdapterRunner(config).run()

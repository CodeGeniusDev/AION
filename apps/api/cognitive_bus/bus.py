from cognitive_bus.schema import CognitiveMessage


class CognitiveBus:
    """In-memory placeholder for future agent-to-agent message routing."""

    def __init__(self) -> None:
        self.messages: list[CognitiveMessage] = []

    def publish(self, message: CognitiveMessage) -> CognitiveMessage:
        self.messages.append(message)
        return message


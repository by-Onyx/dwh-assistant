"""Session memory combines a rolling summary and a bounded window of turns."""
from langchain_core.messages import AIMessage, HumanMessage


def excerpt(text, limit):
    if len(text) <= limit:
        return text
    half = (limit - 3) // 2
    return text[:half] + " … " + text[-half:]


class DialogueMemory:
    """Store completed turns only. A failed summary leaves session state intact."""

    def __init__(self, window_turns=2):
        if type(window_turns) is not int or not 1 <= window_turns <= 8:
            raise ValueError("Размер окна должен быть целым числом от 1 до 8")
        self.window_turns = window_turns
        self.clear()

    def clear(self):
        self.summary = ""
        self.turns = []

    def messages(self):
        return [message for pair in self.turns for message in pair]

    def append(self, question, answer, summarize):
        # Also bound the total size of historical messages in the answer prompt.
        limit = 2400 // self.window_turns
        pair = (HumanMessage(content=excerpt(question, limit)),
                AIMessage(content=excerpt(answer, limit)))
        if len(self.turns) == self.window_turns:
            oldest = self.turns[0]
            summary = summarize.invoke({"summary": self.summary, "turn": list(oldest)}).strip()
            if not summary:
                raise ValueError("Модель вернула пустую сводку диалога")
            self.summary = excerpt(summary, 1000)
            self.turns.pop(0)
        self.turns.append(pair)

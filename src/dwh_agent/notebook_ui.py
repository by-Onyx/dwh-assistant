"""Two independent notebook outputs: chat and service CELL."""
import json
import ipywidgets as widgets

class NotebookChat:
    def __init__(self):
        self.agent = None
        self.on_close = lambda: None
        self.service_output = widgets.Output(layout={"border": "1px solid #ccc", "max_height": "280px", "overflow": "auto"})
        self.chat_output = widgets.Output(layout={"border": "1px solid #aaa", "min_height": "140px"})
        self.input = widgets.Textarea(placeholder="Сообщение; /memory, /forget поле, /clear или /exit", layout={"width": "100%", "height": "90px"})
        self.send = widgets.Button(description="Отправить", button_style="primary", disabled=True)
        self.send.on_click(self._submit)
        self.chat_box = widgets.VBox([self.chat_output, self.input, self.send])

    def service(self, event):
        self.service_output.append_stdout(json.dumps(event, ensure_ascii=False) + "\n")

    def attach(self, agent, on_close=None):
        self.agent = agent
        if on_close is not None:
            self.on_close = on_close
        self.send.disabled = False

    def _submit(self, button):
        message = self.input.value.strip()
        if not message or self.agent is None:
            return
        self.input.value = ""
        self.send.disabled = True
        closed = False
        try:
            if message == "/memory":
                self.service({"event": "memory_view", **self.agent.memory.load_memory_variables()})
            elif message == "/clear":
                self.agent.memory.forget()
                self.service({"event": "profile_cleared", "user_id": self.agent.memory.user_id})
            elif message.startswith("/forget "):
                self.agent.memory.forget(message.split(maxsplit=1)[1])
                self.service({"event": "fact_forgotten", **self.agent.memory.load_memory_variables()})
            elif message == "/exit":
                self.on_close()
                closed = True
                self.service({"event": "chat_closed", "memory": "сохранена"})
            elif message.startswith("/"):
                self.service({"event": "unknown_command", "commands": ["/memory", "/forget name", "/clear", "/exit"]})
            else:
                self.chat_output.append_stdout("Вы: " + message + "\n")
                result = self.agent.ask(message)
                self.chat_output.append_stdout("Ассистент: " + result["answer"] + "\n\n")
        except Exception as exc:
            self.service({"event": "error", "type": type(exc).__name__, "message": str(exc)})
        finally:
            self.send.disabled = closed

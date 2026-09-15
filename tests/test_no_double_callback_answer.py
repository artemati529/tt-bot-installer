"""delete_user_callback отвечал на callback-query дважды: один раз безусловно
в начале функции (`await q.answer()`), и ещё раз в каждой ветке через
`cb_answer(q, ...)` — который несёт нужный текст тоста ("Отменено",
"Удаляю…"). Первый вызов был лишним хвостом: Telegram принимает только один
answerCallbackQuery на запрос, второй вызов ничего не даёт, кроме путаницы
в коде.

По всему файлу было ещё 9 мест с сырым `await q.answer()`
вместо `cb_answer(q)` — разница реальная: сырой `q.answer()` в сети с заминками
бросает исключение прямо в хендлер (→ `log_unhandled_error` → лишняя
"Внутренняя ошибка" в чат), а `cb_answer` эту заминку гасит и повторяет без
текста. Заменены все 9 на `cb_answer(q)`; `cb_answer`'s собственный внутренний
фолбэк (единственное законное место для сырого `q.answer()`) не трогаем.
"""
import ast
import inspect


def test_delete_user_callback_answers_exactly_once_per_step(
    bot_tt, allowed_callback_update, context, run_async
):
    for data in ("delask:alice", "del2:alice", "delcancel:alice"):
        update = allowed_callback_update(data)
        run_async(bot_tt.delete_user_callback(update, context))
        assert update.callback_query.answer.await_count == 1, data


def test_no_raw_q_answer_calls_outside_cb_answer(bot_tt):
    """Единственное легитимное место для `q.answer()` напрямую — сам cb_answer."""
    tree = ast.parse(inspect.getsource(bot_tt))
    offenders = []

    class Visitor(ast.NodeVisitor):
        def __init__(self):
            self.stack = []

        def visit_FunctionDef(self, node):
            self.stack.append(node.name)
            self.generic_visit(node)
            self.stack.pop()

        def visit_AsyncFunctionDef(self, node):
            self.stack.append(node.name)
            self.generic_visit(node)
            self.stack.pop()

        def visit_Call(self, node):
            if (
                isinstance(node.func, ast.Attribute)
                and node.func.attr == "answer"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "q"
            ):
                caller = self.stack[-1] if self.stack else "<module>"
                if caller != "cb_answer":
                    offenders.append((caller, node.lineno))
            self.generic_visit(node)

    Visitor().visit(tree)
    assert offenders == []

from types import FunctionType

from gitfive.lib.objects import TMPrinter

import trio


class TrioProgress(trio.abc.Instrument):
    def __init__(self, message: str, target_func: FunctionType, total: int, to_sum=1, tmprinter=TMPrinter()):
        self.tmprinter = tmprinter
        self.message = message
        self.target_func_name = target_func.__name__
        self.total = total
        self.current = 0
        self.to_sum = to_sum

    def task_exited(self, task):
        if task.name.split('.')[-1] == self.target_func_name:
            if self.current < self.total:
                self.current += self.to_sum
            else:
                self.current = self.total
        if self.current >= self.total:
            self.tmprinter.clear()
        else:
            self.tmprinter.out(f"[~] {self.message} {self.current} / {self.total} ({round(self.current / self.total * 100, 2)} %)")

class TrioAliveProgress(trio.abc.Instrument):
    def __init__(self, target_func: FunctionType, to_sum: int, bar):
        self.target_func_name = target_func.__name__
        self.to_sum = to_sum
        self.bar = bar
    
    def task_exited(self, task):
        if task.name.split('.')[-1] == self.target_func_name:
            self.bar(self.to_sum)
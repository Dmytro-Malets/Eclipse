class NoAPIError(Exception):
    def __init__(self, *args):
        self.message = args[0] if args else None

    def __str__(self):
        return f'{self.message}' if self.message else 'NoAPIError'


class MissingEnvVariableError(Exception):
    def __init__(self, *args):
        self.message = args[0] if args else None

    def __str__(self):
        return f'{self.message}' if self.message else 'MissingEnvVariableError'
class TemplateProxy(object):
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs


def render_template(*args, **kwargs):
    return TemplateProxy(*args, **kwargs)

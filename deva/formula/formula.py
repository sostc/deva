from outliers import smirnov_grubbs as grubbs
import pandas as pd
from .log import log


def detect_outlier(num_list, alpha=0.05):
    """异常值检测"""
    data = pd.Series(num_list)
    return grubbs.min_test_outliers(data, alpha)


def translate(x, to='en'):
    """翻译函数to = 'zh-CN'"""
    from googletrans import Translator
    translator = Translator(service_urls=[
        'translate.google.com',
        'translate.google.jp',
    ])
    try:
        return translator.translate(x, dest=to).text
    except Exception as e:
        e >> log
        return x

#  from cocoNLP import extractor

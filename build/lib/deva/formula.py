from outliers import smirnov_grubbs as grubbs
import pandas as pd

def detect_outlier(num_list, alpha=0.05):
    """异常值检测"""
    data = pd.Series(num_list)
    return grubbs.min_test_outliers(data,alpha)

def translate(x,to='en'):
    """翻译函数to = 'zh-CN'"""
    from textblob import TextBlob
    try:
        return TextBlob(x).translate(to=to).raw
    except:
        return x

# from cocoNLP import extractor
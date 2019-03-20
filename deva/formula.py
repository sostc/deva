from outliers import smirnov_grubbs as grubbs
import pandas as pd

def detect_outlier(num_list,alpha=0.05):
    data = pd.Series(num_list)
    return grubbs.min_test_outliers(data,alpha)
    

from textblob import TextBlob

def translate(x,to='en'):
    """ to = 'zh-CN'"""
    return TextBlob(x).translate(to=to).raw
    
from cocoNLP import extractor
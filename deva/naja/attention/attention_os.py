# 兼容 shim - 实际实现已移至 attention/os/attention_os.py
from .os.attention_os import *  # noqa: F401,F403
from .os.attention_os import get_attention_os, AttentionOS, AttentionKernel  # noqa: F401

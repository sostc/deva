# 兼容 shim - 实际实现已移至 attention/os/os_kernel.py
from .os.os_kernel import *  # noqa: F401,F403
from .os.os_kernel import OSAttentionKernel, AttentionKernel  # noqa: F401

import asyncio
import os
import time
import pickle
import aiofiles
from deva.sources import from_textfile
from deva import write_to_file

class SharedQueueService:
    def __init__(self, queue_name: str) -> None:
        """初始化共享队列服务
        
        Args:
            queue_name (str): 队列名称标识符，用于标识要连接的共享队列
        """
        self.queue_name = queue_name
        self.data_file = f"{queue_name}_data.txt"  # 数据存储文件
        self.flag_file = f"{queue_name}_service_flag"  # 服务状态标识文件
        self.server_process = None
        self.server_ready = asyncio.Event()

    async def start(self) -> None:
        """启动或连接共享队列服务"""
        if not await self._is_service_running():
            print(f"未找到运行中的{self.queue_name}服务，启动新服务...")
            await self._start_service()
        else:
            print(f"检测到运行中的{self.queue_name}服务，尝试连接...")
            await self._connect_to_service()

    async def _is_service_running(self) -> bool:
        """检查目标服务是否正在运行"""
        try:
            async with aiofiles.open(self.flag_file, 'rb') as f:
                service_info = pickle.loads(await f.read())
                return service_info.get("running", False) and service_info.get("queue_name") == self.queue_name
        except (FileNotFoundError, EOFError):
            return False

    async def _start_service(self) -> None:
        """启动新的共享队列服务进程"""
        print(f"启动{self.queue_name}服务进程（{os.getpid()}）...")
        await self._create_flag_file()
        await self._service_function()

    async def _connect_to_service(self) -> None:
        """连接到已存在的共享队列服务"""
        print(f"正在连接到{self.queue_name}共享队列服务...")
        await self._listen_for_messages()

    async def _create_flag_file(self) -> None:
        """创建服务运行状态标识文件"""
        service_info = {
            "running": True,
            "pid": os.getpid(),
            "queue_name": self.queue_name
        }
        async with aiofiles.open(self.flag_file, 'wb') as f:
            await f.write(pickle.dumps(service_info))

    async def _service_function(self) -> None:
        """服务进程主循环"""
        print(f"{self.queue_name}服务进程启动，进程 ID: {os.getpid()}")
        self.server_ready.set()

        try:
            # 监听数据文件变化
            async for message in from_textfile(self.data_file):
                print(f"{self.queue_name}服务接收到: {message}")
        except asyncio.CancelledError:
            print(f"{self.queue_name}服务收到退出信号")
        finally:
            await self._broadcast_exit()

    async def _broadcast_exit(self) -> None:
        """广播服务退出信号"""
        print(f"{self.queue_name}服务广播退出信号...")
        await write_to_file(self.data_file, "exit")

    async def stop(self) -> None:
        """停止共享队列服务"""
        if self.server_process:
            print(f"停止{self.queue_name}服务进程...")
            self.server_process.cancel()
            await self.server_process
            await self._delete_flag_file()
            print(f"{self.queue_name}服务进程（{self.server_process.pid}）已停止。")
        else:
            print(f"没有运行中的{self.queue_name}服务进程。")

    async def _delete_flag_file(self) -> None:
        """删除服务运行状态标识文件"""
        try:
            os.remove(self.flag_file)
        except FileNotFoundError:
            pass

    async def send_message(self, message: str) -> None:
        """向共享队列发送消息"""
        await write_to_file(self.data_file, message)

    async def _listen_for_messages(self) -> None:
        """监听共享队列消息"""
        print(f"进程 {os.getpid()} 正在监听{self.queue_name}共享队列...")
        
        try:
            async for message in from_textfile(self.data_file):
                print(f"进程 {os.getpid()} 从{self.queue_name}接收到消息: {message}")
                
                if message == "exit":
                    print(f"进程 {os.getpid()} 接收到退出信号，停止监听{self.queue_name}...")
                    break
        except Exception as e:
            print(f"进程 {os.getpid()} 连接{self.queue_name}异常: {str(e)}")
        finally:
            print(f"进程 {os.getpid()} 已断开与{self.queue_name}的连接")

async def main() -> None:
    """主程序入口"""
    service = SharedQueueService(queue_name="shared_queue")

    await service.start()

    try:
        while True:
            await service.send_message("Hello from main process!")
            await asyncio.sleep(5)
    except asyncio.CancelledError:
        print("主进程收到退出信号")
    finally:
        await service.stop()
        print("主进程退出")


if __name__ == "__main__":
    asyncio.run(main())


# server.py - 共享内存创建者
import numpy as np
import multiprocessing.shared_memory as sm

# 创建共享内存块
size = 10
shm = sm.SharedMemory(create=True, size=size * 8)  # 10 个 float64 (8字节)
array = np.ndarray((size,), dtype=np.float64, buffer=shm.buf)
print(shm)
# 初始化数据
array[:] = np.arange(size)

print("共享内存创建完成，数据:", array)
input("按回车退出，保持共享内存活跃...")  # 进程不退出，保持共享
shm.close()
shm.unlink()  # 释放共享内存


# client.py - 读取共享内存
import numpy as np
import multiprocessing.shared_memory as sm

shm = sm.SharedMemory(name="psm_9983b07e")  # 替换为正确的共享内存名称
array = np.ndarray((10,), dtype=np.float64, buffer=shm.buf)

print("客户端读取共享数据:", array)

shm.close()  # 关闭但不释放共享内存
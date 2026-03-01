"""Naja 命令行入口

使用方法:
    python -m deva.naja
    python -m deva.naja --port 8080
"""

import argparse


def main():
    parser = argparse.ArgumentParser(description="Naja 管理平台")
    parser.add_argument("--port", type=int, default=8080, help="Web 服务器端口")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="绑定地址")
    args = parser.parse_args()
    
    from .web_ui import run_server
    run_server(port=args.port, host=args.host)


if __name__ == "__main__":
    main()

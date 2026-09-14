"""SSH ProxyCommand：把 stdio 转发到 HTTP 代理，用于「只能走代理」的网络。

背景：公司网络直连 github.com:22 / :443 都不通，必须经 HTTP 代理；
Git 版本自带的 connect.exe 在当前安装里没有，所以用 Python 实现一个。

用法（~/.ssh/config）：
    Host github.com
        HostName ssh.github.com
        Port 443
        User git
        ProxyCommand "D:/.../python.exe" "D:/.../ssh_proxy.py" %h %p
        ProxyUseFdpass no

脚本只做 TCP 转发，不接触任何凭据——认证仍由 ssh 用你的私钥完成。
"""

import os
import socket
import sys

PROXY = os.environ.get("BSP_SSH_PROXY", "http://10.71.251.52:3128")
CONNECT_TIMEOUT = 30
BUFFER = 32768


def parse_proxy(url):
    url = url.strip()
    if "://" in url:
        url = url.split("://", 1)[1]
    if "@" in url:                       # 形如 user:pass@host:port
        creds, url = url.rsplit("@", 1)
    else:
        creds = None
    if ":" in url:
        host, port = url.rsplit(":", 1)
        port = int(port)
    else:
        host, port = url, 8080
    return host, port, creds


def connect_via_proxy(target_host, target_port):
    proxy_host, proxy_port, creds = parse_proxy(PROXY)
    sock = socket.create_connection((proxy_host, proxy_port), CONNECT_TIMEOUT)
    request = [f"CONNECT {target_host}:{target_port} HTTP/1.1",
               f"Host: {target_host}:{target_port}"]
    if creds:
        import base64
        token = base64.b64encode(creds.encode()).decode()
        request.append(f"Proxy-Authorization: Basic {token}")
    request.append("")
    request.append("")
    sock.sendall("\r\n".join(request).encode())

    # 读响应头，直到空行
    response = b""
    while b"\r\n\r\n" not in response:
        chunk = sock.recv(4096)
        if not chunk:
            raise RuntimeError(f"代理提前断开，已收到: {response[:200]!r}")
        response += chunk
    status_line = response.split(b"\r\n", 1)[0].decode(errors="replace")
    if " 200" not in status_line:
        raise RuntimeError(f"代理拒绝连接: {status_line}")
    return sock


def pump(sock):
    """stdin/stdout 与 socket 之间双向转发。

    Windows 的 select() 只能用于 socket，不能用于管道，
    所以这里用两个线程做阻塞读写（各自负责一个方向）。
    """
    import threading

    stdin_fd = sys.stdin.buffer.fileno() if hasattr(sys.stdin, "buffer") \
        else sys.stdin.fileno()
    stdout_fd = sys.stdout.buffer.fileno() if hasattr(sys.stdout, "buffer") \
        else sys.stdout.fileno()

    def stdin_to_sock():
        while True:
            try:
                data = os.read(stdin_fd, BUFFER)
            except OSError:
                break
            if not data:
                break
            try:
                sock.sendall(data)
            except OSError:
                break
        # 输入结束：关掉写方向，让 ssh 感知对端 EOF
        try:
            sock.shutdown(socket.SHUT_WR)
        except OSError:
            pass

    reader = threading.Thread(target=stdin_to_sock, daemon=True)
    reader.start()

    while True:
        try:
            data = sock.recv(BUFFER)
        except OSError:
            break
        if not data:
            break
        try:
            os.write(stdout_fd, data)
        except OSError:
            break

    try:
        sock.close()
    except OSError:
        pass


def main():
    if len(sys.argv) < 3:
        print("用法: ssh_proxy.py <host> <port>", file=sys.stderr)
        return 2
    host, port = sys.argv[1], int(sys.argv[2])
    try:
        sock = connect_via_proxy(host, port)
    except Exception as exc:                                  # noqa: BLE001
        print(f"ssh_proxy: 连接 {host}:{port} 失败: {exc}", file=sys.stderr)
        return 1
    pump(sock)
    return 0


if __name__ == "__main__":
    sys.exit(main())

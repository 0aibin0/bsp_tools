"""版本更新检查 + 从 GitHub 下载并自替换重启。

三条路：
- **检查**：优先 `GET /repos/{repo}/releases/latest`（能拿到 release 说明和附件），
  没有 release 就退回 tags API，只比版本号。
- **下载**：release 附件里的 exe（找不到 exe 就退而求其次找 zip，都没有就从
  仓库 `bsp_tools/dist` 取提交好的 exe）。落盘先叫 `DisplayTools.exe.new`
  （运行中的 exe 锁着，不能直接覆盖），换名后就是正式的 `DisplayTools.exe`，
  **不带版本号**。
- **自替换重启**：打包运行时，下载完退出旧进程 → 旧 exe 改名成
  `DisplayTools.exe.old` → 新文件就位 → 启动新版本。新版本启动 3 秒后自己把
  `.old` 删掉（万一新版起不来，.old 还在，改回名字就能用）。
  换名用 PowerShell -EncodedCommand（UTF-16LE base64），避开批处理文件的编码坑。

刻意不自动检查、不弹模态窗口，只在用户点「检查更新」时跑；失败一律当成
"没查到"，不让网络问题干扰调试。

私有仓库：未带 token 的 API 调用返回 404（GitHub 对私有仓库不区分"不存在"和
"没权限"）。在本机数据文件的 config 段里加一条 "update_token": "ghp_xxx" 即可；
下载附件也会走带 token 的 API 地址（见 download_asset）。
"""

import base64
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request

from PyQt5.QtCore import QThread, pyqtSignal

import app_config
import theme

DEFAULT_REPO = "0aibin0/bsp_tools"
TIMEOUT = 8
DOWNLOAD_TIMEOUT = 30
CHUNK = 64 * 1024
_UA = "DisplayTools-update-check"

_VERSION_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")


def repo_slug():
    return (app_config.config().get("update_repo", "") or DEFAULT_REPO).strip()


def repo_url():
    return "https://github.com/{}".format(repo_slug())


def releases_url():
    return "{}/releases".format(repo_url())


def release_page_url(tag):
    return "{}/releases/tag/{}".format(repo_url(), tag) if tag else releases_url()


def api_url():
    return "https://api.github.com/repos/{}/tags".format(repo_slug())


def release_api_url():
    return "https://api.github.com/repos/{}/releases/latest".format(repo_slug())


def contents_url(path, ref=""):
    url = "https://api.github.com/repos/{}/contents/{}".format(repo_slug(), path)
    if ref:
        url += "?ref={}".format(ref)
    return url


def _token():
    return (app_config.config().get("update_token", "") or "").strip()


def _headers(accept="application/vnd.github+json"):
    headers = {"User-Agent": _UA, "Accept": accept}
    token = _token()
    if token:
        headers["Authorization"] = "Bearer {}".format(token)
    return headers


class _AuthSafeRedirect(urllib.request.HTTPRedirectHandler):
    """跳转到别的域名时摘掉 Authorization。

    GitHub 的附件地址会 302 到带签名的 S3 地址，那个 URL 本身已经带鉴权，
    再挂一个 Authorization 头会被 S3 拒（400 Only one auth mechanism allowed）。
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new is not None:
            new.remove_header("Authorization")
        return new


_OPENER = urllib.request.build_opener(_AuthSafeRedirect)


def _get(url, timeout=TIMEOUT, accept="application/vnd.github+json"):
    request = urllib.request.Request(url, headers=_headers(accept))
    with _OPENER.open(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8", "replace"))


def parse_version(text):
    """'v3.1.2' -> (3, 1, 2)；解析不了返回 None。"""
    match = _VERSION_RE.match((text or "").strip())
    if not match:
        return None
    return tuple(int(part) for part in match.groups())


def is_newer(candidate, current=None):
    """candidate 是否比当前版本新。"""
    new = parse_version(candidate)
    old = parse_version(current or theme.APP_VERSION)
    if new is None or old is None:
        return False
    return new > old


def fetch_tags(timeout=TIMEOUT):
    """取远端 tag 名列表；任何异常都往上抛，由调用方决定怎么提示。"""
    payload = _get(api_url(), timeout)
    return [item.get("name", "") for item in payload if isinstance(item, dict)]


def latest_tag(timeout=TIMEOUT):
    """返回 (最新版本号, 全部版本列表)。"""
    versions = [v for v in (parse_version(name) for name in fetch_tags(timeout))
                if v is not None]
    if not versions:
        return None, []
    newest = max(versions)
    return "v{}.{}.{}".format(*newest), sorted(versions, reverse=True)


def fetch_latest_release(timeout=TIMEOUT):
    """取最新 release：返回 dict（tag / name / notes / assets / html_url）。

    release 不存在（仓库只用 tag）时返回 None，由调用方退回 tags API。
    """
    payload = _get(release_api_url(), timeout)
    if not isinstance(payload, dict):
        return None
    assets = []
    for item in payload.get("assets") or []:
        if not isinstance(item, dict):
            continue
        assets.append({
            "name": item.get("name") or "",
            "size": int(item.get("size") or 0),
            "url": item.get("url") or "",
            "browser_download_url": item.get("browser_download_url") or "",
        })
    return {
        "tag": payload.get("tag_name") or "",
        "name": payload.get("name") or "",
        "notes": payload.get("body") or "",
        "assets": assets,
        "html_url": payload.get("html_url") or "",
    }


def pick_asset(assets):
    """挑一个能下载的附件：优先 DisplayTools 的 exe，其次任意 exe，再退到 zip。"""
    def by_name(suffix, keyword=None):
        for asset in assets or []:
            name = (asset.get("name") or "").lower()
            if not name.endswith(suffix):
                continue
            if keyword and keyword not in name:
                continue
            return asset
        return None

    return (by_name(".exe", "displaytools") or by_name(".exe")
            or by_name(".zip") or (assets[0] if assets else None))


def default_download_name(asset=None, tag=""):
    """下载到本地的文件名：**固定 DisplayTools.exe，不带版本号**。

    版本号在 exe 内部的 theme.APP_VERSION 和 git tag 里，文件名里不再重复一份；
    正在运行的自己改名/覆盖会失败，所以落盘时先加 .new 后缀（见 staged_path），
    由更新脚本在旧进程退出后换成正式名字。
    """
    name = os.path.basename((asset or {}).get("name") or "")
    if not name.lower().endswith(".exe"):
        name = DOWNLOAD_NAME
    return name


#: 正式文件名（不带版本号）
DOWNLOAD_NAME = "DisplayTools.exe"
#: 落盘的临时后缀：运行中的 exe 锁着，先下成 .new，重启时再换名
STAGED_SUFFIX = ".new"


def running_exe_path():
    """当前运行的 exe 路径；从源码跑（python mainwindow.py）时返回 None。"""
    if getattr(sys, "frozen", False):
        try:
            return os.path.abspath(sys.executable)
        except Exception:                                   # noqa: BLE001
            return None
    return None


def can_self_update():
    """能不能自动替换并重启（只有打包成 exe 运行时才行）。"""
    return running_exe_path() is not None


def staged_path(asset=None, tag=""):
    """新版本先落到哪儿。

    打包运行时：跟当前 exe 同目录，名字是 `DisplayTools.exe.new`（当前 exe 被
    锁着，不能直接覆盖；也不改叫带版本号的名字——换名后就是正式的
    DisplayTools.exe）。从源码跑：落到数据目录的 DisplayTools.exe，不自动替换。
    """
    name = default_download_name(asset, tag)
    target = running_exe_path()
    if target:
        return os.path.join(os.path.dirname(target), name + STAGED_SUFFIX)
    return os.path.join(download_dir(), name)


def old_backup_path():
    """旧版本备份路径（自动更新时把旧 exe 改名成它，起不来能换回去）。"""
    target = running_exe_path()
    return target + ".old" if target else ""


def swap_command(new_path, target_exe=None, pid=None, wait_seconds=90,
                 expected_size=0):
    """生成"等旧进程退出 → 换文件 → 启动新版本"的 PowerShell 命令。

    为什么用 PowerShell -EncodedCommand 而不是写个 .bat：批处理文件的编码
    容易和 cmd 的代码页打架（路径里有中文就废），而 -EncodedCommand 传的是
    UTF-16LE base64，绕开整个编码问题，也不额外留文件。

    expected_size > 0 时脚本会先核对新文件大小：对不上就直接启动旧版本退出，
    不给"半截 exe 换上去 → 启动弹 DLL 报错"留任何机会（Python 侧已经校验过一次，
    这里是第二道保险）。
    """
    target_exe = target_exe or running_exe_path()
    if not target_exe:
        raise ValueError("只有打包成 exe 运行时才能自动替换")
    pid = pid or os.getpid()
    backup = target_exe + ".old"
    script = """
$ErrorActionPreference = 'SilentlyContinue'
$target = {target}
$new    = {new}
$backup = {backup}
$oldPid = {pid}
$expected = {expected}
# 0) 新文件不完整就别动旧版本（第二道保险）
if (($expected -gt 0) -and ((Get-Item -LiteralPath $new).Length -ne $expected)) {{
    Start-Process -FilePath $target
    exit 0
}}
# 1) 等旧进程退出（最多 {wait} 秒）
for ($i = 0; $i -lt {loops}; $i++) {{
    if (-not (Get-Process -Id $oldPid -ErrorAction SilentlyContinue)) {{ break }}
    Start-Sleep -Milliseconds 500
}}
# 2) 旧版留一份 .old（下次更新时再清掉），新文件就位
if (Test-Path -LiteralPath $backup) {{ Remove-Item -LiteralPath $backup -Force }}
if (Test-Path -LiteralPath $target) {{
    Rename-Item -LiteralPath $target -NewName (Split-Path -Leaf $backup) -Force
}}
$moved = $false
for ($i = 0; $i -lt 20; $i++) {{
    Move-Item -LiteralPath $new -Destination $target -Force -ErrorAction SilentlyContinue
    if (Test-Path -LiteralPath $target) {{ $moved = $true; break }}
    Start-Sleep -Milliseconds 500
}}
# 3) 换不上去就把旧版放回去，别让用户没有 exe 可用
if (-not $moved) {{
    if ((-not (Test-Path -LiteralPath $target)) -and (Test-Path -LiteralPath $backup)) {{
        Rename-Item -LiteralPath $backup -NewName (Split-Path -Leaf $target) -Force
    }}
    Start-Process -FilePath $target
    exit 0
}}
Start-Sleep -Milliseconds 800
Start-Process -FilePath $target
""".format(target=_ps_quote(target_exe),
           new=_ps_quote(new_path),
           backup=_ps_quote(backup),
           pid=int(pid),
           expected=int(expected_size or 0),
           wait=int(wait_seconds),
           loops=int(wait_seconds * 2))
    return script


def _ps_quote(text):
    """PowerShell 单引号字符串：内部的单引号写成两个。"""
    return "'{}'".format(str(text).replace("'", "''"))


def start_swap(new_path, target_exe=None, pid=None, wait_seconds=90,
               expected_size=0):
    """后台启动更新脚本（脱离当前进程，父进程退出后它继续跑）。

    返回启动命令的列表（给日志/自测用）；起不来的话抛异常，由调用方提示。
    """
    script = swap_command(new_path, target_exe, pid, wait_seconds, expected_size)
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    exe = "powershell.exe"
    flags = 0
    if os.name == "nt":
        # CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP：不弹黑框，父进程退出也不影响
        # 子进程。注意**不能用 DETACHED_PROCESS**（0x8）：实测那样起的 powershell
        # 会立刻带着 rc=0 退出、脚本一行都不执行（没有控制台时连 -EncodedCommand
        # 都不跑），换文件就静默失败。
        flags = 0x08000000 | 0x00000200
    args = [exe, "-NoProfile", "-ExecutionPolicy", "Bypass",
            "-EncodedCommand", encoded]
    subprocess.Popen(args, close_fds=True, creationflags=flags,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL)
    return args


def cleanup_old_backup():
    """启动成功后清掉上一次更新留下的 .old（在安全窗口之后调用）。

    返回被删掉的路径（没有就返回 ""）。
    """
    path = old_backup_path()
    if not path or not os.path.isfile(path):
        return ""
    try:
        os.remove(path)
        return path
    except Exception:                                       # noqa: BLE001
        return ""


# 仓库里放打包产物的目录 / exe 路径（提交进仓库的就是最新版本的 exe，
# 所以没有 Release 附件时直接从仓库拿这个文件）
DIST_DIRS = ("bsp_tools/dist", "dist")
EXE_CANDIDATES = ("bsp_tools/dist/DisplayTools.exe", "dist/DisplayTools.exe",
                  "DisplayTools.exe")


def _asset_from_entry(entry, from_repo=True):
    """把 contents API 的一个条目转成附件结构。"""
    if not isinstance(entry, dict) or not entry.get("name"):
        return None
    asset = {
        "name": entry.get("name") or "",
        "size": int(entry.get("size") or 0),
        "url": entry.get("url") or "",
        "browser_download_url": entry.get("download_url")
                                or entry.get("browser_download_url") or "",
        "path": entry.get("path") or "",
    }
    if from_repo:
        asset["from_repo"] = True
    return asset


def _pick_from_listing(entries):
    """从目录列表里挑 exe：优先不带版本号的 DisplayTools.exe，否则第一个 exe。"""
    exes = [item for item in (entries or [])
            if isinstance(item, dict)
            and str(item.get("name", "")).lower().endswith(".exe")]
    if not exes:
        return None
    plain = [item for item in exes
             if str(item.get("name", "")).lower() == "displaytools.exe"]
    return _asset_from_entry((plain or exes)[0])


def repo_asset(tag, timeout=TIMEOUT):
    """从仓库里找该版本的可执行文件。

    仓库里是把打包好的 exe 一起提交的（bsp_tools/dist/），所以即使没建
    Release，也能"直接从仓库下载最新版本"：先列 dist 目录挑 exe，再退回
    几个常见路径。列不到就返回 None（由调用方提示去打开发布页）。
    """
    for path in DIST_DIRS:
        try:
            payload = _get(contents_url(path, tag), timeout)
        except Exception:                                   # noqa: BLE001
            continue
        if isinstance(payload, list):
            asset = _pick_from_listing(payload)
            if asset is not None:
                return asset
    for path in EXE_CANDIDATES:
        try:
            payload = _get(contents_url(path, tag), timeout)
        except Exception:                                   # noqa: BLE001
            continue
        asset = _asset_from_entry(payload)
        if asset is not None:
            return asset
    return None


def download_target(asset):
    """按附件来源给出 (地址, 请求头)。

    - Release 附件：带 token 时用 API 地址（browser_download_url 要浏览器登录态），
      Accept: application/octet-stream；
    - 仓库文件：用 contents API 地址配 Accept: application/vnd.github.raw，
      公开仓库不带 token 也能下，私有仓库带 token。
    """
    asset = asset or {}
    token = _token()
    if asset.get("from_repo"):
        url = asset.get("url") or asset.get("browser_download_url") or ""
        headers = {"User-Agent": _UA, "Accept": "application/vnd.github.raw"}
    else:
        url = asset.get("browser_download_url") or ""
        headers = {"User-Agent": _UA, "Accept": "application/octet-stream"}
        if token:
            url = asset.get("url") or url
    if token:
        headers["Authorization"] = "Bearer {}".format(token)
    return url, headers


def download_dir():
    """下载目录：优先 exe / 源码目录（和配置、收藏放一起），不可写就退到下载文件夹。"""
    base = app_config.data_dir()
    if os.access(base, os.W_OK):
        return base
    fallback = os.path.join(os.path.expanduser("~"), "Downloads")
    return fallback if os.path.isdir(fallback) else os.path.expanduser("~")


def download_asset(asset, dest_path, progress=None, timeout=DOWNLOAD_TIMEOUT,
                   expected_size=0, validate=True):
    """把附件下载到 dest_path（先写 .part，**校验通过后**才改名）。

    progress: 可选回调 progress(已下载字节, 总字节, 总字节为 0 表示未知)。
    返回实际落盘路径；异常照旧往上抛。

    下载完整性在改名之前就把关，三道：
      1. Content-Length 和实收字节数；
      2. 附件元数据里声明的大小（GitHub 会给出真实大小）；
      3. validate 时再做一次 exe 体检（MZ 头 + 大小下限）。
    任何一条不过 → 删掉 .part 并报错，**绝不把一个截断的文件变成 .new**。
    截断的 exe 一旦被换成正式版本，新程序启动只会弹一个
    "Error loading Python DLL" 的 DLL 报错，用户根本不知道发生了什么
    （公司代理会悄悄断连接，实测能复现）。
    """
    url, headers = download_target(asset)
    if not url:
        raise ValueError("附件没有可下载地址")
    # 附件元数据里声明的大小也要对得上（GitHub 的 contents/release 接口都会给），
    # 调用方没显式传 expected_size 时就用它兜底
    expected = expected_size or asset_size(asset)

    directory = os.path.dirname(os.path.abspath(dest_path))
    if directory:
        os.makedirs(directory, exist_ok=True)
    tmp = dest_path + ".part"
    done = 0
    request = urllib.request.Request(url, headers=headers)
    try:
        with _OPENER.open(request, timeout=timeout) as response:
            total = int(response.headers.get("Content-Length") or 0)
            with open(tmp, "wb") as handle:
                while True:
                    chunk = response.read(CHUNK)
                    if not chunk:
                        break
                    handle.write(chunk)
                    done += len(chunk)
                    if callable(progress):
                        progress(done, total)
    except Exception:
        # 半截文件（.part）别留在 exe 目录里碍事
        _remove_quietly(tmp)
        raise
    if total and done != total:
        _remove_quietly(tmp)
        raise DownloadError(
            "下载不完整：收到 {} 字节，应该 {} 字节（网络/代理中途断了）".format(done, total))
    if expected and done != expected:
        _remove_quietly(tmp)
        raise DownloadError(
            "下载不完整：收到 {} 字节，附件声明 {} 字节".format(done, expected))
    if validate and dest_path.lower().endswith(".exe"):
        ok, detail = verify_update_file(tmp, expected)
        if not ok:
            _remove_quietly(tmp)
            raise DownloadError("下载的文件不可用：{}".format(detail))
    os.replace(tmp, dest_path)
    return dest_path


def _remove_quietly(path):
    try:
        if path and os.path.isfile(path):
            os.remove(path)
    except Exception:                                       # noqa: BLE001
        pass


class DownloadError(Exception):
    """下载结果不能用（不完整 / 不是可执行文件）。"""


def verify_update_file(path, expected_size=0):
    """换文件之前的最后一道关：确认这是个完整、像样的 exe。

    返回 (ok, 说明)。这里挡住的都是实测踩过的坑：
    - 代理把连接掐了 → 文件只有一半 → 换上去新版本启动弹 DLL 报错；
    - 下到了 HTML 错误页（某些代理会返回 200 + 错误页）→ 不是 MZ 开头。
    """
    if not path or not os.path.isfile(path):
        return False, "文件不存在：{}".format(path or "-")
    size = os.path.getsize(path)
    if expected_size and size != expected_size:
        return False, "大小不符：实得 {} 字节 / 应有 {} 字节".format(size, expected_size)
    if size < 1024 * 1024:
        return False, "文件太小（{} 字节），不像完整的安装包".format(size)
    try:
        with open(path, "rb") as handle:
            head = handle.read(2)
    except Exception as exc:                                # noqa: BLE001
        return False, "读不出文件头：{}".format(type(exc).__name__)
    if head != b"MZ":
        return False, "不是 Windows 可执行文件（缺少 MZ 头，可能下到了错误页）"
    return True, "{:.1f} MB".format(size / 1024.0 / 1024.0)


def asset_size(asset):
    try:
        return int((asset or {}).get("size") or 0)
    except (TypeError, ValueError):
        return 0


def pending_update_path():
    """上次下载好但还没换上去的新版本（DisplayTools.exe.new）；没有返回 ""。"""
    target = running_exe_path()
    if not target:
        return ""
    path = target + STAGED_SUFFIX
    return path if os.path.isfile(path) else ""


class UpdateChecker(QThread):
    """后台查一次，避免网络卡住界面。"""

    finished_with = pyqtSignal(str, str)      # kind: ok / newer / error, message

    def __init__(self, parent=None):
        super().__init__(parent)
        self._stop = False
        #: 查到的结果：{"tag": ..., "asset": {...}, "notes": ..., "html_url": ...}
        self.result = {}

    def stop(self):
        self._stop = True

    def run(self):
        if self._stop:
            return
        release = None
        try:
            release = fetch_latest_release()
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                release = None          # 没有 release，退回 tags
            elif exc.code in (401, 403):
                self._emit_auth_error()
                return
            else:
                self.finished_with.emit(
                    "error", "查询失败：HTTP {}（可能是网络限制或频率限制）".format(exc.code))
                return
        except Exception:                                   # noqa: BLE001
            # release 接口不通不代表 tags 也不通（比如旧仓库没建 release），继续走 tags
            release = None

        if self._stop:
            return

        tag = (release or {}).get("tag") or ""
        if tag:
            asset = pick_asset(release.get("assets") or [])
            source = "release" if asset is not None else ""
            if asset is None:
                # 没有 Release 附件就退回仓库里提交的 exe——"直接从仓库下载"
                asset = repo_asset(tag)
                source = "repo" if asset is not None else ""
            self.result = {
                "tag": tag,
                "asset": asset,
                "source": source,
                "notes": release.get("notes") or "",
                "html_url": release.get("html_url") or release_page_url(tag),
            }
            if is_newer(tag):
                self.finished_with.emit("newer", self._newer_message(tag))
            else:
                self.finished_with.emit("ok", "已是最新版本（{}）".format(theme.APP_VERSION))
            return

        try:
            newest, _all_versions = latest_tag()
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403, 404):
                self._emit_auth_error()
            else:
                self.finished_with.emit(
                    "error", "查询失败：HTTP {}（可能是网络限制或频率限制）".format(exc.code))
            return
        except Exception as exc:                            # noqa: BLE001
            self.finished_with.emit(
                "error", "连不上 GitHub（{}），可手动访问 {}".format(
                    type(exc).__name__, repo_url()))
            return
        if self._stop:
            return
        if newest is None:
            self.finished_with.emit(
                "error", "远端还没有版本标签，可到 {} 查看".format(repo_url()))
        elif is_newer(newest):
            asset = repo_asset(newest)
            self.result = {"tag": newest, "asset": asset,
                           "source": "repo" if asset else "",
                           "notes": "", "html_url": release_page_url(newest)}
            self.finished_with.emit("newer", self._newer_message(newest))
        else:
            self.finished_with.emit("ok", "已是最新版本（{}）".format(theme.APP_VERSION))

    def _newer_message(self, tag):
        asset = self.result.get("asset")
        if asset:
            where = "仓库" if self.result.get("source") == "repo" else "Release 附件"
            return "发现新版本 {}（当前 {}），可以从{}直接下载 {}".format(
                tag, theme.APP_VERSION, where, asset.get("name") or "安装包")
        return "发现新版本 {}（当前 {}）：{}".format(
            tag, theme.APP_VERSION, release_page_url(tag))

    def _emit_auth_error(self):
        self.finished_with.emit(
            "error", "查不到版本信息：仓库非公开时需要在 DisplayTools.json 的 config 段里设置 "
                     "update_token；也可以直接打开 {}".format(releases_url()))


class UpdateDownloader(QThread):
    """后台下载新版本，边下边报进度。

    下完先自己校验一遍（大小 / MZ 头）；不合格就直接删掉并报错，
    **不会**把半截文件留给换文件流程。
    """

    progress = pyqtSignal(int, int)            # 已下载字节, 总字节（0 = 未知）
    finished_with = pyqtSignal(str, str)       # kind: ok / error, message(成功=路径)
    rejected = pyqtSignal(str)                 # 校验不通过的原因（对象已删）

    def __init__(self, asset, dest_path, parent=None):
        super().__init__(parent)
        self.asset = asset
        self.dest_path = dest_path
        self._stop = False

    def stop(self):
        self._stop = True

    def expected_size(self):
        return asset_size(self.asset)

    def run(self):
        try:
            path = download_asset(
                self.asset, self.dest_path,
                progress=lambda done, total: self.progress.emit(done, total),
                expected_size=self.expected_size())
        except DownloadError as exc:
            self.finished_with.emit(
                "error", "{}\n\n已丢弃这个不完整的文件，可以重试，"
                         "或到发布页手动下载：{}".format(exc, releases_url()))
            return
        except Exception as exc:                            # noqa: BLE001
            self.finished_with.emit(
                "error", "下载失败（{}）：可在浏览器里打开 {}".format(
                    type(exc).__name__, releases_url()))
            return
        if self._stop:
            return
        ok, detail = verify_update_file(path, self.expected_size())
        if not ok:
            _remove_quietly(path)
            self.rejected.emit(detail)
            self.finished_with.emit(
                "error", "下载校验没通过：{}\n\n已丢弃这个文件，可以重试，"
                         "或到发布页手动下载：{}".format(detail, releases_url()))
            return
        self.finished_with.emit("ok", path)


def human_size(size):
    """字节数转成好读的字符串。"""
    try:
        value = float(size)
    except (TypeError, ValueError):
        return "--"
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return "{:.0f} {}".format(value, unit) if unit == "B" else "{:.1f} {}".format(value, unit)
        value /= 1024.0
    return "--"

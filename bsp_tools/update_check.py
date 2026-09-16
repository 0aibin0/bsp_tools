"""版本更新检查 + 从 GitHub 下载新版本。

两条路：
- **检查**：优先 `GET /repos/{repo}/releases/latest`（能拿到 release 说明和附件），
  没有 release 就退回 tags API，只比版本号。
- **下载**：release 附件里的 exe（找不到 exe 就退而求其次找 zip），下载到
  exe / 源码同目录，文件名带上版本号——运行中的 DisplayTools.exe 是锁着的，
  覆盖不了，也不能覆盖（万一新版本起不来就没法回退）。

刻意不自动下载、不弹模态窗口，只在用户点「检查更新」时跑；失败一律当成
"没查到"，不让网络问题干扰调试。

私有仓库：未带 token 的 API 调用返回 404（GitHub 对私有仓库不区分"不存在"和
"没权限"）。在 config.ini 里加一行 `update_token = ghp_xxx` 即可；默认仓库
是私有的，所以下载附件也走带 token 的 API 地址（见 download_asset）。
"""

import json
import os
import re
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


def default_download_name(tag, asset):
    """下载到本地的文件名。

    附件本身就叫 DisplayTools.exe，直接落盘会顶掉正在运行的自己（Windows 也
    不让覆盖运行中的 exe），所以带上版本号区分。
    """
    name = os.path.basename((asset or {}).get("name") or "") or "DisplayTools.exe"
    stem, ext = os.path.splitext(name)
    if tag and tag.lower() not in stem.lower():
        stem = "{}_{}".format(stem, tag)
    return stem + ext


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


def download_asset(asset, dest_path, progress=None, timeout=DOWNLOAD_TIMEOUT):
    """把附件下载到 dest_path（先写 .part，成功后再改名）。

    progress: 可选回调 progress(已下载字节, 总字节, 总字节为 0 表示未知)。
    返回实际落盘路径；异常照旧往上抛。
    """
    url, headers = download_target(asset)
    if not url:
        raise ValueError("附件没有可下载地址")

    directory = os.path.dirname(os.path.abspath(dest_path))
    if directory:
        os.makedirs(directory, exist_ok=True)
    tmp = dest_path + ".part"
    done = 0
    request = urllib.request.Request(url, headers=headers)
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
    os.replace(tmp, dest_path)
    return dest_path


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
            "error", "查不到版本信息：仓库非公开时需要在 config.ini 里设置 "
                     "update_token；也可以直接打开 {}".format(releases_url()))


class UpdateDownloader(QThread):
    """后台下载新版本，边下边报进度。"""

    progress = pyqtSignal(int, int)            # 已下载字节, 总字节（0 = 未知）
    finished_with = pyqtSignal(str, str)       # kind: ok / error, message(成功=路径)

    def __init__(self, asset, dest_path, parent=None):
        super().__init__(parent)
        self.asset = asset
        self.dest_path = dest_path
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        try:
            path = download_asset(
                self.asset, self.dest_path,
                progress=lambda done, total: self.progress.emit(done, total))
        except Exception as exc:                            # noqa: BLE001
            self.finished_with.emit(
                "error", "下载失败（{}）：可在浏览器里打开 {}".format(
                    type(exc).__name__, releases_url()))
            return
        if self._stop:
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

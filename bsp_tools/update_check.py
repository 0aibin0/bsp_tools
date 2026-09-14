"""版本更新检查（GitHub Releases / Tags）。

刻意做得很轻：不自动下载、不弹模态窗口，只在用户点「检查更新」时跑一次，
结果用浮层提示。失败一律当成"没查到"，不让网络问题干扰调试工作。

走系统/环境变量里的代理（urllib 默认行为）；公司网络里如果连不上 GitHub，
提示里会带上仓库地址让用户自己去看。

仓库如果是**私有**的，未带 token 的 API 调用会返回 404（GitHub 对私有仓库
不区分"不存在"和"没权限"）。这种情况在 config.ini 里加一行
`update_token = ghp_xxx` 即可，或者直接在「关于」里点「打开仓库」。
"""

import json
import re
import urllib.error
import urllib.request

from PyQt5.QtCore import QThread, pyqtSignal

import app_config
import theme

DEFAULT_REPO = "0aibin0/bsp_tools"
TIMEOUT = 8
_UA = "DisplayTools-update-check"

_VERSION_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")


def repo_slug():
    return (app_config.config().get("update_repo", "") or DEFAULT_REPO).strip()


def repo_url():
    return "https://github.com/{}".format(repo_slug())


def api_url():
    return "https://api.github.com/repos/{}/tags".format(repo_slug())


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
    headers = {
        "User-Agent": _UA,
        "Accept": "application/vnd.github+json",
    }
    token = app_config.config().get("update_token", "").strip()
    if token:
        headers["Authorization"] = "Bearer {}".format(token)
    request = urllib.request.Request(api_url(), headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8", "replace"))
    return [item.get("name", "") for item in payload if isinstance(item, dict)]


def latest_tag(timeout=TIMEOUT):
    """返回 (最新版本号, 全部版本列表)。"""
    versions = [v for v in (parse_version(name) for name in fetch_tags(timeout))
                if v is not None]
    if not versions:
        return None, []
    newest = max(versions)
    return "v{}.{}.{}".format(*newest), sorted(versions, reverse=True)


class UpdateChecker(QThread):
    """后台查一次，避免网络卡住界面。"""

    finished_with = pyqtSignal(str, str)      # kind: ok / newer / error, message

    def __init__(self, parent=None):
        super().__init__(parent)
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        if self._stop:
            return
        try:
            newest, all_versions = latest_tag()
        except urllib.error.HTTPError as exc:
            if exc.code in (403, 404):
                self.finished_with.emit(
                    "error", "查不到版本信息：仓库非公开时需要在 config.ini 里设置 "
                             "update_token；也可以直接打开 {}".format(repo_url()))
            else:
                self.finished_with.emit(
                    "error", "查询失败：HTTP {}（可能是网络限制或频率限制）".format(exc.code))
            return
        except Exception as exc:                           # noqa: BLE001
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
            self.finished_with.emit(
                "newer", "发现新版本 {}（当前 {}）：{}".format(
                    newest, theme.APP_VERSION, repo_url()))
        else:
            self.finished_with.emit(
                "ok", "已是最新版本（{}）".format(theme.APP_VERSION))

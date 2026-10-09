import json
import locale
import os
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any
from uuid import uuid4

import urllib3
from farlog import getLogger

from funvideo.app.models import const

logger = getLogger("funvideo")
urllib3.disable_warnings()


def get_response(status: int, data: Any = None, message: str = "") -> dict[str, Any]:
    """构造统一响应；参数为状态码、可选数据和消息，返回响应字典。"""
    obj = {
        "status": status,
    }
    if data:
        obj["data"] = data
    if message:
        obj["message"] = message
    return obj


def to_json(obj: Any) -> str | None:
    """将对象转为 JSON；参数为任意对象，失败时记录日志并返回 ``None``。"""
    try:
        # 定义一个辅助函数来处理不同类型的对象
        def serialize(o: Any) -> Any:
            # 如果对象是可序列化类型，直接返回
            if isinstance(o, (int, float, bool, str)) or o is None:
                return o
            # 如果对象是二进制数据，转换为base64编码的字符串
            elif isinstance(o, bytes):
                return "*** binary data ***"
            # 如果对象是字典，递归处理每个键值对
            elif isinstance(o, dict):
                return {k: serialize(v) for k, v in o.items()}
            # 如果对象是列表或元组，递归处理每个元素
            elif isinstance(o, (list, tuple)):
                return [serialize(item) for item in o]
            # 如果对象是自定义类型，尝试返回其__dict__属性
            elif hasattr(o, "__dict__"):
                return serialize(o.__dict__)
            # 其他情况返回None（或者可以选择抛出异常）
            else:
                return None

        # 使用serialize函数处理输入对象
        serialized_obj = serialize(obj)

        # 序列化处理后的对象为JSON字符串
        return json.dumps(serialized_obj, ensure_ascii=False, indent=4)
    except (TypeError, ValueError, RecursionError) as exc:
        logger.warning(f"serialize object failed: {exc}")
        return None


def get_uuid(remove_hyphen: bool = False) -> str:
    """生成 UUID；参数控制是否移除连字符，返回字符串 ID。"""
    u = str(uuid4())
    if remove_hyphen:
        u = u.replace("-", "")
    return u


def root_dir() -> str:
    """返回应用数据根目录，不依赖服务的启动工作目录。"""
    configured_path = os.environ.get("FUNVIDEO_DATA_DIR")
    if configured_path:
        return str(Path(configured_path).expanduser().resolve())
    data_home = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return str(data_home / "farfarfun" / "funvideo")


def storage_dir(sub_dir: str = "", create: bool = False) -> str:
    """返回素材存储目录；可指定子目录并按需创建。"""
    d = os.path.join(root_dir(), "material")
    if sub_dir:
        d = os.path.join(d, sub_dir)
    if create and not os.path.exists(d):
        os.makedirs(d)

    return d


def resource_dir(sub_dir: str = "") -> str:
    """返回资源目录；参数为可选子目录名。"""
    d = os.path.join(root_dir(), "material")
    if sub_dir:
        d = os.path.join(d, sub_dir)
    return d


def task_dir(sub_dir: str = "") -> str:
    """返回并确保任务目录存在；参数为可选任务子目录。"""
    d = os.path.join(storage_dir(), "tasks")
    if sub_dir:
        d = os.path.join(d, sub_dir)
    if not os.path.exists(d):
        os.makedirs(d)
    return d


def font_dir(sub_dir: str = "") -> str:
    """返回并确保字体目录存在；参数为可选子目录。"""
    d = resource_dir("fonts")
    if sub_dir:
        d = os.path.join(d, sub_dir)
    if not os.path.exists(d):
        os.makedirs(d)
    return d


def song_dir(sub_dir: str = "") -> str:
    """返回并确保音乐目录存在；参数为可选子目录。"""
    d = resource_dir("songs")
    if sub_dir:
        d = os.path.join(d, sub_dir)
    if not os.path.exists(d):
        os.makedirs(d)
    return d


def public_dir(sub_dir: str = "") -> str:
    """返回并确保静态资源目录存在；参数为可选子目录。"""
    d = resource_dir("public")
    if sub_dir:
        d = os.path.join(d, sub_dir)
    if not os.path.exists(d):
        os.makedirs(d)
    return d


def run_in_background(
    func: Callable[..., Any], *args: Any, **kwargs: Any
) -> threading.Thread:
    """在线程中运行函数；参数透传给函数，返回已启动的线程。"""

    def run():
        try:
            func(*args, **kwargs)
        except Exception as e:
            logger.error(f"run_in_background error: {e}")

    thread = threading.Thread(target=run)
    thread.start()
    return thread


def time_convert_seconds_to_hmsm(seconds: float) -> str:
    """将秒数转换为 SRT 时间戳字符串。"""
    hours = int(seconds // 3600)
    seconds = seconds % 3600
    minutes = int(seconds // 60)
    milliseconds = int(seconds * 1000) % 1000
    seconds = int(seconds % 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"


def text_to_srt(idx: int, msg: str, start_time: float, end_time: float) -> str:
    """将序号、文本和起止秒数组装成 SRT 字幕块。"""
    start_time = time_convert_seconds_to_hmsm(start_time)
    end_time = time_convert_seconds_to_hmsm(end_time)
    return f"{idx}\n{start_time} --> {end_time}\n{msg}\n        "


def str_contains_punctuation(word: str) -> bool:
    """判断文本是否包含字幕分隔标点。"""
    for p in const.PUNCTUATIONS:
        if p in word:
            return True
    return False


def split_string_by_punctuations(s: str) -> list[str]:
    """按字幕标点拆分文本，返回非空片段列表。"""
    result = []
    txt = ""

    previous_char = ""
    next_char = ""
    for i in range(len(s)):
        char = s[i]
        if char == "\n":
            result.append(txt.strip())
            txt = ""
            continue

        if i > 0:
            previous_char = s[i - 1]
        if i < len(s) - 1:
            next_char = s[i + 1]

        if char == "." and previous_char.isdigit() and next_char.isdigit():
            # 取现1万，按2.5%收取手续费, 2.5 中的 . 不能作为换行标记
            txt += char
            continue

        if char not in const.PUNCTUATIONS:
            txt += char
        else:
            result.append(txt.strip())
            txt = ""
    result.append(txt.strip())
    # filter empty string
    result = list(filter(None, result))
    return result


def md5(text: str) -> str:
    """计算文本 MD5；参数为明文字符串，返回十六进制摘要。"""
    import hashlib

    return hashlib.md5(text.encode("utf-8"), usedforsecurity=False).hexdigest()


def get_system_locale() -> str:
    """返回系统语言代码，无法识别时返回英语。"""
    language = locale.getlocale()[0]
    return language.split("_")[0] if language else "en"


def load_locales(i18n_dir: str) -> dict[str, Any]:
    """读取国际化目录中的 JSON 文件，返回按语言代码索引的字典。"""
    _locales = {}
    for root, dirs, files in os.walk(i18n_dir):
        for file in files:
            if file.endswith(".json"):
                lang = file.split(".")[0]
                with open(os.path.join(root, file), encoding="utf-8") as f:
                    _locales[lang] = json.loads(f.read())
    return _locales


def parse_extension(filename: str) -> str:
    """返回文件名的小写扩展名，不包含点号。"""
    return os.path.splitext(filename)[1].strip().lower().replace(".", "")

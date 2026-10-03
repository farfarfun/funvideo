import json
import re
from functools import lru_cache

from farlog import getLogger
from funai.llm import get_model

logger = getLogger("funai")

_max_retries = 5


class LLMGenerationError(RuntimeError):
    """大模型在重试后仍无法生成指定内容。"""


@lru_cache(maxsize=1)
def _get_model():
    """按需创建并复用大模型客户端。"""
    return get_model("deepseek")


def generate_script(
    video_subject: str, language: str = "", paragraph_number: int = 1
) -> str:
    """生成视频脚本。

    Args:
        video_subject: 视频主题。
        language: 可选目标语言。
        paragraph_number: 需要保留的段落数。

    Returns:
        清理格式后的脚本文本。

    Raises:
        LLMGenerationError: 多次调用模型后仍无法生成有效脚本。
    """
    prompt = f"""
# Role: Video Script Generator

## Goals:
Generate a script for a video, depending on the subject of the video.

## Constrains:
1. the script is to be returned as a string with the specified number of paragraphs.
2. do not under any circumstance reference this prompt in your response.
3. get straight to the point, don't start with unnecessary things like, "welcome to this video".
4. you must not include any type of markdown or formatting in the script, never use a title.
5. only return the raw content of the script.
6. do not include "voiceover", "narrator" or similar indicators of what should be spoken at the beginning of each paragraph or line.
7. you must not mention the prompt, or anything about the script itself. also, never talk about the amount of paragraphs or lines. just write the script.
8. respond in the same language as the video subject.

# Initialization:
- video subject: {video_subject}
- number of paragraphs: {paragraph_number}
""".strip()
    if language:
        prompt += f"\n- language: {language}"

    final_script = ""
    last_error: Exception | None = None
    logger.info(f"subject: {video_subject}")

    def format_response(response: str) -> str:
        # Clean the script
        # Remove asterisks, hashes
        response = response.replace("*", "")
        response = response.replace("#", "")

        # Remove markdown syntax
        response = re.sub(r"\[.*]", "", response)
        response = re.sub(r"\(.*\)", "", response)

        # Split the script into paragraphs
        paragraphs = response.split("\n\n")

        # Join the selected paragraphs into a single string
        return "\n\n".join(paragraphs[:paragraph_number])

    for i in range(_max_retries):
        try:
            response = _get_model().chat(prompt=prompt)
            if not isinstance(response, str) or not response.strip():
                raise ValueError("模型返回空脚本")
            final_script = format_response(response)

            # g4f may return an error message
            if final_script and "当日额度已消耗完" in final_script:
                raise ValueError(final_script)

            if final_script:
                break
        except (OSError, TimeoutError, ValueError) as error:
            last_error = error
            logger.error(f"failed to generate script: {error}")

        if i < _max_retries:
            logger.warning(f"failed to generate video script, trying again... {i + 1}")

    if not final_script:
        detail = str(last_error) if last_error else "模型未返回有效脚本"
        raise LLMGenerationError(f"生成视频脚本失败（主题：{video_subject}）：{detail}")
    logger.success(f"completed: \n{final_script}")
    return final_script.strip()


def generate_terms(video_subject: str, video_script: str, amount: int = 5) -> list[str]:
    """生成视频素材检索词。

    Args:
        video_subject: 视频主题。
        video_script: 视频脚本。
        amount: 期望返回的检索词数量。

    Returns:
        英文素材检索词列表。

    Raises:
        LLMGenerationError: 多次调用模型后仍无法生成有效检索词。
    """
    prompt = f"""
# Role: Video Search Terms Generator

## Goals:
Generate {amount} search terms for stock videos, depending on the subject of a video.

## Constrains:
1. the search terms are to be returned as a json-array of strings.
2. each search term should consist of 1-3 words, always add the main subject of the video.
3. you must only return the json-array of strings. you must not return anything else. you must not return the script.
4. the search terms must be related to the subject of the video.
5. reply with english search terms only.

## Output Example:
["search term 1", "search term 2", "search term 3","search term 4","search term 5"]

## Context:
### Video Subject
{video_subject}

### Video Script
{video_script}

Please note that you must use English for generating video search terms; Chinese is not accepted.
""".strip()

    logger.info(f"subject: {video_subject}")

    search_terms: list[str] = []
    response = ""
    last_error: Exception | None = None
    for i in range(_max_retries):
        try:
            response = _get_model().chat(prompt)
            search_terms = json.loads(response)
            if not isinstance(search_terms, list) or not all(
                isinstance(term, str) for term in search_terms
            ):
                logger.error("response is not a list of strings.")
                continue

        except (OSError, TimeoutError, ValueError, json.JSONDecodeError) as error:
            last_error = error
            logger.warning(f"failed to generate video terms: {error}")
            if response:
                match = re.search(r"\[.*]", response)
                if match:
                    try:
                        search_terms = json.loads(match.group())
                    except (json.JSONDecodeError, TypeError) as parse_error:
                        last_error = parse_error
                        logger.warning(f"failed to generate video terms: {parse_error}")

        if search_terms and len(search_terms) > 0:
            break
        if i < _max_retries:
            logger.warning(f"failed to generate video terms, trying again... {i + 1}")

    if not search_terms:
        detail = str(last_error) if last_error else "模型未返回有效检索词"
        raise LLMGenerationError(f"生成素材检索词失败（主题：{video_subject}）：{detail}")
    logger.success(f"completed: \n{search_terms}")
    return search_terms

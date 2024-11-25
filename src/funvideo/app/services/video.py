import glob
import math
import os
import random
from typing import List
from tqdm import tqdm
import moviepy.audio.fx as afx
import moviepy.video.fx as vfx
from funutil import getLogger
from funvideo.app.models import const
from funvideo.app.models.schema import (
    MaterialInfo,
    VideoAspect,
    VideoConcatMode,
    VideoParams,
)
from funvideo.app.utils import utils
from moviepy import (
    AudioFileClip,
    ColorClip,
    CompositeAudioClip,
    CompositeVideoClip,
    ImageClip,
    TextClip,
    VideoFileClip,
    concatenate_videoclips,
)
from moviepy.video.tools.subtitles import SubtitlesClip
from PIL import ImageFont

logger = getLogger("funvideo")


def get_bgm_file(bgm_type: str = "random", bgm_file: str = ""):
    if not bgm_type:
        return ""

    if bgm_file and os.path.exists(bgm_file):
        return bgm_file

    if bgm_type == "random":
        suffix = "*.mp3"
        song_dir = utils.song_dir()
        files = glob.glob(os.path.join(song_dir, suffix))
        return random.choice(files)

    return ""


def combine_videos(
    combined_video_path: str,
    video_paths: List[str],
    audio_file: str,
    video_aspect: VideoAspect = VideoAspect.portrait,
    video_concat_mode: VideoConcatMode = VideoConcatMode.random,
    max_clip_duration: int = 5,
    threads: int = 2,
) -> str:
    audio_clip = AudioFileClip(audio_file)

    audio_duration = math.floor(audio_clip.duration)
    logger.info(f"max duration of audio: {audio_duration} seconds")
    req_dur = min(math.floor(audio_duration / len(video_paths)), max_clip_duration)
    logger.info(f"each clip will be maximum {req_dur} seconds long")

    aspect = VideoAspect(video_aspect)
    video_width, video_height = aspect.to_resolution()

    clips = []
    video_duration = 0

    raw_clips = []
    # 将多个视频拆成一个个小片段
    for video_path in tqdm(video_paths, desc="clip"):
        clip = VideoFileClip(video_path).without_audio()
        clip_duration = clip.duration
        for start_time in range(0, math.floor(clip_duration), req_dur):
            raw_clips.append(
                clip.subclipped(start_time, min(start_time + req_dur, clip_duration))
            )
            if video_concat_mode.value == VideoConcatMode.sequential.value:
                break

    # 打乱重排
    if video_concat_mode.value == VideoConcatMode.random.value:
        random.shuffle(raw_clips)

    video_ratio = video_width / video_height

    # 一遍又一遍地添加下载的剪辑，直到音频的持续时间（最大持续时间）已经达到

    while video_duration < audio_duration:
        for clip in raw_clips:
            # 检查剪辑是否比剩余音频长
            if (audio_duration - video_duration) < clip.duration:
                clip = clip.subclipped(0, audio_duration - video_duration)
            # 只有当计算出的剪辑长度（要求长度）比实际剪辑短时才缩短剪辑，以防止静止图像
            elif req_dur < clip.duration:
                clip = clip.subclipped(0, req_dur)
            clip = clip.with_fps(30)

            # 并非所有视频都是相同的大小，所以我们需要调整它们的大小
            clip_w, clip_h = clip.size
            if clip_w != video_width or clip_h != video_height:
                clip_ratio = clip.w / clip.h
                if clip_ratio == video_ratio:
                    # 等比例缩放
                    clip = clip.with_effects(
                        [vfx.Resize(new_size=(video_width, video_height))]
                    )
                else:
                    # 等比缩放视频
                    if clip_ratio > video_ratio:
                        scale_factor = video_width / clip_w  # 按照目标宽度等比缩放
                    else:
                        scale_factor = video_height / clip_h  # 按照目标高度等比缩放

                    new_width, new_height = (
                        int(clip_w * scale_factor),
                        int(clip_h * scale_factor),
                    )
                    clip_resized = clip.with_effects(
                        [vfx.Resize(new_size=(new_width, new_height))]
                    )

                    background = ColorClip(
                        size=(video_width, video_height), color=(0, 0, 0)
                    )
                    clip = CompositeVideoClip(
                        [
                            background.with_duration(clip.duration),
                            clip_resized.with_position("center"),
                        ]
                    )

            clips.append(clip)
            logger.info(
                f"resizing video to {video_width} x {video_height}, clip size: {clip.w} x {clip.h},duration: {clip.duration}"
            )
            video_duration += clip.duration
            if video_duration >= audio_duration:
                break

    video_clip = concatenate_videoclips(clips)
    video_clip = video_clip.with_fps(30)
    logger.info("writing")
    # https://github.com/harry0703/MoneyPrinterTurbo/issues/111#issuecomment-2032354030
    video_clip.write_videofile(
        filename=combined_video_path,
        threads=threads,
        logger="bar",
        temp_audiofile_path=os.path.dirname(combined_video_path),
        audio_codec="aac",
        fps=30,
    )
    video_clip.close()
    logger.success(f"completed writing video to {combined_video_path}")
    return combined_video_path


def wrap_text(text, max_width, font="Arial", fontsize=60):
    # 创建字体对象
    font = ImageFont.truetype(font, fontsize)

    def get_text_size(inner_text):
        inner_text = inner_text.strip()
        left, top, right, bottom = font.getbbox(inner_text)
        return right - left, bottom - top

    width, height = get_text_size(text)
    if width <= max_width:
        return text, height

    # logger.warning(f"wrapping text, max_width: {max_width}, text_width: {width}, text: {text}")

    processed = True

    _wrapped_lines_ = []
    words = text.split(" ")
    _txt_ = ""
    for word in words:
        _before = _txt_
        _txt_ += f"{word} "
        _width, _height = get_text_size(_txt_)
        if _width <= max_width:
            continue
        else:
            if _txt_.strip() == word.strip():
                processed = False
                break
            _wrapped_lines_.append(_before)
            _txt_ = f"{word} "
    _wrapped_lines_.append(_txt_)
    if processed:
        _wrapped_lines_ = [line.strip() for line in _wrapped_lines_]
        result = "\n".join(_wrapped_lines_).strip()
        height = len(_wrapped_lines_) * height
        # logger.warning(f"wrapped text: {result}")
        return result, height

    _wrapped_lines_ = []
    chars = list(text)
    _txt_ = ""
    for word in chars:
        _txt_ += word
        _width, _height = get_text_size(_txt_)
        if _width <= max_width:
            continue
        else:
            _wrapped_lines_.append(_txt_)
            _txt_ = ""
    _wrapped_lines_.append(_txt_)
    result = "\n".join(_wrapped_lines_).strip()
    height = len(_wrapped_lines_) * height
    # logger.warning(f"wrapped text: {result}")
    return result, height


def generate_video(
    video_path: str,
    audio_path: str,
    subtitle_path: str,
    output_file: str,
    params: VideoParams,
):
    aspect = VideoAspect(params.video_aspect)
    video_width, video_height = aspect.to_resolution()

    logger.info(f"start, video size: {video_width} x {video_height}")
    logger.info(f"  ① video: {video_path}")
    logger.info(f"  ② audio: {audio_path}")
    logger.info(f"  ③ subtitle: {subtitle_path}")
    logger.info(f"  ④ output: {output_file}")

    # https://github.com/harry0703/MoneyPrinterTurbo/issues/217
    # PermissionError: [WinError 32] The process cannot access the file because it is being used by another process: 'final-1.mp4.tempTEMP_MPY_wvf_snd.mp3'
    # write into the same directory as the output file
    output_dir = os.path.dirname(output_file)

    font_path = ""
    if params.subtitle_enabled:
        if not params.font_name:
            params.font_name = "STHeitiMedium.ttc"
        font_path = os.path.join(utils.font_dir(), params.font_name)
        if os.name == "nt":
            font_path = font_path.replace("\\", "/")

        logger.info(f"using font: {font_path}")

    def create_text_clip(subtitle_item):
        phrase = subtitle_item[1]
        max_width = video_width * 0.9
        wrapped_txt, txt_height = wrap_text(
            phrase, max_width=max_width, font=font_path, fontsize=params.font_size
        )
        _clip = TextClip(
            wrapped_txt,
            font=font_path,
            fontsize=params.font_size,
            color=params.text_fore_color,
            bg_color=params.text_background_color,
            stroke_color=params.stroke_color,
            stroke_width=params.stroke_width,
            print_cmd=False,
        )
        duration = subtitle_item[0][1] - subtitle_item[0][0]
        _clip = _clip.with_start(subtitle_item[0][0])
        _clip = _clip.with_end(subtitle_item[0][1])
        _clip = _clip.with_duration(duration)
        if params.subtitle_position == "bottom":
            _clip = _clip.with_position(("center", video_height * 0.95 - _clip.h))
        elif params.subtitle_position == "top":
            _clip = _clip.with_position(("center", video_height * 0.05))
        elif params.subtitle_position == "custom":
            # 确保字幕完全在屏幕内
            margin = 10  # 额外的边距，单位为像素
            max_y = video_height - _clip.h - margin
            min_y = margin
            custom_y = (video_height - _clip.h) * (params.custom_position / 100)
            custom_y = max(min_y, min(custom_y, max_y))  # 限制 y 值在有效范围内
            _clip = _clip.with_position(("center", custom_y))
        else:  # center
            _clip = _clip.with_position(("center", "center"))
        return _clip

    video_clip = VideoFileClip(video_path)
    audio_clip = AudioFileClip(audio_path).with_effects(
        [afx.MultiplyVolume(params.voice_volume)]
    )

    if subtitle_path and os.path.exists(subtitle_path) and False:
        sub = SubtitlesClip(
            subtitles=subtitle_path,
            font="/Users/bingtao/workspace/explore/MoneyPrinterTurbo/resource/fonts/STHeitiMedium.ttc",
            # font=font_path,
            encoding="utf-8",
        )
        text_clips = []
        for item in sub.subtitles:
            clip = create_text_clip(subtitle_item=item)
            text_clips.append(clip)
        video_clip = CompositeVideoClip([video_clip, *text_clips])

    bgm_file = get_bgm_file(bgm_type=params.bgm_type, bgm_file=params.bgm_file)
    if bgm_file:
        try:
            bgm_clip = AudioFileClip(bgm_file).with_effects(
                [afx.MultiplyVolume(params.voice_volume)]
            )
            bgm_clip = bgm_clip.with_effects([vfx.Loop(duration=video_clip.duration)])
            audio_clip = CompositeAudioClip([audio_clip, bgm_clip])
        except Exception as e:
            logger.error(f"failed to add bgm: {str(e)}")

    video_clip = video_clip.with_audio(audio_clip)
    video_clip.write_videofile(
        output_file,
        audio_codec="aac",
        temp_audiofile_path=output_dir,
        threads=params.n_threads or 2,
        logger=None,
        fps=30,
    )
    video_clip.close()
    del video_clip
    logger.success("completed")


def preprocess_video(materials: List[MaterialInfo], clip_duration=4):
    for material in materials:
        if not material.url:
            continue

        ext = utils.parse_extension(material.url)
        try:
            clip = VideoFileClip(material.url)
        except Exception:
            clip = ImageClip(material.url)

        width = clip.size[0]
        height = clip.size[1]
        if width < 480 or height < 480:
            logger.warning(f"video is too small, width: {width}, height: {height}")
            continue

        if ext in const.FILE_TYPE_IMAGES:
            logger.info(f"processing image: {material.url}")
            # 创建一个图片剪辑，并设置持续时间为3秒钟
            clip = (
                ImageClip(material.url)
                .with_duration(clip_duration)
                .with_position("center")
            )
            # 使用resize方法来添加缩放效果。这里使用了lambda函数来使得缩放效果随时间变化。
            # 假设我们想要从原始大小逐渐放大到120%的大小。
            # t代表当前时间，clip.duration为视频总时长，这里是3秒。
            # 注意：1 表示100%的大小，所以1.2表示120%的大小
            # zoom_clip = clip.resize(lambda t: 1 + (clip_duration * 0.03) * (t / clip.duration))
            zoom_clip = clip.with_effects(
                [vfx.Resize(lambda t: 1 + (clip_duration * 0.03) * (t / clip.duration))]
            )

            # 如果需要，可以创建一个包含缩放剪辑的复合视频剪辑
            # （这在您想要在视频中添加其他元素时非常有用）
            final_clip = CompositeVideoClip([zoom_clip])

            # 输出视频
            video_file = f"{material.url}.mp4"
            final_clip.write_videofile(video_file, fps=30, logger=None)
            final_clip.close()
            del final_clip
            material.url = video_file
            logger.success(f"completed: {video_file}")
    return materials

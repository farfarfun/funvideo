import math
import re
from os import path

from funmaterial.video.download import download_videos
from funtalk.tts import tts_generate
from funutil import getLogger
from funutil.cache import disk_cache
from funvideo.app.config import config
from funvideo.app.models import const
from funvideo.app.models.schema import VideoConcatMode, VideoParams
from funvideo.app.services import llm, video
from funvideo.app.services import state as sm
from funvideo.app.utils import utils

logger = getLogger("funvideo")


class TaskGenerate:
    def __init__(self, task_id, *args, **kwargs):
        self.task_id = task_id
        self.audio_file = self.task_dir("audio.mp3")
        self.subtitle_file = self.task_dir("subtitle.srt")

    def task_dir(self, file_path=None):
        root = utils.task_dir(self.task_id)
        if file_path is None:
            return root
        else:
            return path.join(root, file_path)

    def update_task(
        self,
        state: int = const.TASK_STATE_PROCESSING,
        progress: int = 0,
        **kwargs,
    ):
        sm.state.update_task(self.task_id, state=state, progress=progress, **kwargs)

    def start(self, params: VideoParams, stop_at: str = "video"):
        logger.info(f"start task: {self.task_id}, stop_at: {stop_at}")
        self.update_task(state=const.TASK_STATE_PROCESSING, progress=5)

        if type(params.video_concat_mode) is str:
            params.video_concat_mode = VideoConcatMode(params.video_concat_mode)

        # 1. Generate script
        video_script = self.generate_script(params)
        if not video_script:
            self.update_task(state=const.TASK_STATE_FAILED)
            return

        self.update_task(state=const.TASK_STATE_PROCESSING, progress=10)

        if stop_at == "script":
            self.update_task(
                state=const.TASK_STATE_COMPLETE, progress=100, script=video_script
            )
            return {"script": video_script}

        # 2. Generate terms
        video_terms = ""
        if params.video_source != "local":
            video_terms = self.generate_terms(params, video_script)
            if not video_terms:
                self.update_task(state=const.TASK_STATE_FAILED)
                return

        self.save_script_data(video_script, video_terms, params)

        if stop_at == "terms":
            self.update_task(
                state=const.TASK_STATE_COMPLETE, progress=100, terms=video_terms
            )
            return {"script": video_script, "terms": video_terms}

        self.update_task(state=const.TASK_STATE_PROCESSING, progress=20)

        # 3. Generate audio
        audio_duration, sub_maker = self.generate_audio(params, video_script)
        if not self.audio_file:
            self.update_task(state=const.TASK_STATE_FAILED)
            return
        self.update_task(state=const.TASK_STATE_PROCESSING, progress=30)

        if stop_at == "audio":
            self.update_task(
                state=const.TASK_STATE_COMPLETE,
                progress=100,
                audio_file=self.audio_file,
            )
            return {"audio_file": self.audio_file, "audio_duration": audio_duration}

        if stop_at == "subtitle":
            self.update_task(
                state=const.TASK_STATE_COMPLETE,
                progress=100,
                subtitle_path=self.subtitle_file,
            )
            return {"subtitle_path": self.subtitle_file}

        self.update_task(state=const.TASK_STATE_PROCESSING, progress=40)

        # 5. Get video materials
        downloaded_videos = self.get_video_materials(
            params, video_terms, audio_duration
        )
        if not downloaded_videos:
            self.update_task(state=const.TASK_STATE_FAILED)
            return

        if stop_at == "materials":
            self.update_task(
                state=const.TASK_STATE_COMPLETE,
                progress=100,
                materials=downloaded_videos,
            )
            return {"materials": downloaded_videos}

        self.update_task(state=const.TASK_STATE_PROCESSING, progress=50)

        # 6. Generate final videos
        final_video_paths, combined_video_paths = self.generate_final_videos(
            params, downloaded_videos
        )

        if not final_video_paths:
            self.update_task(state=const.TASK_STATE_FAILED)
            return

        logger.success(
            f"task {self.task_id} finished, generated {len(final_video_paths)} videos."
        )

        kwargs = {
            "videos": final_video_paths,
            "combined_videos": combined_video_paths,
            "script": video_script,
            "terms": video_terms,
            "audio_file": self.audio_file,
            "audio_duration": audio_duration,
            "subtitle_path": self.subtitle_file,
            "materials": downloaded_videos,
        }
        self.update_task(state=const.TASK_STATE_COMPLETE, progress=100, **kwargs)
        return kwargs

    def generate_script(self, params):
        logger.info(
            "###################################################################"
        )
        logger.info("generating video script")
        video_script = params.video_script.strip()
        if not video_script:
            video_script = llm.generate_script(
                video_subject=params.video_subject,
                language=params.video_language,
                paragraph_number=params.paragraph_number,
            )
        else:
            logger.debug(f"video script: \n{video_script}")

        if not video_script:
            sm.state.update_task(self.task_id, state=const.TASK_STATE_FAILED)
            logger.error("failed to generate video script.")
            return None

        return video_script

    def generate_terms(self, params, video_script):
        logger.info(
            "###################################################################"
        )
        logger.info("generating video terms")
        video_terms = params.video_terms
        if not video_terms:
            video_terms = llm.generate_terms(
                video_subject=params.video_subject, video_script=video_script, amount=5
            )
        else:
            if isinstance(video_terms, str):
                video_terms = [term.strip() for term in re.split(r"[,，]", video_terms)]
            elif isinstance(video_terms, list):
                video_terms = [term.strip() for term in video_terms]
            else:
                raise ValueError("video_terms must be a string or a list of strings.")

            logger.debug(f"video terms: {utils.to_json(video_terms)}")

        if not video_terms:
            sm.state.update_task(self.task_id, state=const.TASK_STATE_FAILED)
            logger.error("failed to generate video terms.")
            return None

        return video_terms

    def generate_final_videos(self, params, downloaded_videos):
        final_video_paths = []
        combined_video_paths = []
        video_concat_mode = (
            params.video_concat_mode
            if params.video_count == 1
            else VideoConcatMode.random
        )

        _progress = 50
        for i in range(params.video_count):
            index = i + 1
            combined_video_path = path.join(
                utils.task_dir(self.task_id), f"combined-{index}.mp4"
            )
            logger.info(
                "###################################################################"
            )
            logger.info(f"combining video: {index} => {combined_video_path}")
            video.combine_videos(
                combined_video_path=combined_video_path,
                video_paths=downloaded_videos,
                audio_file=self.audio_file,
                video_aspect=params.video_aspect,
                video_concat_mode=video_concat_mode,
                max_clip_duration=params.video_clip_duration,
                threads=params.n_threads,
            )

            _progress += 50 / params.video_count / 2
            self.update_task(progress=_progress)

            final_video_path = path.join(
                utils.task_dir(self.task_id), f"final-{index}.mp4"
            )

            logger.info(
                "###################################################################"
            )
            logger.info(f"generating video: {index} => {final_video_path}")
            video.generate_video(
                video_path=combined_video_path,
                audio_path=self.audio_file,
                subtitle_path=self.subtitle_file,
                output_file=final_video_path,
                params=params,
            )

            _progress += 50 / params.video_count / 2
            self.update_task(progress=_progress)

            final_video_paths.append(final_video_path)
            combined_video_paths.append(combined_video_path)

        return final_video_paths, combined_video_paths

    def save_script_data(self, video_script, video_terms, params):
        script_file = self.task_dir("script.json")
        script_data = {
            "script": video_script,
            "search_terms": video_terms,
            "params": params,
        }

        with open(script_file, "w", encoding="utf-8") as f:
            f.write(utils.to_json(script_data))

    def generate_audio(self, params, video_script):
        logger.info(
            "###################################################################"
        )
        logger.info("generating audio")

        sub_maker = tts_generate(
            text=video_script,
            voice_name=params.voice_name,
            voice_rate=params.voice_rate,
            voice_file=self.audio_file,
            subtitle_file=self.subtitle_file,
        )
        if sub_maker is None:
            self.update_task(state=const.TASK_STATE_FAILED)
            logger.error(
                """failed to generate audio:
        1. check if the language of the voice matches the language of the video script.
        2. check if the network is available. If you are in China, it is recommended to use a VPN and enable the global traffic mode.
            """.strip()
            )
            return None, None, None

        audio_duration = math.ceil(sub_maker.get_audio_duration())
        return audio_duration, sub_maker

    @disk_cache(cache_key="task_id")
    def get_video_materials(self, params, video_terms, audio_duration):
        if params.video_source == "local":
            logger.info(
                "###################################################################"
            )
            logger.info("preprocess local materials")
            materials = video.preprocess_video(
                materials=params.video_materials,
                clip_duration=params.video_clip_duration,
            )
            if not materials:
                self.update_task(state=const.TASK_STATE_FAILED)
                logger.error(
                    "no valid materials found, please check the materials and try again."
                )
                return None
            return [material_info.url for material_info in materials]
        else:
            logger.info(
                "###################################################################"
            )
            logger.info(f"downloading videos from {params.video_source}")
            downloaded_videos = download_videos(
                api_key=config.app.get("pixabay_api_keys")[0],
                search_terms=video_terms,
                source=params.video_source,
                video_aspect=params.video_aspect,
                material_directory=utils.storage_dir("cache_videos"),
                video_contact_mode=params.video_concat_mode,
                audio_duration=audio_duration * params.video_count,
                max_clip_duration=params.video_clip_duration,
            )
            if not downloaded_videos:
                self.update_task(state=const.TASK_STATE_FAILED)
                logger.error(
                    "failed to download videos, maybe the network is not available. if you are in China, please use a VPN."
                )
                return None
            return downloaded_videos


def start(task_id, params: VideoParams, stop_at: str = "video"):
    return TaskGenerate(task_id).start(params, stop_at=stop_at)


def example():
    task_id = "task_id"
    params = VideoParams(
        video_subject="金钱的作用",
        voice_name="zh-CN-XiaoyiNeural-Female",
        voice_rate=1.0,
        video_source="pixabay",
    )
    start(task_id, params, stop_at="video")

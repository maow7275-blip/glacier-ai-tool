import base64
import json
import itertools
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app


def response(data=None, status=200, content=b"", headers=None):
    result = Mock(status_code=status, content=content, headers=headers or {})
    result.text = json.dumps(data)
    result.json.return_value = data
    return result


class ModelConfigurationTests(unittest.TestCase):
    def test_image_configuration_is_complete(self):
        self.assertEqual(app.APP_VERSION, "4.2.1")
        self.assertEqual(len(app.MODEL_QUALITY), 15)
        for model, qualities in app.MODEL_QUALITY.items():
            with self.subTest(model=model):
                self.assertIn(model, app.IMAGE_MODEL_MAX_REFS)
                for ratio in app.IMAGE_MODEL_RATIOS[model]:
                    if model == "seedream-5.0-pro":
                        self.assertIn(ratio, app.SEEDREAM_SIZE_MAP)
                    else:
                        self.assertTrue(set(qualities) <= set(app.SIZE_MAP[ratio]))

    def test_flare_and_sunburst_constraints(self):
        expected = {"1:1", "16:9", "9:16", "5:4", "4:3", "3:2", "3:1", "3:4"}
        for version in ("2.5", "2.6"):
            for variant in ("flare", "sunburst"):
                model = f"gpt-image-{version}-{variant}"
                self.assertEqual(set(app.IMAGE_MODEL_RATIOS[model]), expected)
                self.assertEqual(app.IMAGE_MODEL_MAX_REFS[model], 16)
                self.assertEqual(app.IMAGE_MODEL_MAX_REF_TOTAL_BYTES[model], 25 * 1024**2)
                self.assertIn(model, app.IMAGE_MODELS_WITH_TRANSPARENT_BACKGROUND)
        self.assertEqual(app.SIZE_MAP["3:1"], {
            "1k": "1008x336", "2k": "2016x672", "4k": "3504x1168",
        })

    def test_video_configuration_is_complete(self):
        models = [model for model in app.VIDEO_MODELS if model not in app.VIDEO_MODEL_GROUPS]
        for group in app.VIDEO_MODEL_GROUPS.values():
            models.extend(group)
        self.assertEqual(len(models), 11)
        for model in models:
            for config in (app.VIDEO_MODEL_DURATIONS, app.VIDEO_PROMPT_LIMIT,
                           app.VIDEO_MODEL_ORIENTATIONS, app.VIDEO_MODEL_MAX_IMAGES_BASE,
                           app.VIDEO_MODEL_MAX_VIDEOS, app.VIDEO_MODEL_MAX_AUDIOS):
                self.assertIn(model, config)
        self.assertEqual(app.VIDEO_MODEL_DURATIONS["muse-video"], list(map(str, range(4, 31))))
        self.assertEqual(app.VIDEO_MODEL_ORIENTATIONS["muse-video"], {})
        self.assertEqual(app.VIDEO_MODEL_RATIOS["muse-video"], ["9:16", "16:9"])


class WorkerTests(unittest.TestCase):
    def setUp(self):
        for target in ("app.append_debug_log", "app.time.sleep", "app.requests.post", "app.requests.get"):
            mock = self.enterContext(patch(target))
            setattr(self, target.rsplit(".", 1)[-1], mock)
        self.post.side_effect = AssertionError("Unexpected API call")
        self.get.side_effect = AssertionError("Unexpected download")

    def image_worker(self, model="gpt-image-2.6-flare", **kwargs):
        worker = app.GenerateThread("test-key", model, "test prompt", "2048x2048", "2k", "png", **kwargs)
        worker._download_result = Mock(return_value=response(
            content=b"\x89PNG" + b"x" * 2048, headers={"content-type": "image/png"},
        ))
        return worker

    def collect(self, worker):
        done, errors = [], []
        worker.one_finished.connect(lambda index, data: done.append((index, data)))
        worker.error.connect(lambda index, error: errors.append((index, error)))
        return done, errors

    def test_all_images_use_documented_async_payload(self):
        for model in app.MODEL_QUALITY:
            with self.subTest(model=model):
                worker = self.image_worker(model, image_url=["https://example.com/ref.png"])
                done, errors = self.collect(worker)
                self.post.side_effect = [
                    response({"id": "task/1", "status": "queued"}, status=202),
                ]
                self.get.side_effect = [
                    response({"status": "running"}),
                    response({"status": "completed", "images": [{"url": "https://example.com/result.png"}]}),
                ]
                self.post.reset_mock()
                self.get.reset_mock()
                worker._generate_one(0)
                self.assertEqual(len(done), 1)
                self.assertFalse(errors)
                self.assertEqual(self.post.call_args_list[0].args, (app.API_URL,))
                payload = self.post.call_args_list[0].kwargs["json"]
                self.assertEqual(payload, {
                    "model": model, "prompt": "test prompt", "size": "2048x2048",
                    "reference_images": ["https://example.com/ref.png"],
                })
                self.assertEqual(self.get.call_args_list[0].args[0],
                                 "https://www.hfsyapi.cn/v1/image/query/task%2F1")
                worker._download_result.assert_called_once_with(0, "https://example.com/result.png")

    def test_image_transparency_and_no_silent_reference_trimming(self):
        refs = [f"https://example.com/{i}.png" for i in range(16)]
        worker = self.image_worker(image_url=refs, background="transparent")
        self.post.side_effect = [response({"status": "completed", "images": [{"url": "/result.png"}]})]
        worker._generate_one(0)
        self.assertEqual(self.post.call_args.kwargs["json"]["reference_images"], refs)
        self.assertEqual(self.post.call_args.kwargs["json"]["background"], "transparent")
        worker._download_result.assert_called_once_with(0, "https://www.hfsyapi.cn/result.png")

    def test_image_query_recovers_without_resubmitting(self):
        worker = self.image_worker()
        done, errors = self.collect(worker)
        self.post.side_effect = [
            response({"data": {"id": "task-1", "status": "queued"}}),
        ]
        self.get.side_effect = [
            app.requests.exceptions.ConnectionError("offline"),
            response(status=503),
            response(status=429, headers={"Retry-After": "2"}),
            response({"data": {"status": "completed", "images": [{"url": "/image.png"}]}}),
        ]
        worker._generate_one(0)
        self.assertEqual(len(done), 1)
        self.assertFalse(errors)
        self.assertEqual(self.post.call_count, 1)
        self.assertEqual(self.get.call_count, 4)

    def test_image_failed_task_reports_reason(self):
        self.post.side_effect = [response({"id": "task-1", "status": "failed", "error": {"message": "blocked"}})]
        with self.assertRaisesRegex(RuntimeError, "blocked"):
            self.image_worker()._generate_one(0)

    def test_image_completed_without_image_is_an_error(self):
        self.post.side_effect = [response({"status": "completed", "images": []})]
        with self.assertRaises(RuntimeError):
            self.image_worker()._generate_one(0)

    def test_image_missing_task_id_is_an_error(self):
        self.post.side_effect = [response({"status": "queued"})]
        with self.assertRaisesRegex(RuntimeError, "task_id"):
            self.image_worker()._generate_one(0)

    def test_image_timeout_does_not_submit_again(self):
        self.post.side_effect = [response({"status": "queued", "id": "task-1"})]
        with patch.object(app, "IMAGE_GENERATION_TIMEOUT_SECONDS", 0):
            with self.assertRaisesRegex(RuntimeError, "task-1"):
                self.image_worker()._generate_one(0)
        self.assertEqual(self.post.call_count, 1)

    def test_image_submission_error_is_not_retried(self):
        self.post.side_effect = [response(status=503)]
        worker = self.image_worker()
        done, errors = self.collect(worker)
        worker._generate_one(0)
        self.assertFalse(done)
        self.assertIn("503", errors[0][1])
        self.assertEqual(self.post.call_count, 1)

    def test_image_rate_limit_can_retry_submission(self):
        self.post.side_effect = [response(status=429), response({
            "status": "completed", "images": [{"b64_json": base64.b64encode(b"image bytes").decode()}],
        })]
        worker = self.image_worker()
        done, errors = self.collect(worker)
        worker._generate_one(0)
        self.assertEqual(done, [(0, b"image bytes")])
        self.assertFalse(errors)
        self.assertEqual(self.post.call_count, 2)

    def test_image_invalid_input_never_reaches_api(self):
        worker = self.image_worker()
        for prompt in ("", "x" * 5001):
            worker.prompt = prompt
            with self.assertRaises(ValueError):
                worker._generate_one(0)
        worker.prompt = "test"
        worker.image_url = ["https://example.com/ref.png"] * 17
        with self.assertRaises(ValueError):
            worker._generate_one(0)
        self.post.assert_not_called()

    def video_worker(self, model="muse-video", ratio="9:16"):
        return app.VideoGenerateThread(
            "test-key", "test prompt", "landscape", "5", model=model, sd_ratio=ratio,
            image_url=["https://example.com/image.png"],
            video_refs=["https://example.com/reference.mp4"],
            audio_refs=["https://example.com/audio.mp3"],
        )

    def test_muse_payload_and_documented_video_result(self):
        self.post.side_effect = [response({"id": "video/1", "status": "IN_PROGRESS"})]
        self.get.side_effect = [
            response({"success": True, "data": {"status": "completed", "result_url": "https://example.com/video.mp4"}}),
            response(content=b"video bytes"),
        ]
        worker = self.video_worker()
        done, errors = self.collect(worker)
        worker._generate_one(0)
        self.assertEqual(done, [(0, b"video bytes")])
        self.assertFalse(errors)
        payload = self.post.call_args_list[0].kwargs["json"]
        self.assertNotIn("orientation", payload)
        self.assertNotIn("size", payload)
        self.assertEqual(payload["ratio"], "9:16")
        self.assertEqual(len(payload["images"]), 1)
        self.assertEqual(len(payload["videos"]), 1)
        self.assertEqual(len(payload["audios"]), 1)
        self.assertEqual(self.get.call_args_list[0].args[0],
                         "https://www.hfsyapi.cn/v1/video/query?id=video%2F1")
        self.assertEqual(self.get.call_args_list[1].args[0], "https://example.com/video.mp4")

    def test_existing_video_orientation_and_result_compatibility(self):
        self.post.side_effect = [response({"id": "video-1"})]
        self.get.side_effect = [
            response({"data": {"status": "completed", "video_url": "https://example.com/video.mp4"}}),
            response(content=b"video bytes"),
        ]
        worker = self.video_worker("sd-2.5-720")
        worker.sd_size = "large"
        worker._generate_one(0)
        self.assertEqual(self.post.call_args_list[0].kwargs["json"]["orientation"], "landscape")
        self.assertEqual(self.post.call_args_list[0].kwargs["json"]["size"], "large")

    def test_video_success_status_aliases_are_terminal(self):
        for status in ("succeeded", "complete"):
            with self.subTest(status=status):
                self.post.side_effect = [response({"id": "video-1"})]
                self.get.side_effect = [
                    response({"status": status, "video_url": "https://example.com/video.mp4"}),
                    response(content=b"video bytes"),
                ]
                self.post.reset_mock()
                self.get.reset_mock()
                worker = self.video_worker()
                done, errors = self.collect(worker)
                worker._generate_one(0)
                self.assertEqual(done, [(0, b"video bytes")])
                self.assertFalse(errors)

    def test_video_failure_reason_is_preserved(self):
        self.post.side_effect = [response({"id": "video-1"})]
        self.get.side_effect = [
            response({"data": {"status": "failed", "fail_reason": "moderation"}}),
        ]
        worker = self.video_worker()
        done, errors = self.collect(worker)
        worker._generate_one(0)
        self.assertFalse(done)
        self.assertIn("moderation", errors[0][1])
        self.get.assert_called_once_with(
            "https://www.hfsyapi.cn/v1/video/query?id=video-1",
            headers={"Authorization": "Bearer test-key", "Content-Type": "application/json"},
            timeout=(10, 30),
        )

    def test_video_permanent_query_error_stops_polling(self):
        for status in (401, 403, 404, 405):
            with self.subTest(status=status):
                self.post.side_effect = [response({"id": "existing-video"})]
                self.get.side_effect = [response({"error": {"message": "Invalid URL"}}, status=status)]
                self.post.reset_mock()
                self.get.reset_mock()
                worker = self.video_worker()
                done, errors = self.collect(worker)
                with patch.object(app.time, "monotonic", side_effect=itertools.count()), \
                     patch.object(app, "VIDEO_GENERATION_TIMEOUT_SECONDS", 10):
                    worker._generate_one(0)
                self.assertFalse(done)
                self.assertEqual(len(errors), 1)
                self.assertIn(str(status), errors[0][1])
                self.assertIn("existing-video", errors[0][1])
                self.assertEqual(self.post.call_count, 1)
                self.assertEqual(self.get.call_count, 1)

    def test_video_transient_query_error_recovers_on_same_task(self):
        self.post.side_effect = [response({"id": "existing-video"})]
        self.get.side_effect = [
            app.requests.exceptions.ConnectionError("offline"),
            response(status=503),
            response(status=429, headers={"Retry-After": "2"}),
            response({"data": {"status": "completed", "video_url": "https://example.com/video.mp4"}}),
            response(content=b"video bytes"),
        ]
        worker = self.video_worker()
        done, errors = self.collect(worker)
        worker._generate_one(0)
        self.assertEqual(done, [(0, b"video bytes")])
        self.assertFalse(errors)
        self.assertEqual(self.post.call_count, 1)
        self.assertEqual(self.get.call_count, 5)
        for call in self.get.call_args_list[:-1]:
            self.assertEqual(call.args[0], "https://www.hfsyapi.cn/v1/video/query?id=existing-video")


class ModelInterfaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt_app = app.QApplication.instance() or app.QApplication([])

    def setUp(self):
        self.enterContext(patch.object(app.MainWindow, "refresh_balance"))
        self.enterContext(patch.object(app, "load_history", return_value=[]))
        self.enterContext(patch.object(app, "ensure_history_dir"))
        self.enterContext(patch.object(app, "load_ui_settings", return_value=dict(app.DEFAULT_UI_SETTINGS)))
        self.enterContext(patch.object(app, "save_ui_settings"))
        self.warning = self.enterContext(patch.object(app.QMessageBox, "warning"))
        self.post = self.enterContext(patch.object(app.requests, "post", side_effect=AssertionError("Unexpected API call")))
        self.get = self.enterContext(patch.object(app.requests, "get", side_effect=AssertionError("Unexpected API call")))
        self.window = app.MainWindow("test-key")
        self.addCleanup(self.window.deleteLater)
        self.window.scheduler.enqueue = Mock(return_value=True)

    def select_video(self, model):
        self.window.video_model_combo._select_model(model)

    def test_every_image_model_updates_controls(self):
        self.assertEqual(self.window.model_combo.model_groups, app.IMAGE_MODEL_GROUPS)
        self.assertEqual(
            [self.window.model_combo.itemText(i) for i in range(self.window.model_combo.count())],
            ["gpt-image-2 ▸", "gpt-image-2", "gpt-image-2.5 ▸", "gpt-image-2.6 ▸",
             "gemini-image ▸", "nano-banana ▸", "seedream-5.0-pro"],
        )
        for model, qualities in app.MODEL_QUALITY.items():
            with self.subTest(model=model):
                self.window.model_combo._select_model(model)
                self.assertEqual(self.window.quality_combo.count(), len(qualities))
                self.assertEqual(self.window.size_combo.count(), len(app.IMAGE_MODEL_RATIOS[model]))
                self.assertEqual(self.window.background_combo.isHidden(),
                                 model not in app.IMAGE_MODELS_WITH_TRANSPARENT_BACKGROUND)

    def test_image_task_uses_unified_pixel_sizes(self):
        self.window.model_combo._select_model("gemini-3-pro-image-preview")
        self.window.size_combo.setCurrentText("16:9")
        self.window.quality_combo.setCurrentText("4k")
        self.window.prompt_input.setPlainText("test")
        self.window.on_generate()
        task = self.window.scheduler.enqueue.call_args.args[0]
        self.assertEqual(task.params["size"], "3840x2160")
        self.assertNotIn("response_format", task.params)
        self.warning.assert_not_called()

    def test_image_prompt_and_reference_limits_block_enqueue(self):
        self.window.prompt_input.setPlainText("x" * 5001)
        self.window.on_generate()
        self.window.prompt_input.setPlainText("test")
        self.window.model_combo._select_model("nano-banana-2.1")
        self.window.img_ref_url.setText(" ".join(f"https://example.com/{i}.png" for i in range(5)))
        self.window.on_generate()
        self.assertEqual(self.warning.call_count, 2)
        self.window.scheduler.enqueue.assert_not_called()

    def test_muse_and_existing_video_control_switches(self):
        self.select_video("muse-video")
        self.assertTrue(self.window.video_size_combo.isHidden())
        self.assertTrue(self.window.video_orientation_label.isHidden())
        self.assertFalse(self.window.vid_ratio_combo.isHidden())
        self.assertFalse(self.window.vid_video_ref_card.isHidden())
        self.assertEqual(self.window.vid_ratio_combo.count(), 3)
        self.assertEqual(self.window.video_duration_combo.count(), 27)
        self.select_video("sd-2.5-720")
        self.assertFalse(self.window.video_size_combo.isHidden())
        self.assertFalse(self.window.vid_size_combo.isHidden())
        self.select_video("wan-3.0-720")
        self.assertTrue(self.window.vid_video_ref_card.isHidden())
        self.assertFalse(self.window.vid_audio_ref_card.isHidden())

    def test_reference_preview_and_mentions_use_matching_tokens(self):
        self.select_video("sd-2.5-720")
        self.window._vid_img_ref_data_list = [{"url": "https://example.com/1.png", "bytes": b"invalid"}]
        self.window._vid_video_ref_url_list = ["https://example.com/video.mp4"]
        self.window._vid_audio_ref_url_list = ["https://example.com/audio.mp3"]
        self.window._refresh_vid_img_ref_preview()
        self.window._refresh_vid_video_ref_list()
        self.window._refresh_vid_audio_ref_list()
        self.assertEqual(self.window._mention_candidates(), ["image1", "video1", "audio1"])
        buttons = self.window.vid_img_ref_preview_layout.itemAt(0).widget().findChildren(app.QPushButton)
        self.assertTrue(any("@image1" in button.text() for button in buttons))

    def test_total_reference_count_blocks_generation(self):
        self.select_video("sd-2-fast-480")
        self.window.video_prompt_input.setPlainText("test")
        self.window._vid_img_ref_data_list = [{"url": "https://example.com/image.png"}] * 9
        self.window._vid_video_ref_url_list = ["https://example.com/video.mp4"] * 3
        self.window._vid_audio_ref_url_list = ["https://example.com/audio.mp3"]
        self.assertEqual(self.window._remaining_video_ref_slots(), 0)
        self.window.on_generate_video()
        self.warning.assert_called_once()
        self.assertIn("12", self.warning.call_args.args[-1])
        self.window.scheduler.enqueue.assert_not_called()

    def test_muse_task_has_ratio_without_orientation(self):
        self.select_video("muse-video")
        self.window.video_prompt_input.setPlainText("test")
        self.window.vid_ratio_combo.setCurrentText("16:9")
        self.window.on_generate_video()
        task = self.window.scheduler.enqueue.call_args.args[0]
        self.assertIsNone(task.params["size"])
        self.assertEqual(task.params["sd_ratio"], "16:9")
        self.assertEqual(task.params["orientation_label"], "16:9")
        self.warning.assert_not_called()

    def test_video_task_card_shows_download_progress(self):
        task = app.Task("video", {}, {"label": "minimax-h3", "count": 1})
        task.status = "running"
        card = app.TaskCard(task, self.window)
        self.window.scheduler.all_tasks[task.id] = task
        self.window._task_cards[task.id] = card

        self.window._on_task_progress(task.id, "第1个视频: 正在下载...")

        self.assertEqual(card.status_lbl.text(), "下载中")

    def test_sd_video_reference_requires_an_image(self):
        self.select_video("sd-2-vip-480")
        self.window.video_prompt_input.setPlainText("test")
        self.window._vid_video_ref_url_list = ["https://example.com/video.mp4"]
        self.window.on_generate_video()
        self.warning.assert_called_once()
        self.window.scheduler.enqueue.assert_not_called()


if __name__ == "__main__":
    unittest.main()

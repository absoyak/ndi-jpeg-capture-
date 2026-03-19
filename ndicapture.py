import os
import time
from datetime import datetime, timezone
from queue import Queue, Full, Empty
from threading import Thread, Event

import cv2
from cyndilib.wrapper.ndi_recv import RecvColorFormat, RecvBandwidth
from cyndilib.finder import Finder
from cyndilib.receiver import Receiver
from cyndilib.video_frame import VideoFrameSync

TARGET_SOURCE_NAME = "NDISOURCE"

OUTPUT_BASE = r"C:\Frames"
TARGET_FPS = 25.0
FRAME_PERIOD = 1.0 / TARGET_FPS

JPEG_QUALITY = 85  # 75-90 is typical sweet spot. Raise if you can still keep 25 fps.
WRITER_THREADS = 4
QUEUE_MAX = 200  # buffer size in frames. Too big = RAM blow-up. Too small = drops.


def get_dotnet_ticks_utc() -> int:
    epoch = datetime(1, 1, 1, tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    delta = now - epoch
    return int(delta.total_seconds() * 10_000_000)


def choose_source_name(finder: Finder) -> str:
    names = finder.get_source_names()
    if not names:
        raise RuntimeError("No NDI sources found.")
    for n in names:
        if TARGET_SOURCE_NAME.lower() in n.lower():
            return n
    return names[0]


def writer_loop(stop_evt: Event, q: Queue, out_dir: str) -> None:
    jpg_params = [int(cv2.IMWRITE_JPEG_QUALITY), int(JPEG_QUALITY)]
    while not stop_evt.is_set():
        try:
            ticks, frame_rgba = q.get(timeout=0.2)
        except Empty:
            continue

        try:
            # frame_rgba is (H,W,4) uint8
            frame_bgr = cv2.cvtColor(frame_rgba, cv2.COLOR_RGBA2BGR)
            path = os.path.join(out_dir, f"{ticks}.jpg")
            cv2.imwrite(path, frame_bgr, jpg_params)
        finally:
            q.task_done()


def main() -> None:
    session_dir = os.path.join(OUTPUT_BASE, datetime.now().strftime("%Y%m%d_%H%M%S"))
    os.makedirs(session_dir, exist_ok=True)

    q: Queue = Queue(maxsize=QUEUE_MAX)
    stop_evt = Event()

    # Start writer threads
    writers = []
    for _ in range(WRITER_THREADS):
        t = Thread(target=writer_loop, args=(stop_evt, q, session_dir), daemon=True)
        t.start()
        writers.append(t)

    finder = Finder()
    receiver = Receiver(
        color_format=RecvColorFormat.RGBX_RGBA,
        bandwidth=RecvBandwidth.highest,
    )

    video_frame = VideoFrameSync()
    receiver.frame_sync.set_video_frame(video_frame)

    finder.open()

    # Wait up to 5s for discovery
    chosen_name = None
    deadline = time.time() + 5.0
    while time.time() < deadline:
        try:
            chosen_name = choose_source_name(finder)
            break
        except RuntimeError:
            time.sleep(0.1)

    if not chosen_name:
        finder.close()
        stop_evt.set()
        raise SystemExit("No NDI sources discovered within 5 seconds.")

    print(f"Using NDI source: {chosen_name}")
    receiver.set_source(finder.get_source(chosen_name))

    print(f"Recording to: {session_dir}")
    print("Press CTRL+C to stop.")
    print(f"JPEG quality={JPEG_QUALITY}, writers={WRITER_THREADS}, queue={QUEUE_MAX}")

    saved = 0
    dropped = 0

    # Sample exactly at 25 Hz based on perf_counter
    next_t = time.perf_counter()

    try:
        while True:
            now = time.perf_counter()
            if now < next_t:
                time.sleep(next_t - now)
            next_t += FRAME_PERIOD

            if not receiver.is_connected():
                continue

            receiver.frame_sync.capture_video()

            if min(video_frame.xres, video_frame.yres) == 0:
                continue

            # Copy frame immediately (NDI buffer gets reused)
            frame_rgba = video_frame.get_array().reshape(video_frame.yres, video_frame.xres, 4).copy()
            ticks = get_dotnet_ticks_utc()

            try:
                q.put((ticks, frame_rgba), block=False)
                saved += 1
            except Full:
                dropped += 1

            # Print once per second-ish
            if saved % 25 == 0:
                print(f"Saved={saved} Dropped={dropped} Queue={q.qsize()} Last={ticks}.jpg")

    except KeyboardInterrupt:
        print("\nStopping...")

    finally:
        # Stop capture
        if receiver.is_connected():
            receiver.disconnect()
        finder.close()

        # Drain queue
        q.join()
        stop_evt.set()

        print(f"Done. Saved={saved}, Dropped={dropped}")
        print(f"Folder: {session_dir}")


if __name__ == "__main__":
    main()

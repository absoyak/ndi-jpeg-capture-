# ndi-jpeg-capture

Captures an NDI video stream at a fixed FPS, saving frames as JPEG files named with .NET DateTime.Ticks for precise timestamp-based retrieval.

## Requirements

```
pip install cyndilib opencv-python
```

NDI Runtime must be installed on the machine: https://ndi.video/tools/

## Configuration

Edit the constants at the top of `ndicapture.py`:

| Constant | Default | Description |
|---|---|---|
| `TARGET_SOURCE_NAME` | `"NDISOURCE"` | NDI source name to look for |
| `OUTPUT_BASE` | `C:\Frames` | Root folder where session folders are created |
| `TARGET_FPS` | `25.0` | Frames per second to capture |
| `JPEG_QUALITY` | `85` | JPEG quality (75–95 recommended) |
| `WRITER_THREADS` | `4` | Number of parallel disk writer threads |
| `QUEUE_MAX` | `200` | In-memory frame buffer size |

## Usage

```bash
python ndicapture.py
```

On start, the script discovers available NDI sources and connects to the one matching `TARGET_SOURCE_NAME`. A new session folder is created under `OUTPUT_BASE` named by the current date and time (e.g. `20260319_143000`).

Frames are saved as:
```
<OUTPUT_BASE>/<session>/638781234567890000.jpg
```

Press `CTRL+C` to stop. The script drains the write queue before exiting.

## Output

Each frame is saved as a JPEG file whose name is the capture time expressed as [.NET DateTime.Ticks](https://learn.microsoft.com/en-us/dotnet/api/system.datetime.ticks) in UTC. This allows downstream systems to look up any frame by timestamp without needing a separate index file.

## License

MIT

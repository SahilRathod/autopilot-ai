# V0.6.1 local post-production

After assembling an approved MP4, open Media Studio → Render tasks & exports and choose your video. The post-production panel supports:

- SRT input with explicit non-overlapping timestamp cues; edit before attaching. Captions are muxed as switchable MP4 subtitles without re-encoding the video stream.
- Imported narration audio in media/raw (WAV, MP3, M4A, AAC, OGG, FLAC), mixed from the beginning of the video with adjustable original and narration volumes. Use only audio you own or have rights to.
- 1280×720 JPEG thumbnail frame at your chosen timestamp. The image is a frame extraction, not a generative graphic. Save it and add it in YouTube Studio manually.
- Earlier video revisions remain stored, and you can activate an earlier version before any upload record exists.

## Optional offline speech recognition

The ordinary application does not need a speech model. On Windows, install it explicitly if desired:

    .\.venv\Scripts\python.exe -m pip install faster-whisper
    .\.venv\Scripts\python.exe -c "from huggingface_hub import snapshot_download; snapshot_download(repo_id='Systran/faster-whisper-base', local_dir='data/models/whisper-base')"

The second command downloads model weights once from Hugging Face. After that, transcription runs locally on CPU with INT8, four CPU threads and local-files-only mode, so no cloud audio upload occurs.

    .\.venv\Scripts\python.exe -m app.postproduction transcribe --workspace 1 --channel 1 --job 1 --language hi

Replace IDs and choose hi, en, or omit language for automatic detection. The output is a timed SRT file in media/output. Open that file using the post-production panel and review the actual words and timing, especially Hinglish. Do not assume Whisper is always accurate.

Speech recognition has mocked segment tests; model execution and real speech accuracy are not tested by CI. FFmpeg caption mux, narration mix and thumbnail creation have real synthetic-video integration tests. Large revisions are synchronous and can take time. The upload queue protects the reviewed file fingerprint and refuses revisions after an upload record is created. Embedded subtitles may not be displayed in every browser or imported by YouTube; use your SRT file in YouTube Studio if necessary.

Model documentation: https://github.com/SYSTRAN/faster-whisper and https://huggingface.co/Systran/faster-whisper-base.

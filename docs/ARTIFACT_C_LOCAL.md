# Artifact C: local asynchronous service

Start the stack with `docker compose up --build`. The API is available at
`http://localhost:8000/docs` and uses a fake inference worker by default so the
integration path is free and CPU-compatible. Submit a video with:

```bash
curl -F video=@sample.mp4 http://localhost:8000/jobs
curl http://localhost:8000/jobs/<job_id>
```

Set `VIDEO_USE_FAKE_INFERENCE=false` only in a GPU worker image that includes
the model runtime. PostgreSQL is authoritative for job state; Valkey is only
the queue; generated results are persisted in the shared artifact volume.

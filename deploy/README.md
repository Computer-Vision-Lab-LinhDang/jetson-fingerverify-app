# MDGT Edge — Deployment

## Database replication with Litestream

`data/mdgt_edge.db` is continuously streamed (WAL frames) to an S3-compatible
object store.  One-line install:

```bash
sudo bash scripts/install_litestream.sh
sudo vi /etc/default/mdgt-litestream     # fill in bucket + credentials
sudo systemctl restart mdgt-litestream
```

### Provider options

| Provider       | Notes                                      | Endpoint                                                  |
| -------------- | ------------------------------------------ | --------------------------------------------------------- |
| Cloudflare R2  | Recommended — zero egress, S3-compatible   | `https://<account-id>.r2.cloudflarestorage.com`           |
| AWS S3         | Standard choice                            | *(leave empty, just set `LITESTREAM_REGION`)*             |
| Backblaze B2   | Cheapest storage tier                      | `https://s3.<region>.backblazeb2.com`                     |
| MinIO (self)   | For on-prem / air-gapped setups            | `http://<host>:9000`                                      |

### Restore on a new Jetson

```bash
sudo systemctl stop mdgt-edge        # (if the app is running)
litestream restore -config /etc/litestream.yml \
    -o /opt/mdgt-edge/data/mdgt_edge.db \
    /opt/mdgt-edge/data/mdgt_edge.db
sudo systemctl start mdgt-edge
```

### Multi-device isolation

Each device writes to `mdgt-edge/<LITESTREAM_DEVICE_ID>/` inside the bucket, so
setting a unique `LITESTREAM_DEVICE_ID` per Jetson keeps replicas separate.
Set `LITESTREAM_DEVICE_ID` to match `config/default.yaml -> device.id`.

### Cost / bandwidth expectations

Litestream ships only WAL frames since the last snapshot, not the full DB.
With typical enrollment volume (a few MB/day) expect < 100 MB/month per
device.  Snapshots run every 24 h; history retained 72 h — tunable in
`deploy/litestream.yml`.

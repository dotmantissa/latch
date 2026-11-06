#!/usr/bin/env bash
# Run as root on the separately inventoried Vultr control VM after staged file transfer.
set -euo pipefail
[[ $EUID == 0 && $(hostname -s) == latch-control ]]
cd /opt/latch-control
umask 077
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq caddy cryptsetup e2fsprogs ca-certificates curl
for LATCH_USER in latch-api latch-runner; do
  id "$LATCH_USER" >/dev/null 2>&1 || useradd --system --user-group --no-create-home --shell /usr/sbin/nologin "$LATCH_USER"
done
getent group latch-artifacts >/dev/null || groupadd --system latch-artifacts
usermod -aG latch-artifacts latch-api
usermod -aG latch-artifacts latch-runner
install -d -m 0751 /var/lib/latch-control
install -d -m 0700 /etc/latch /etc/latch/api /etc/latch/runner
install -d -m 0700 -o latch-runner -g latch-runner /etc/latch/runner/tls
install -m 0600 -o latch-api -g latch-api /etc/latch/bootstrap/database-url /etc/latch/api/database-url
install -m 0600 -o latch-api -g latch-api /etc/latch/bootstrap/csrf-key /etc/latch/api/csrf-key
install -m 0600 -o latch-api -g latch-api /etc/latch/bootstrap/backup-key /etc/latch/api/backup-key
install -m 0600 -o latch-runner -g latch-runner /etc/latch/bootstrap/database-url /etc/latch/runner/database-url
install -m 0600 -o latch-runner -g latch-runner /etc/latch/bootstrap/vultr-inference-key /etc/latch/runner/inference-key
install -m 0600 -o latch-runner -g latch-runner /etc/latch/bootstrap/tunnel-key /etc/latch/runner/tunnel-key
install -m 0600 -o latch-runner -g latch-runner /etc/latch/bootstrap/worker-known-hosts /etc/latch/runner/worker-known-hosts
for LATCH_CERT in ca.crt runner.crt runner.key; do
  install -m 0600 -o latch-runner -g latch-runner "/etc/latch/bootstrap/tls/$LATCH_CERT" "/etc/latch/runner/tls/$LATCH_CERT"
done
if [[ -f /etc/latch/volume-key ]] && ! cmp -s /etc/latch/bootstrap/volume-key /etc/latch/volume-key; then
  printf '%s\n' 'Existing encrypted volume key differs; preserve recovery material.' >&2
  exit 1
fi
install -m 0600 /etc/latch/bootstrap/volume-key /etc/latch/volume-key
# Parent traversal only; each child and secret keeps its own private access.
chmod 0751 /etc/latch
chown latch-api:latch-api /etc/latch/api
chown latch-runner:latch-runner /etc/latch/runner
if [[ ! -f /var/lib/latch-control/artifacts.luks ]]; then
  truncate -s 4G /var/lib/latch-control/artifacts.luks
  chmod 0600 /var/lib/latch-control/artifacts.luks
  cryptsetup luksFormat --type luks2 --batch-mode --key-file /etc/latch/volume-key /var/lib/latch-control/artifacts.luks
  cryptsetup open --key-file /etc/latch/volume-key /var/lib/latch-control/artifacts.luks latch-artifacts
  mkfs.ext4 -q /dev/mapper/latch-artifacts
fi
install -d -m 0751 /var/lib/latch-control/data
cat > /etc/systemd/system/latch-storage.service <<'UNIT'
[Unit]
Description=Latch encrypted persistent evidence volume
Before=latch-api.service latch-runner.service
[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/bin/bash -c 'test -b /dev/mapper/latch-artifacts || /usr/sbin/cryptsetup open --key-file /etc/latch/volume-key /var/lib/latch-control/artifacts.luks latch-artifacts'
ExecStart=/bin/bash -c 'mountpoint -q /var/lib/latch-control/data || mount -o nodev,nosuid,noexec /dev/mapper/latch-artifacts /var/lib/latch-control/data'
ExecStop=/bin/umount /var/lib/latch-control/data
ExecStop=/usr/sbin/cryptsetup close latch-artifacts
[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable --now latch-storage.service
chmod 0751 /var/lib/latch-control/data
install -d -m 2770 -o latch-api -g latch-artifacts /var/lib/latch-control/data/evidence /var/lib/latch-control/data/exports
install -d -m 0700 -o latch-api -g latch-api /var/lib/latch-control/data/backups
install -d -m 0700 -o latch-runner -g latch-runner /var/lib/latch-control/data/quarantine
chmod 0755 /opt/latch-control/uv
export UV_PYTHON_INSTALL_DIR=/opt/latch-control/python
/opt/latch-control/uv python install --no-bin 3.13.18
if [[ ! -x /opt/latch-control/venv/bin/python ]]; then
  /opt/latch-control/uv venv --python 3.13.18 /opt/latch-control/venv
fi
/opt/latch-control/uv pip install --python /opt/latch-control/venv/bin/python --require-hashes --only-binary :all: -r infra/control/requirements.lock
# Application code and runtimes are public release material, never secrets.
find /opt/latch-control -type d -exec chmod a+rx {} +
find /opt/latch-control -type f -exec chmod a+r {} +
find /opt/latch-control/python -type f -perm /111 -exec chmod a+rx {} +
python3 - <<'PY'
import json,pwd,grp
from pathlib import Path
v=json.loads(Path('/etc/latch/bootstrap/control.json').read_text())
shared={'PGSSLCERT':'/etc/ssl/latch-no-client.crt','PGSSLKEY':'/etc/ssl/latch-no-client.key','PGSSLROOTCERT':'/etc/ssl/certs/ca-certificates.crt','LATCH_PUBLIC_ORIGIN':'https://'+v['hostname'],'LATCH_ENABLE_INSPECTIONS':'true','LATCH_ENABLE_DEMO':'true',
'LATCH_STATIC_DIR':'/opt/latch-control/dist','LATCH_EVIDENCE_DIR':'/var/lib/latch-control/data/evidence',
'LATCH_ARTIFACT_GROUP_ID':str(grp.getgrnam('latch-artifacts').gr_gid),
'LATCH_ARTIFACT_OWNER_IDS':','.join(str(pwd.getpwnam(n).pw_uid) for n in ['latch-api','latch-runner'])}
for role in ['api','runner']:
 env={**shared,'LATCH_DATABASE_URL_FILE':f'/etc/latch/{role}/database-url',
      'LATCH_CSRF_KEY_FILE':'/etc/latch/api/csrf-key'}
 if role=='runner': env.update(LATCH_MODEL_ID=v['model'],LATCH_INFERENCE_KEY_FILE='/etc/latch/runner/inference-key')
 Path(f'/etc/latch/{role}.env').write_text(''.join(f'{k}={value}\n' for k,value in env.items()))
Path('/etc/caddy/Caddyfile').write_text(v['hostname']+' {\n  encode zstd gzip\n  reverse_proxy 127.0.0.1:8080\n}\n')
Path('/etc/latch/tunnel.env').write_text('LATCH_WORKER_HOST='+v['worker_ip']+'\n')
PY
chmod 0600 /etc/latch/*.env
for LATCH_ROLE in api runner; do
  cat > "/etc/systemd/system/latch-$LATCH_ROLE.service" <<UNIT
[Unit]
Description=Latch $LATCH_ROLE service
Requires=latch-storage.service
After=network-online.target latch-storage.service
Wants=network-online.target
[Service]
Type=simple
User=latch-$LATCH_ROLE
Group=latch-$LATCH_ROLE
SupplementaryGroups=latch-artifacts
WorkingDirectory=/opt/latch-control
EnvironmentFile=/etc/latch/$LATCH_ROLE.env
Environment=PYTHONDONTWRITEBYTECODE=1
Restart=on-failure
RestartSec=3
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
PrivateDevices=yes
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectControlGroups=yes
RestrictSUIDSGID=yes
LockPersonality=yes
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6
CapabilityBoundingSet=
UMask=0077
LimitNOFILE=512
MemoryMax=1200M
TasksMax=64
ReadWritePaths=/var/lib/latch-control/data
UNIT
  if [[ $LATCH_ROLE == api ]]; then
    printf '%s\n' 'ExecStart=/opt/latch-control/venv/bin/python -m uvicorn services.api.app:create_app --factory --host 127.0.0.1 --port 8080 --proxy-headers --forwarded-allow-ips 127.0.0.1 --no-access-log' >> "/etc/systemd/system/latch-$LATCH_ROLE.service"
  else
    printf '%s\n' 'ExecStart=/opt/latch-control/venv/bin/python -m services.runner.jobs --tls /etc/latch/runner/tls --artifacts /var/lib/latch-control/data/quarantine' >> "/etc/systemd/system/latch-$LATCH_ROLE.service"
  fi
  printf '\n%s\n%s\n' '[Install]' 'WantedBy=multi-user.target' >> "/etc/systemd/system/latch-$LATCH_ROLE.service"
done
cat > /etc/systemd/system/latch-tunnel.service <<'UNIT'
[Unit]
Description=Latch runner restricted private worker channel
After=network-online.target
Wants=network-online.target
Before=latch-runner.service
[Service]
User=latch-runner
Group=latch-runner
EnvironmentFile=/etc/latch/tunnel.env
ExecStart=/usr/bin/ssh -N -i /etc/latch/runner/tunnel-key -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile=/etc/latch/runner/worker-known-hosts -o ExitOnForwardFailure=yes -o ServerAliveInterval=15 -o ServerAliveCountMax=3 -L 127.0.0.1:9443:127.0.0.1:9443 latch-tunnel@${LATCH_WORKER_HOST}
Restart=always
RestartSec=3
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
CapabilityBoundingSet=
[Install]
WantedBy=multi-user.target
UNIT
cat > /etc/systemd/system/latch-backup.service <<'UNIT'
[Unit]
Description=Latch encrypted consistent database and evidence backup
Requires=latch-storage.service
After=latch-storage.service
[Service]
Type=oneshot
User=latch-api
Group=latch-api
SupplementaryGroups=latch-artifacts
WorkingDirectory=/opt/latch-control
EnvironmentFile=/etc/latch/api.env
ExecStart=/opt/latch-control/venv/bin/python -m services.storage.recovery backup --key-file /etc/latch/api/backup-key --store /var/lib/latch-control/data/backups
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
ReadWritePaths=/var/lib/latch-control/data/backups
UNIT
cat > /etc/systemd/system/latch-backup.timer <<'UNIT'
[Unit]
Description=Daily Latch recovery snapshot
[Timer]
OnCalendar=daily
Persistent=true
[Install]
WantedBy=timers.target
UNIT
systemctl daemon-reload
systemctl enable --now latch-tunnel.service
systemctl enable latch-api.service latch-runner.service latch-backup.timer
caddy validate --config /etc/caddy/Caddyfile
systemctl restart caddy
# API/runner activation follows verified migration and initial profile admission.
printf '%s\n' 'Control host installed; API and runner activation pending schema verification.'
